"""M2 multi-instance anytime evaluator, also the native Shinka job entrypoint.

No model calls. The candidate evolves; graph/OD/scorer/splits/clocks do not.
M1 evaluate.py and its historical results remain independently reproducible.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from math import fsum
from pathlib import Path
import platform
import os
import random
import sys
from time import perf_counter

from swarm_location.anytime import run_anytime
from swarm_location.core import ShortestPathCoverage
from swarm_location.suite import file_sha256, load_suite
from swarm_location.comparisons import (evaluation_methods, comparison_spec,
                                        paired_comparisons, comparison_feedback)

ROOT = Path(__file__).resolve().parent


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def mean(values):
    return fsum(values) / len(values)


def summarize(records):
    rows = []
    methods = sorted(records[0]["methods"])
    for dataset in sorted({r["dataset"] for r in records}):
        group = [r for r in records if r["dataset"] == dataset]
        for method in methods:
            final = [r["methods"][method]["final_coverage"] for r in group]
            checkpoint = [r["methods"][method]["mean_checkpoint_coverage"] for r in group]
            rows.append({"dataset": dataset, "method": method, "runs": len(group),
                "mean_final_coverage_pct": 100 * mean(final),
                "mean_checkpoint_coverage_pct": 100 * mean(checkpoint),
                "mean_delta_vs_greedy_pp": 100 * mean([
                    r["methods"][method]["mean_checkpoint_coverage"] -
                    r["methods"]["greedy"]["mean_checkpoint_coverage"] for r in group])})
    return rows


def evaluate(program_path, results_dir, suite_path, split="development", baselines_only=False,
             feedback_profile=None):
    output = Path(results_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Mark incomplete before work, including interrupted or failed reruns.
    write_json(output / "correct.json", {"correct": False, "error": "evaluation incomplete"})
    write_json(output / "metrics.json", {"combined_score": 0.0, "text_feedback": "evaluation incomplete"})
    # A failed rerun must not leave a seemingly current successful comparison.
    (output / "comparisons.json").unlink(missing_ok=True)
    for name in ("feedback.json", "diagnostics.json"):
        (output / name).unlink(missing_ok=True)
    records, prep = [], []
    started = perf_counter()
    suite_path = Path(suite_path).resolve()
    candidate = None if baselines_only else Path(program_path).resolve()
    try:
        from swarm_location.feedback import checked_profile, load_context, evidence_packet, text_feedback
        checked_profile(feedback_profile)
        context = load_context() if feedback_profile else None
        protocol, instances = load_suite(suite_path, split)
        tracked = [suite_path, Path(__file__).resolve(), *sorted((ROOT / "swarm_location").glob("*.py"))]
        if context:
            tracked.extend(ROOT / name for name in context["source_sha256"])
        if candidate is not None:
            tracked.append(candidate)
        before = {str(p): file_sha256(p) for p in tracked}
        methods = evaluation_methods(protocol, split, baselines_only)
        comparison = comparison_spec(protocol, split)
        checkpoints = protocol["checkpoints_seconds"]
        for entry, instance in instances:
            then = perf_counter()
            oracle = ShortestPathCoverage(instance)
            prep.append({"dataset": entry["id"], "parent_oracle_seconds": perf_counter() - then,
                         "nodes": len(instance.nodes), "edges": len(instance.edges),
                         "positive_od_pairs": sum(q > 0 for _, _, q in instance.od),
                         "origins": len(oracle.dags), "first_thru_node": instance.first_thru_node,
                         "shortest_routes": sum(d.counts[t] for d in oracle.dags for t, _ in d.destinations),
                         "dataset_sha256": entry["sha256"]})
            for k in entry["budgets"]:
                for seed in protocol["seeds"]:
                    order = list(methods)
                    random.Random(f"{entry['id']}:{k}:{seed}").shuffle(order)
                    observed = {}
                    for method in order:
                        observed[method] = run_anytime(instance, k, checkpoints, seed=seed, oracle=oracle,
                            program_path=candidate if method == "candidate" else None,
                            baseline=None if method == "candidate" else method,
                            **({"feedback_profile": feedback_profile} if feedback_profile else {}))
                    records.append({"dataset": entry["id"], "source_graph": entry["source_graph"],
                                    "k": k, "seed": seed, "execution_order": order, "methods": observed})
                    write_json(output / "traces.json", {"stage": "m2_in_progress", "cases": records})
                    print(f"{entry['id']} k={k} seed={seed}: " + ", ".join(
                        f"{m}={100*observed[m]['final_coverage']:.4f}%" for m in methods), flush=True)
        if any(file_sha256(p) != digest for p, digest in before.items()):
            raise RuntimeError("candidate, evaluator, or suite changed during evaluation")
        selected = "greedy_swap" if baselines_only else "candidate"
        failures = [{"dataset": r["dataset"], "k": r["k"], "seed": r["seed"], "method": method,
                     "error": result["error"]} for r in records for method, result in r["methods"].items()
                    if not result["correct"]]
        delta = 100 * mean([r["methods"][selected]["mean_checkpoint_coverage"] -
                            r["methods"]["greedy"]["mean_checkpoint_coverage"] for r in records])
        delta_swap = 100 * mean([r["methods"][selected]["mean_checkpoint_coverage"] -
                                 r["methods"]["greedy_swap"]["mean_checkpoint_coverage"] for r in records])
        coverage = 100 * mean([r["methods"][selected]["mean_checkpoint_coverage"] for r in records])
        summary = summarize(records)
        budget_feedback = []
        for dataset, k in sorted({(r["dataset"], r["k"]) for r in records}):
            group = [r for r in records if r["dataset"] == dataset and r["k"] == k]
            versus_greedy = 100 * mean([r["methods"][selected]["mean_checkpoint_coverage"] -
                                        r["methods"]["greedy"]["mean_checkpoint_coverage"] for r in group])
            versus_swap = 100 * mean([r["methods"][selected]["mean_checkpoint_coverage"] -
                                      r["methods"]["greedy_swap"]["mean_checkpoint_coverage"] for r in group])
            budget_feedback.append(f"{dataset} k={k}: greedy {versus_greedy:+.4f} pp, swap {versus_swap:+.4f} pp")
        feedback = (f"{len(records)} paired cases on {len(instances)} source datasets; split={split}. "
            f"Mean checkpoint coverage {coverage:.6f}%; delta versus timed greedy {delta:+.6f} pp; "
            f"delta versus timed fixed greedy+swap {delta_swap:+.6f} pp. "
            "Inspect per-source and per-budget records before proposing a mechanism. Scores are exact-route "
            "model calculations, not real-world detection or causal evidence. A result on development "
            "data is not generalization. Meta interpretations cannot change numerical fitness. " + "; ".join(budget_feedback))
        metrics = {"combined_score": 0.0 if failures else 100.0 + delta,
            "public": {"stage": "m2_fixed_baselines" if baselines_only else "m2_anytime_candidate_evaluation",
                       "split": split, "paired_cases": len(records), "source_datasets": len(instances),
                       "mean_checkpoint_coverage_pct": coverage, "delta_vs_greedy_pp": delta,
                       "delta_vs_greedy_swap_pp": delta_swap, "failed_cases": len(failures)},
            "private": {"suite_sha256": before[str(suite_path)],
                        "candidate_sha256": None if candidate is None else before[str(candidate)],
                        "implementation_sha256": {str(p.relative_to(ROOT)): before[str(p)] for p in tracked if p.is_relative_to(ROOT) and p != candidate and p != suite_path},
                        "python": platform.python_version(), "platform": platform.platform(),
                        "docker_image_id": os.environ.get("SWARM_DOCKER_IMAGE"),
                        "wall_seconds": perf_counter() - started,
                        "evaluated_utc": datetime.now(timezone.utc).isoformat()},
            "extra_data": {"summary": summary, "preprocessing": prep, "failures": failures},
            "text_feedback": feedback}
        comparisons = None
        if comparison is not None:
            comparisons = paired_comparisons(records, selected, comparison)
            metrics["extra_data"]["comparisons"] = comparisons
            metrics["private"]["comparison_profile"] = comparison
            metrics["public"]["stage"] = "m4_fixed_baselines" if baselines_only else "m4_anytime_candidate_evaluation"
            metrics["public"]["fixed_controls"] = len(comparison["baselines"])
            metrics["public"]["solver_trials"] = sum(len(r["methods"]) for r in records)
            for row in comparisons["rows"]:
                if row["scope"] == "overall" and row["valid"]:
                    metrics["public"]["delta_vs_" + row["baseline"] + "_pp"] = row["delta_mean_checkpoint_pp"]
                    metrics["public"]["final_delta_vs_" + row["baseline"] + "_pp"] = row["delta_final_pp"]
            metrics["text_feedback"] += comparison_feedback(comparisons)
            write_json(output / "comparisons.json", comparisons)
        if feedback_profile:
            packet = evidence_packet(records, comparisons, split, selected)
            metrics["text_feedback"] = text_feedback(packet)
            metrics["extra_data"]["feedback"] = packet
            metrics["private"]["feedback_context"] = {
                "profile_id": feedback_profile, "source_sha256": context["source_sha256"]}
            # These diagnostics do not enter scalar/public numerical reward fields.
            write_json(output / "feedback.json", packet)
            write_json(output / "diagnostics.json", {"schema_version": 1,
                "profile_id": feedback_profile, "scoring_input": False,
                "trials": [{"dataset": row["dataset"], "k": row["k"], "seed": row["seed"],
                    "method": method, "diagnostics": trial.get("diagnostics")}
                    for row in records for method, trial in row["methods"].items()]})
        write_json(output / "traces.json", {"stage": "m2_complete", "protocol": protocol,
            "suite_sha256": before[str(suite_path)], "split": split, "cases": records})
        write_json(output / "metrics.json", metrics)
        write_json(output / "correct.json", {"correct": not failures,
                   "error": "" if not failures else json.dumps(failures)})
        return metrics
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        write_json(output / "correct.json", {"correct": False, "error": error})
        write_json(output / "metrics.json", {"combined_score": 0.0, "text_feedback": error})
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--program_path", default=str(ROOT / "anytime_initial.py"))
    p.add_argument("--results_dir", default=str(ROOT / "results/local_anytime"))
    p.add_argument("--suite", default=str(ROOT / "data/commissioning/suite.json"))
    p.add_argument("--split", choices=["development", "validation", "test"], default="development")
    p.add_argument("--baselines-only", action="store_true")
    p.add_argument("--feedback-profile", "--feedback_profile", dest="feedback_profile", choices=["m7-evidence-v1"])
    a = p.parse_args()
    result = evaluate(a.program_path, a.results_dir, a.suite, a.split, a.baselines_only, a.feedback_profile)
    print(json.dumps({"combined_score": result["combined_score"], **result["public"]}, indent=2))
    if result["public"]["failed_cases"]:
        sys.exit(1)

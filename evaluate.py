"""Step-1 commissioning evaluator; not the final anytime research fitness.

Default local backend requires only Python. --backend shinka uses SakanaAI's
native run_shinka_eval when separately installed. No LLM/API calls are made.
This evaluates reviewed seed code; neither backend is a hostile-code sandbox.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from math import fsum, isfinite
from pathlib import Path
import subprocess
import sys
import time

from swarm_location import Instance, ShortestPathCoverage
from swarm_location.baselines import greedy

ROOT = Path(__file__).resolve().parent


def evaluate(program_path: str, results_dir: str, instance_path: str,
             budgets: list[int], backend: str = "local", timeout: float = 30.0) -> dict:
    output = Path(results_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(Path(instance_path).read_text())
        instance = Instance.from_dict(data)
        if not budgets:
            raise ValueError("at least one budget is required")
        for k in budgets:
            instance.validate_budget(k)
        if not isfinite(timeout) or not timeout > 0:
            raise ValueError("timeout must be positive and finite")
        reference = ShortestPathCoverage(instance)
        fast = reference.compile_routes()
        path = str(Path(program_path).resolve())
        candidate_sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        instance_sha = hashlib.sha256(Path(instance_path).read_bytes()).hexdigest()
        observed_wall = []

        def get_kwargs(run_index):
            return {"instance_data": data, "k": budgets[run_index], "random_seed": 0}

        def aggregate(results):
            if len(results) != len(budgets):
                raise ValueError("wrong number of candidate outputs")
            records = []
            for k, selected in zip(budgets, results):
                if not isinstance(selected, list):
                    raise ValueError("candidate must return a list of node IDs")
                selected = instance.validate_selection(selected, k)
                coverage = reference.score(selected)  # Never use a candidate-reported score.
                base_set = greedy(fast, k)
                base = reference.score(base_set)
                records.append({"k": k, "selected": list(selected), "coverage": coverage,
                    "greedy_coverage": base, "improvement_pp": 100 * (coverage - base)})
            metrics = {
                "combined_score": 100 * fsum(r["coverage"] for r in records) / len(records),
                "public": {"stage": "step1_seed_commissioning", "instance": instance.name,
                    "mean_improvement_over_greedy_pp": fsum(r["improvement_pp"] for r in records) / len(records),
                    "evolved_generations": 0},
                "private": {"candidate_sha256": candidate_sha, "instance_sha256": instance_sha,
                    "backend": backend, "budgets": budgets,
                    "local_process_wall_seconds": observed_wall},
                "extra_data": {"cases": records},
                "text_feedback": (
                    "Fixed OD-weighted, endpoint-inclusive coverage; no route sampling or rerouting. "
                    "This is a commissioning score on one public debugging benchmark, not the "
                    "planned multi-network anytime fitness. Differences from greedy are in "
                    "extra_data.cases. No evolutionary or generalization result is established."
                ),
            }
            return metrics

        if backend == "shinka":
            from shinka.core import run_shinka_eval
            metrics, correct, error = run_shinka_eval(
                program_path=path, results_dir=str(output.resolve()),
                experiment_fn_name="run_experiment", num_runs=len(budgets), run_workers=1,
                get_experiment_kwargs=get_kwargs, aggregate_metrics_fn=aggregate,
            )
            if not correct:
                raise RuntimeError(error or "native evaluation failed")
        elif backend == "local":
            results = []
            for i in range(len(budgets)):
                start = time.perf_counter()
                completed = subprocess.run(
                    [sys.executable, "-m", "swarm_location.worker", path],
                    input=json.dumps(get_kwargs(i)), text=True, capture_output=True,
                    timeout=timeout, cwd=ROOT, check=True,
                )
                observed_wall.append(time.perf_counter() - start)
                results.append(json.loads(completed.stdout))
            metrics = aggregate(results)
        else:
            raise ValueError(f"unknown backend: {backend}")
        (output / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
        (output / "correct.json").write_text(json.dumps({"correct": True, "error": ""}, indent=2) + "\n")
        return metrics
    except Exception as exc:
        # Overwrite stale success artifacts so a failed rerun cannot appear successful.
        error = f"{type(exc).__name__}: {exc}"
        (output / "metrics.json").write_text(json.dumps({"combined_score": 0.0,
            "public": {}, "private": {}, "extra_data": {}, "text_feedback": error}, indent=2) + "\n")
        (output / "correct.json").write_text(json.dumps({"correct": False, "error": error}, indent=2) + "\n")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program_path", default=str(ROOT / "initial.py"))
    parser.add_argument("--results_dir", default=str(ROOT / "results/local_seed"))
    parser.add_argument("--instance", default=str(ROOT / "data/sioux_falls.json"))
    parser.add_argument("--budgets", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6, 7, 8])
    parser.add_argument("--backend", choices=["local", "shinka"], default="local")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="Per-process timeout for local backend only; not applied by native wrapper")
    args = parser.parse_args()
    result = evaluate(args.program_path, args.results_dir, args.instance, args.budgets, args.backend, args.timeout)
    print(json.dumps({"combined_score": result["combined_score"], **result["public"]}, indent=2))


if __name__ == "__main__":
    main()

"""Versioned fixed-control profiles and descriptive paired comparisons.

These reports do not replace fitness, select a different champion, pool hosts,
construct a pointwise oracle portfolio, or claim statistical significance.
Legacy suites without a profile retain their original methods and feedback.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from math import fsum, isfinite
from pathlib import Path

from .strong_baselines import METHODS

SPLITS = ("development", "validation", "test")
REQUIRED = ("greedy", "greedy_swap")
REGISTERED = ("random", "topk", *REQUIRED, *METHODS)
FITNESS = "100_plus_mean_checkpoint_delta_vs_greedy_pp"
ASSESSMENT_RULE = "report_all_fixed_controls_no_automatic_discovery_claim"


def definition_sha256(definition: dict) -> str:
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checked_methods(methods: object) -> list[str]:
    if (not isinstance(methods, list) or not methods
            or any(not isinstance(m, str) or m not in REGISTERED for m in methods)
            or len(set(methods)) != len(methods)
            or not set(REQUIRED).issubset(methods)):
        raise ValueError("baselines must be unique registered fixed controls including greedy and greedy_swap")
    return list(methods)


def checked_definition(definition: object) -> dict:
    if not isinstance(definition, dict) or set(definition) != {
            "schema_version", "profile_id", "fitness", "baseline_sets", "assessment_rule"}:
        raise ValueError("unexpected comparison profile fields")
    if type(definition["schema_version"]) is not int or definition["schema_version"] != 1:
        raise ValueError("expected comparison profile schema 1")
    name = definition["profile_id"]
    if not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise ValueError("comparison profile_id must be a nonempty lowercase identifier")
    if definition["fitness"] != FITNESS or definition["assessment_rule"] != ASSESSMENT_RULE:
        raise ValueError("this integration does not change fitness or automate discovery claims")
    stages = definition["baseline_sets"]
    if not isinstance(stages, dict) or set(stages) != set(SPLITS):
        raise ValueError("define development, validation and test comparator sets explicitly")
    for split in SPLITS:
        checked_methods(stages[split])
    if stages["validation"] != stages["test"]:
        raise ValueError("validation and test must use the same ordered assessment controls")
    if not set(stages["development"]).issubset(stages["test"]):
        raise ValueError("assessment must include every development control")
    return deepcopy(definition)


def load_profile(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    definition = checked_definition(json.loads(raw))
    return {"definition": definition, "definition_sha256": definition_sha256(definition),
            "file_sha256": hashlib.sha256(raw).hexdigest()}


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def bind_profile(suite: dict, profile: dict, split: str) -> dict:
    """Add explicit comparator metadata without touching dataset bytes or budgets."""
    if split not in SPLITS:
        raise ValueError("unknown comparison stage")
    result = deepcopy(suite)
    result["comparison_profile"] = {**deepcopy(profile), "stage": split}
    methods = profile["definition"]["baseline_sets"][split]
    result["extra_baselines"] = [m for m in methods if m not in REQUIRED]
    comparison_spec(result, split)
    return result


def comparison_spec(protocol: dict, split: str) -> dict | None:
    """Validate a self-contained profile before solver work or dataset loading."""
    if "comparison_profile" not in protocol:
        return None
    record = protocol["comparison_profile"]
    if not isinstance(record, dict) or set(record) != {
            "definition", "definition_sha256", "file_sha256", "stage"}:
        raise ValueError("invalid embedded comparison profile")
    definition = checked_definition(record["definition"])
    if (split not in SPLITS or record["stage"] != split
            or not _digest(record["file_sha256"])
            or record["definition_sha256"] != definition_sha256(definition)):
        raise ValueError("comparison profile stage or digest mismatch")
    baselines = definition["baseline_sets"][split]
    if protocol.get("extra_baselines") != [m for m in baselines if m not in REQUIRED]:
        raise ValueError("extra_baselines disagree with the frozen comparison profile")
    return {"profile_id": definition["profile_id"], "stage": split,
            "definition_sha256": record["definition_sha256"],
            "file_sha256": record["file_sha256"], "baselines": list(baselines),
            "assessment_baselines": list(definition["baseline_sets"]["test"]),
            "fitness": definition["fitness"], "assessment_rule": definition["assessment_rule"]}


def evaluation_methods(protocol: dict, split: str, baselines_only: bool = False) -> list[str]:
    spec = comparison_spec(protocol, split)
    if spec is not None:
        return spec["baselines"] + ([] if baselines_only else ["candidate"])
    # Historical M2/M3 ordering and opt-in extras are intentionally unchanged.
    methods = ["random", "topk", "greedy", "greedy_swap"] if baselines_only else ["greedy", "greedy_swap", "candidate"]
    extras = protocol.get("extra_baselines", [])
    if (not isinstance(extras, list)
            or any(not isinstance(m, str) or m not in ("random", "topk", *METHODS) for m in extras)
            or len(set(extras)) != len(extras)):
        raise ValueError("extra_baselines must be unique registered fixed controls")
    return list(dict.fromkeys([*methods, *extras]))


def comparison_plan(protocol: dict, split: str, cases: int) -> dict | None:
    spec = comparison_spec(protocol, split)
    if spec is None:
        return None
    return {**spec, "paired_cases_per_program": cases,
            "fixed_control_trials_per_program": cases * len(spec["baselines"]),
            "candidate_trials_per_program": cases,
            "total_solver_trials_per_program": cases * (len(spec["baselines"]) + 1),
            "cost_scope": "Trial counts, not predicted runtime, model cost or completed work"}


def _avg(values: list[float]) -> float:
    return fsum(values) / len(values)


def paired_comparisons(records: list[dict], selected: str, spec: dict) -> dict:
    """Compare each fixed method separately on the same cases and checkpoints.

    Failed comparisons are explicitly invalid; successful subsets are not used
    to hide failed trials. Values are descriptive, not significance estimates.
    """
    if not records:
        raise ValueError("comparison requires recorded paired cases")
    expected = set(spec["baselines"]) | {selected}
    for row in records:
        if set(row["methods"]) != expected:
            raise ValueError("recorded methods do not match the comparison profile")
    checkpoints = records[0]["methods"][selected]["checkpoints_seconds"]
    groups = [("overall", None, None, records)]
    for dataset in sorted({r["dataset"] for r in records}):
        source = [r for r in records if r["dataset"] == dataset]
        groups.append(("source", dataset, None, source))
        for k in sorted({r["k"] for r in source}):
            groups.append(("source_budget", dataset, k, [r for r in source if r["k"] == k]))
    rows = []
    for scope, dataset, k, group in groups:
        for method in spec["baselines"]:
            candidates = [r["methods"][selected] for r in group]
            controls = [r["methods"][method] for r in group]
            for result in candidates + controls:
                if (result["checkpoints_seconds"] != checkpoints
                        or len(result["coverage_at_checkpoints"]) != len(checkpoints)):
                    raise ValueError("unpaired checkpoint grids")
                if any(not isinstance(x, (int, float)) or not isfinite(x) for x in
                       [result["mean_checkpoint_coverage"], result["final_coverage"],
                        *result["coverage_at_checkpoints"]]):
                    raise ValueError("nonfinite comparison coverage")
            failed = sum(not a["correct"] or not b["correct"] for a, b in zip(candidates, controls))
            row = {"scope": scope, "dataset": dataset, "k": k, "baseline": method,
                   "paired_cases": len(group), "failed_pairs": failed, "valid": failed == 0}
            if not failed:
                row.update(
                    baseline_mean_checkpoint_coverage_pct=100 * _avg([b["mean_checkpoint_coverage"] for b in controls]),
                    baseline_mean_final_coverage_pct=100 * _avg([b["final_coverage"] for b in controls]),
                    delta_mean_checkpoint_pp=100 * _avg([a["mean_checkpoint_coverage"] - b["mean_checkpoint_coverage"] for a, b in zip(candidates, controls)]),
                    delta_final_pp=100 * _avg([a["final_coverage"] - b["final_coverage"] for a, b in zip(candidates, controls)]),
                    delta_at_checkpoints_pp=[100 * _avg([a["coverage_at_checkpoints"][j] - b["coverage_at_checkpoints"][j] for a, b in zip(candidates, controls)]) for j in range(len(checkpoints))])
            rows.append(row)
    return {"schema_version": 1, **spec, "selected_method": selected,
            "checkpoints_seconds": checkpoints,
            "evaluation_valid": all(r["valid"] for r in rows), "rows": rows,
            "interpretation": "Paired descriptive differences, not statistical significance, an oracle portfolio, or proof of evolutionary discovery. Positive fitness versus greedy alone is insufficient."}


def comparison_feedback(comparisons: dict) -> str:
    details = []
    for row in comparisons["rows"]:
        if row["scope"] == "source":
            continue
        label = "overall" if row["scope"] == "overall" else f"{row['dataset']} k={row['k']}"
        if row["valid"]:
            values = f"checkpoints {row['delta_mean_checkpoint_pp']:+.4f} pp, final {row['delta_final_pp']:+.4f} pp"
        else:
            values = f"INVALID ({row['failed_pairs']} failed paired cases)"
        details.append(f"{label} vs {row['baseline']}: {values}")
    missing = sorted(set(comparisons["assessment_baselines"]) - set(comparisons["baselines"]))
    return (f" Comparison profile {comparisons['profile_id']}, stage={comparisons['stage']}. "
            "Compare early availability separately from final optimization quality. "
            "The scalar fitness is unchanged; these comparisons are evidence, not extra rewards. "
            "Beating greedy alone does not establish superiority over strong controls. "
            + (f"Assessment controls not executed in this screening evaluation: {', '.join(missing)}. " if missing else "")
            + "; ".join(details))


def verify_comparison_evidence(metrics: dict, suite_path: str | Path, split: str) -> None:
    """Reject stale cached validation/test evidence with missing or wrong controls."""
    protocol = json.loads(Path(suite_path).read_text())
    spec = comparison_spec(protocol, split)
    if spec is None:
        return
    comparison = metrics.get("extra_data", {}).get("comparisons", {})
    if any(comparison.get(key) != value for key, value in spec.items()):
        raise ValueError("comparison evidence identity mismatch")
    expected = set(spec["baselines"])
    overall = [row for row in comparison.get("rows", []) if row.get("scope") == "overall"]
    if len(overall) != len(expected) or {r.get("baseline") for r in overall} != expected:
        raise ValueError("missing fixed-control comparison evidence")
    if metrics.get("public", {}).get("failed_cases") == 0 and (
            comparison.get("evaluation_valid") is not True or any(r.get("valid") is not True for r in overall)):
        raise ValueError("inconsistent comparator correctness evidence")

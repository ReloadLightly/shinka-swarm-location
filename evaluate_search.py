"""Chapter-search-v2: candidate-only evaluation against immutable offline controls.

Normalized anytime deployment quality and independently certified quality are
reported separately. Their declared weighted mean is this project's evolutionary
objective, not an equation from the book. Real elapsed time is retained because
arbitrary new kernels/raw-DAG algorithms cannot honestly be priced by API calls.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from math import fsum, isfinite
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

from evaluate_anytime import write_json
from swarm_location.anytime import run_anytime, TRUSTED
from swarm_location.core import ShortestPathCoverage
from swarm_location.dag_bounds import IntervalOracle, SCALE
from swarm_location.relabel import relabel
from swarm_location.suite import load_suite, file_sha256

ROOT = Path(__file__).resolve().parent


def mean(values):
    values = list(values)
    return fsum(values) / len(values)


def family_mean(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row["source_graph"]].append(row[key])
    return mean(mean(values) for values in groups.values())


def validate(protocol):
    if protocol.get("research_protocol") != "chapter-search-v2":
        raise ValueError("requires an explicit chapter-search-v2 suite, not a historical timing suite")
    weights = protocol["fitness"]
    values = [weights["coverage_weight"], weights["certificate_weight"]]
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v) or v < 0 for v in values) or abs(sum(values)-1) > 1e-12:
        raise ValueError("fitness weights must be nonnegative and sum to one")
    controls = protocol["controls"]
    if not controls or len(controls) != len(set(controls)) or any(not isinstance(v, str) for v in controls):
        raise ValueError("nonempty distinct controls required")
    if type(protocol.get("relabel_seed")) is not int:
        raise ValueError("integer relabel seed required")
    return values


def control_path(method):
    path = (ROOT / method.removeprefix("program:")).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("control program must be an existing repository file")
    return path


def identity(suite_path, protocol, split):
    files = [Path(__file__), ROOT / 'swarm_location/relabel.py', ROOT / 'swarm_location/isolation.py',
             ROOT / 'swarm_location/anytime.py', ROOT / 'swarm_location/baseline_proofs.py',
             ROOT / 'swarm_location/certificates.py', ROOT / 'swarm_location/certificate_references.py',
             *(ROOT / 'swarm_location' / name for name in TRUSTED)]
    files += [control_path(m) for m in protocol["controls"] if m.startswith("program:")]
    cpu = ''
    if Path('/proc/cpuinfo').exists():
        cpu = next((l.split(':', 1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')), '')
    return {"suite_sha256": file_sha256(suite_path), "split": split,
            "source_sha256": {str(p.relative_to(ROOT)): file_sha256(p) for p in sorted(set(files))},
            "python": platform.python_version(), "platform": platform.platform(), "cpu": cpu,
            "docker_image": os.environ.get('SWARM_DOCKER_IMAGE'),
            "worker_memory_mib": os.environ.get('SWARM_WORKER_MEMORY_MIB', '768')}


def case_seed(protocol, entry, seed):
    text = f"{protocol['relabel_seed']}:{entry['id']}:{seed}".encode()
    return int.from_bytes(hashlib.sha256(text).digest()[:8], 'big')


def key(dataset, k, seed):
    return json.dumps([dataset, k, seed], separators=(',', ':'))


def certificate_curve(instance, k, trace, oracle):
    interval = IntervalOracle(instance, oracle)
    cached = {(): Fraction(0)}
    curve = []
    for time in trace["checkpoints_seconds"]:
        improvements = [e for e in trace["improvements"] if e["received_seconds"] <= time]
        best = max(improvements, key=lambda e: e["coverage"])
        selected = tuple(best["selected"])
        if selected not in cached:
            lower, _, _ = interval.intervals(selected)
            cached[selected] = Fraction(lower, SCALE)
        bounds = [Fraction(e["upper_exact"]) for e in trace.get("verified_search_bounds", []) if e["received_seconds"] <= time]
        upper = min([Fraction(1 if k else 0), *bounds])
        lower = cached[selected]
        if lower > upper:
            raise ValueError("verified lower bound exceeds verified upper bound")
        curve.append(float(lower / upper) if upper else 1.)
    return curve


def run(instance, k, seed, protocol, oracle, *, method=None, program=None):
    if method is not None and method.startswith("program:"):
        program, method = control_path(method), None
    trace = run_anytime(instance, k, protocol["checkpoints_seconds"], program_path=program,
                        baseline=method, seed=seed, oracle=oracle,
                        setup_timeout=protocol.get("setup_timeout_seconds", 1800),
                        max_messages=protocol.get("max_report_messages", 4096),
                        max_output_bytes=protocol.get("max_report_bytes", 4_000_000),
                        allow_candidate_bounds=True)
    trace["certificate_at_checkpoints"] = certificate_curve(instance, k, trace, oracle)
    trace["mean_certificate"] = mean(trace["certificate_at_checkpoints"])
    return trace


def build_references(suite_path, references_path, split="development"):
    protocol, instances = load_suite(suite_path, split)
    validate(protocol)
    stamp = identity(suite_path, protocol, split)
    path = Path(references_path)
    if path.exists():
        raise ValueError("reference cache exists; use a NEW path to intentionally rebuild")
    cases = {}
    for entry, original in instances:
        for seed in protocol["seeds"]:
            instance, _ = relabel(original, case_seed(protocol, entry, seed))
            oracle = ShortestPathCoverage(instance)
            for k in entry["budgets"]:
                controls = {}
                for method in protocol["controls"]:
                    result = run(instance, k, seed, protocol, oracle, method=method)
                    if not result["correct"]:
                        raise RuntimeError(f"{entry['id']} k={k} {method}: {result['error']}")
                    controls[method] = result
                normalizer = max(t["final_coverage"] for t in controls.values())
                if k and normalizer <= 0:
                    raise ValueError("no positive feasible normalizer; increase reference search effort")
                cases[key(entry['id'], k, seed)] = {"dataset": entry['id'], "source_graph": entry['source_graph'],
                    "k": k, "seed": seed, "best_known_feasible": normalizer, "controls": controls}
                write_json(path.with_suffix('.partial.json'), {"complete": False, "identity": stamp, "cases": cases})
                print(f"references {entry['id']} k={k} seed={seed}: best feasible={normalizer:.8f}", flush=True)
    if identity(suite_path, protocol, split) != stamp:
        raise RuntimeError("reference implementation changed during construction")
    cache = {"complete": True, "identity": stamp, "cases": cases,
             "normalizer_kind": "best final feasible fixed-control coverage; NOT an optimum or upper bound"}
    write_json(path, cache)
    path.with_suffix('.partial.json').unlink(missing_ok=True)
    return cache


def evaluate(program_path, results_dir, suite_path, references_path, split="development"):
    output = Path(results_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'correct.json', {"correct": False, "error": "evaluation incomplete"})
    write_json(output/'metrics.json', {"combined_score": 0., "text_feedback": "evaluation incomplete"})
    (output/'traces.json').unlink(missing_ok=True)
    started = perf_counter()
    try:
        protocol, instances = load_suite(suite_path, split)
        weights = validate(protocol)
        stamp = identity(suite_path, protocol, split)
        cache_hash = file_sha256(references_path)
        cache = json.loads(Path(references_path).read_text())
        if cache.get("complete") is not True or cache.get("identity") != stamp:
            raise ValueError("reference cache mismatch: suite, code, split or execution environment changed; rebuild once, not per candidate")
        candidate_hash = file_sha256(program_path)
        records = []
        feedback = []
        for entry, original in instances:
            for seed in protocol["seeds"]:
                instance, _ = relabel(original, case_seed(protocol, entry, seed))
                oracle = ShortestPathCoverage(instance)
                for k in entry["budgets"]:
                    reference = cache["cases"][key(entry['id'], k, seed)]
                    trace = run(instance, k, seed, protocol, oracle, program=Path(program_path).resolve())
                    if not trace["correct"]:
                        write_json(output/'traces.json', {"cases": records, "failed_case": trace})
                        raise RuntimeError(trace["error"])
                    normalizer = reference["best_known_feasible"]
                    quality = trace["mean_checkpoint_coverage"] / normalizer if normalizer else 1.
                    certificate = trace["mean_certificate"]
                    row = {"dataset": entry['id'], "source_graph": entry['source_graph'], "k": k, "seed": seed,
                           "normalized_quality": quality, "mean_certificate": certificate,
                           "joint_quality": weights[0]*quality + weights[1]*certificate,
                           "best_known_feasible": normalizer,
                           "normalizer_exceeded": trace["final_coverage"] > normalizer + 1e-12,
                           "final_coverage": trace["final_coverage"], "trace": trace,
                           "fixed_control_comparisons": {}}
                    for name, control in reference["controls"].items():
                        control_quality = control["mean_checkpoint_coverage"] / normalizer if normalizer else 1.
                        control_joint = weights[0]*control_quality + weights[1]*control["mean_certificate"]
                        row["fixed_control_comparisons"][name] = {
                            "delta_checkpoint_coverage_pp": 100*(trace["mean_checkpoint_coverage"]-control["mean_checkpoint_coverage"]),
                            "delta_final_coverage_pp": 100*(trace["final_coverage"]-control["final_coverage"]),
                            "delta_certificate_pp": 100*(certificate-control["mean_certificate"]),
                            "delta_joint_score": 100*(row["joint_quality"]-control_joint)}
                    records.append(row)
                    write_json(output/'traces.json', {"complete": False, "cases": records})
                    feedback.append(f"{entry['id']} k={k} seed={seed}: quality={quality:.4f}, certificate={certificate:.4f}, final={100*trace['final_coverage']:.4f}%")
        if (file_sha256(program_path) != candidate_hash or file_sha256(references_path) != cache_hash or
                identity(suite_path, protocol, split) != stamp):
            raise RuntimeError("candidate, cache or implementation changed during evaluation")
        controls = {}
        for name in protocol["controls"]:
            for row in records:
                row['_delta'] = row['fixed_control_comparisons'][name]['delta_joint_score']
            controls[name] = family_mean(records, '_delta')
        for row in records:
            row.pop('_delta', None)
        metrics = {"combined_score": 100*family_mean(records, 'joint_quality'),
            "public": {"stage": "chapter_search_v2", "split": split, "cases": len(records),
                       "source_families": len({r['source_graph'] for r in records}),
                       "normalized_anytime_quality": family_mean(records, 'normalized_quality'),
                       "mean_certified_quality": family_mean(records, 'mean_certificate'),
                       "solver_runs_this_evaluation": len(records), "fixed_control_runs_this_evaluation": 0,
                       "delta_joint_score_vs_each_control": controls},
            "private": {"candidate_sha256": candidate_hash, "reference_sha256": cache_hash,
                        "identity": stamp, "fitness_weights": protocol['fitness'],
                        "wall_seconds": perf_counter()-started},
            "extra_data": {"per_case": [{k:v for k,v in r.items() if k != 'trace'} for r in records]},
            "text_feedback": "Two separate outcomes: deployment quality and verified certificate quality. "
                             "Current best-known normalizers are feasible controls, not optima. "
                             "Wall-clock fitness remains noisy; compare final coverage separately. " + '; '.join(feedback)}
        write_json(output/'traces.json', {"complete": True, "cases": records})
        write_json(output/'metrics.json', metrics)
        write_json(output/'correct.json', {"correct": True, "error": ""})
        return metrics
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        metrics = {"combined_score": 0., "public": {}, "private": {}, "extra_data": {}, "text_feedback": error}
        write_json(output/'metrics.json', metrics)
        write_json(output/'correct.json', {"correct": False, "error": error})
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite', type=Path, default=ROOT/'data/search/suite.json')
    p.add_argument('--references', type=Path)
    p.add_argument('--split', choices=['development', 'validation', 'test'], default='development')
    p.add_argument('--build-references', action='store_true')
    p.add_argument('--program_path', type=Path, default=ROOT/'search_initial.py')
    p.add_argument('--results_dir', type=Path, default=ROOT/'results/local_search')
    a = p.parse_args()
    references = a.references or a.suite.parent/'references.json'
    result = (build_references(a.suite, references, a.split) if a.build_references else
              evaluate(a.program_path, a.results_dir, a.suite, references, a.split))
    print(json.dumps({k:v for k,v in result.items() if k in ('combined_score', 'public', 'complete')}, indent=2))

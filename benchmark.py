"""Reproducible step-1 baseline comparison, not an evolutionary experiment."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from math import comb
from pathlib import Path
import platform
from statistics import mean, stdev
from time import perf_counter

from swarm_location import Instance, ShortestPathCoverage
from swarm_location.baselines import greedy, topk_bc, greedy_swap, random_deployment, exhaustive

ROOT = Path(__file__).resolve().parent


def run(instance_path: Path, output: Path, max_k: int = 8, random_runs: int = 100,
        exact_max_k: int = 4) -> dict:
    instance = Instance.load(instance_path)
    instance.validate_budget(max_k)
    if max_k < 1 or random_runs < 2 or exact_max_k < 0:
        raise ValueError("require max_k>=1, random_runs>=2, exact_max_k>=0")
    start = perf_counter()
    reference = ShortestPathCoverage(instance)
    fast = reference.compile_routes()
    preprocessing = perf_counter() - start
    rows, observations = [], []
    for k in range(1, max_k + 1):
        row = {"k": k}
        for name, solver in [("individual_bc", topk_bc), ("greedy_gbc", greedy),
                             ("greedy_swap", greedy_swap)]:
            start = perf_counter()
            locations = solver(fast, k)
            seconds = perf_counter() - start
            coverage = reference.score(locations)
            if abs(coverage - fast.score(locations)) > 1e-12:
                raise AssertionError("DAG and route backends disagree")
            row[name] = {"coverage": coverage, "locations": sorted(locations),
                         "solver_seconds": seconds}
        random_scores = []
        for seed in range(random_runs):
            locations = random_deployment(fast, k, seed)
            value = reference.score(locations)
            random_scores.append(value)
            observations.append({"k": k, "seed": seed, "locations": sorted(locations),
                                 "coverage": value})
        row["random"] = {"mean": mean(random_scores), "sample_sd": stdev(random_scores),
                         "min": min(random_scores), "max": max(random_scores), "n": random_runs}
        row["exact"] = None
        if k <= exact_max_k:
            start = perf_counter()
            locations = exhaustive(fast, k)
            row["exact"] = {"coverage": reference.score(locations), "locations": locations,
                            "solver_seconds": perf_counter() - start,
                            "groups_examined": comb(len(instance.nodes), k)}
        rows.append(row)
        print(f"k={k}: greedy={100 * row['greedy_gbc']['coverage']:.4f}%, "
              f"swap={100 * row['greedy_swap']['coverage']:.4f}%", flush=True)
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [ROOT / 'benchmark.py', ROOT / 'swarm_location/core.py',
                        ROOT / 'swarm_location/baselines.py']}
    result = {"stage": "step1_reference_baselines", "created_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.system(),
              "instance": instance.name, "instance_sha256": hashlib.sha256(instance_path.read_bytes()).hexdigest(),
              "source_sha256": hashes, "nodes": len(instance.nodes), "directed_edges": len(instance.edges),
              "positive_od_pairs": len([q for _, _, q in instance.od if q > 0]),
              "total_demand": reference.total_demand, "exact_shortest_routes": fast.num_routes,
              "distinct_route_masks": len(fast.routes), "preprocessing_seconds": preprocessing,
              "timing_note": "One descriptive timing per deterministic solver; shared preprocessing excluded and reported separately. Not a matched-time or anytime comparison.",
              "random_seeds": [0, random_runs - 1], "evolved_generations": 0,
              "llm_calls": 0, "rows": rows}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'baselines.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    (output / 'random_coverages.json').write_text(json.dumps({
        'seeds': list(range(random_runs)), 'by_k': {str(k): [x['coverage'] for x in observations if x['k'] == k]
        for k in range(1, max_k + 1)}}, separators=(',', ':')) + '\n')
    lines = ["| Monitors | Random mean +/- SD (%) | Individual BC (%) | Greedy GBC (%) | Greedy + swap (%) | Exact optimum (%) |",
             "|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        exact = f"{100 * r['exact']['coverage']:.4f}" if r['exact'] else 'Not computed'
        lines.append(f"| {r['k']} | {100 * r['random']['mean']:.4f} +/- {100 * r['random']['sample_sd']:.4f} | "
                     f"{100 * r['individual_bc']['coverage']:.4f} | {100 * r['greedy_gbc']['coverage']:.4f} | "
                     f"{100 * r['greedy_swap']['coverage']:.4f} | {exact} |")
    (output / 'table.md').write_text('\n'.join(lines) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance', type=Path, default=ROOT / 'data/sioux_falls.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/local_baselines')
    parser.add_argument('--max-k', type=int, default=8)
    parser.add_argument('--random-runs', type=int, default=100)
    parser.add_argument('--exact-max-k', type=int, default=4)
    args = parser.parse_args()
    run(args.instance, args.output, args.max_k, args.random_runs, args.exact_max_k)

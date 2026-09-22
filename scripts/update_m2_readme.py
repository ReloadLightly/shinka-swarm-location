"""Refresh only the evidence-backed M2 table; historical M1 results stay intact."""
import argparse
import json
from pathlib import Path
import re
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
START, END = '<!-- M2-RESULTS:START -->', '<!-- M2-RESULTS:END -->'


def render(evidence):
    evidence = Path(evidence)
    metrics = json.loads((evidence/'baselines/metrics.json').read_text())
    correctness = json.loads((evidence/'baselines/correct.json').read_text())
    native = json.loads((evidence/'native/native_seed_check.json').read_text())
    native_config = json.loads((evidence/'native/native_config_check.json').read_text())
    backend = json.loads((evidence/'marginals.json').read_text())
    tests = (evidence/'tests.txt').read_text()
    if not correctness['correct'] or not native['correct'] or not native_config['configuration_constructed']:
        raise ValueError('cannot report successful M2 from failed evidence')
    counts = re.findall(r'Ran (\d+) tests? in', tests)
    if not counts or not re.search(r'^OK\s*$', tests, re.M):
        raise ValueError('missing successful test transcript')
    rows = metrics['extra_data']['summary']
    table = ['| Development dataset | Method | Mean checkpoint coverage (%) | Mean final coverage (%) |',
             '|---|---|---:|---:|']
    for row in rows:
        table.append(f"| {row['dataset']} | {row['method']} | {row['mean_checkpoint_coverage_pct']:.4f} | {row['mean_final_coverage_pct']:.4f} |")
    table.extend(['', '| Dataset | Reference gain pass (median ms) | Reverse-dependency pass (median ms) | Speed ratio | Max. absolute difference |',
                  '|---|---:|---:|---:|---:|'])
    for row in backend['measurements']:
        table.append(f"| {row['dataset']} | {1000*median(row['reference_seconds']):.4f} | {1000*median(row['reverse_dependency_seconds']):.4f} | {row['median_speed_ratio']:.2f}x | {row['max_abs_disagreement']:.3g} |")
    relative = evidence.resolve().relative_to(ROOT).as_posix()
    table.extend(['', f"**Executed evidence:** {counts[-1]} tests passed; {metrics['public']['paired_cases']} paired cases; "
        f"{metrics['public']['source_datasets']} development source networks; zero failed baseline trials. "
        f"Native seed correctness: `{native['correct']}`; native score: `{native['combined_score']:.6f}`. "
        'The native score includes a +100 affine offset; its checkpoint difference can vary with timing.',
        '', f"[Protocol and raw baseline trajectories]({relative}/baselines/traces.json), "
        f"[baseline metrics]({relative}/baselines/metrics.json), "
        f"[native integration record]({relative}/native/native_seed_check.json), "
        f"[native seed metrics]({relative}/native/seed/metrics.json), "
        f"[gain-pass timings]({relative}/marginals.json), and [tests]({relative}/tests.txt).",
        '', 'These are fixed-baseline and reviewed-seed calculations, not evolved results. '
        'The gain-pass comparison uses three alternating-order measurements at the empty selection; '
        'its speed ratio is not an end-to-end algorithm speedup. The tables average budgets and seeds '
        'within each dataset and do not establish cross-network confidence intervals.'])
    return '\n\n' + '\n'.join(table) + '\n\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT/'results/step2/ci')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT/'README.md'
    text = path.read_text()
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('README must contain one M2 marker pair')
    before, rest = text.split(START)
    _, after = rest.split(END)
    updated = before + START + render(args.evidence) + END + after
    if args.check:
        if updated != text:
            raise SystemExit('M2 README table is stale')
    else:
        path.write_text(updated)


if __name__ == '__main__':
    main()

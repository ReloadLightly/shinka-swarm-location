"""Compare identical exact-route marginal calculations, not evolved algorithms."""
import argparse
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_anytime import write_json
from swarm_location.core import ShortestPathCoverage
from swarm_location.search import SearchProblem
from swarm_location.suite import load_suite, file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT/'data/commissioning/suite.json')
    parser.add_argument('--output', type=Path, default=ROOT/'results/step2/marginals.json')
    args = parser.parse_args()
    _, instances = load_suite(args.suite)
    rows = []
    for entry, instance in instances:
        started = perf_counter()
        problem = SearchProblem(instance)
        preprocessing = perf_counter()-started
        naive, fast, errors = [], [], []
        for repeat in range(3):
            timings, values = {}, {}
            order = ['reference','reverse_dependency'] if repeat % 2 == 0 else ['reverse_dependency','reference']
            for method in order:
                start = perf_counter()
                values[method] = (ShortestPathCoverage.marginal_gains(problem, []) if method == 'reference'
                                  else problem.marginal_gains([]))
                timings[method] = perf_counter()-start
            naive.append(timings['reference'])
            fast.append(timings['reverse_dependency'])
            errors.append(max(abs(values['reference'][v]-values['reverse_dependency'][v]) for v in problem.nodes))
        rows.append({'dataset':entry['id'],'nodes':len(instance.nodes),'edges':len(instance.edges),
            'dataset_sha256':entry['sha256'],'preprocessing_seconds':preprocessing,
            'reference_seconds':naive,'reverse_dependency_seconds':fast,
            'median_speed_ratio':median(naive)/median(fast),'max_abs_disagreement':max(errors)})
    write_json(args.output,{'scope':'Empty-selection marginal calculation, three alternating-order repeats; not evolution',
        'suite_sha256':file_sha256(args.suite),'search_code_sha256':file_sha256(ROOT/'swarm_location/search.py'),
        'measurements':rows})
    for row in rows:
        print(row)


if __name__ == '__main__':
    main()

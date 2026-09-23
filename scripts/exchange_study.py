"""Reproduce exact headroom and exchange geometry on a small development case.

Existing optimum proofs are independently reused, not relabeled new discoveries.
The new census, neutral component and minimal-loss path/cut are computed in full.
No solver is added to the campaign, and validation/test performance is unopened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.quality_study import verify_study, write
from swarm_location.anytime_baselines import solve
from swarm_location.certificates import ExactCoverage, MODEL
from swarm_location.exchange_landscape import (ExchangeProblem, exchange_census,
    neutral_component, minimum_loss_escape, verify_escape)
from swarm_location.search import SearchProblem
from swarm_location.suite import file_sha256, load_suite

SOURCES = ['scripts/exchange_study.py', 'swarm_location/exchange_landscape.py',
           'swarm_location/certificates.py', 'swarm_location/certificate_references.py',
           'swarm_location/core.py', 'swarm_location/search.py',
           'swarm_location/anytime_baselines.py', 'swarm_location/suite.py']
FROZEN = ['anytime_initial.py', 'initial.py', 'evaluate_anytime.py', 'evaluate.py',
          'run_evo.py', 'campaign.py', 'configs/evolution.json', 'configs/evolution_m3.json',
          'configs/m3_launch_request.json', 'configs/source_catalog_m3.json',
          'swarm_location/anytime.py', 'swarm_location/anytime_worker.py',
          'swarm_location/isolation.py', 'swarm_location/selection.py']


def compute(suite_path: Path, references: Path, dataset: str, k: int) -> dict:
    suite, data = load_suite(suite_path, 'development')
    candidates = [(entry, inst) for entry, inst in data if entry['id'] == dataset]
    if len(candidates) != 1:
        raise ValueError('request must identify exactly one development dataset')
    entry, instance = candidates[0]
    if len(instance.nodes) > 32:
        raise ValueError('this exhaustive diagnostic is restricted to small development graphs')
    old = json.loads((references/'study.json').read_text())
    prior_verification = verify_study(suite_path, references)
    headroom = []
    relevant = [c for c in old['cases'] if c['dataset'] == dataset]
    for row in relevant:
        optimum = row['reference_best']
        if not optimum['deployment_optimality_proved']:
            raise ValueError('exact headroom requires a proved optimal reference deployment')
        best = Fraction(optimum['coverage_exact'])
        g = Fraction(row['methods']['greedy']['certificate']['coverage_exact'])
        s = Fraction(row['methods']['greedy_swap']['certificate']['coverage_exact'])
        headroom.append({'k': row['k'], 'greedy_exact': str(g), 'greedy_swap_exact': str(s),
                         'optimum_exact': str(best), 'swap_gap_exact': str(best-s),
                         'in_campaign_budget_list': row['in_campaign_budget_list'],
                         'reference_file': row['reference_file'],
                         'reference_sha256': row['reference_sha256']})
    current = [c for c in relevant if c['k'] == k]
    if len(current) != 1:
        raise ValueError('diagnostic budget must have exactly one verified reference case')
    current = current[0]
    # Reproduce the published completed baseline without the two-second campaign
    # truncation. The returned deployment must match the preserved reference.
    selected = solve(SearchProblem(instance), k, 0, lambda s: None, 3600.0, 'greedy_swap')
    oracle = ExactCoverage(instance)
    selected = list(oracle.instance.validate_selection(selected, k))
    expected = current['methods']['greedy_swap']['certificate']['selected']
    if selected != expected:
        raise ValueError('completed baseline differs from the preserved starting deployment')
    problem = ExchangeProblem(oracle, k)
    census = exchange_census(problem, selected)
    if Fraction(census['global_optimum_units'], problem.scale) != Fraction(current['reference_best']['coverage_exact']):
        raise ArithmeticError('full census disagrees with the existing independently verified optimum proof')
    plateau = neutral_component(problem, selected)
    if not plateau['complete']:
        raise RuntimeError('neutral component incomplete; do not publish a no-escape conclusion')
    # Include exits after a neutral move at larger simultaneous radii as well.
    # These component spheres are additional diagnostics, not unique global states.
    member_radii = []
    for member in plateau['members']:
        best_by_radius = []
        for radius in range(1, min(3, k, len(problem.nodes)-k)+1):
            values = [problem.units(g) for g in problem.neighbors(member, radius)]
            best_by_radius.append({'radius': radius, 'evaluated': len(values),
                'strictly_better_than_initial': sum(v > census['initial_units'] for v in values),
                'best_units': max(values)})
        member_radii.append({'selected': member, 'spheres': best_by_radius})
    barrier = minimum_loss_escape(problem, selected)
    if census['strict_improving_deployments'] and barrier['status'] != 'proved':
        raise RuntimeError('loss-barrier diagnostic incomplete; preserve failure without inventing proof')
    # Check every scientifically reported witness with the independent avoiding-DAG
    # rational scorer, not only the route-union engine used by the enumeration.
    groups = {tuple(selected), *(tuple(r['best_selected']) for r in census['spheres']),
              *(tuple(g) for g in census['global_optimum_examples']),
              *(tuple(g) for g in plateau['members'])}
    for row in census['spheres']:
        groups.update(tuple(g) for group_list in row['examples'].values() for g in group_list)
    if barrier['proof']:
        verify_escape(problem, barrier['proof'])
        groups.update(tuple(g) for g in barrier['proof']['path'])
        groups.update(tuple(g) for g in barrier['proof']['strict_superlevel_cut'])
    disagreement = 0.0
    for group in sorted(groups):
        value = problem.coverage(group)
        if value != oracle.score(group):
            raise ArithmeticError('route-union witness disagrees with exact avoiding-DAG score')
        disagreement = max(disagreement, abs(float(value)-oracle.oracle.score(group)))
    return {'schema_version': 1, 'model': MODEL, 'dataset': dataset,
            'source_graph': entry['source_graph'], 'split': 'development',
            'dataset_sha256': entry['sha256'], 'suite_sha256': file_sha256(suite_path),
            'instance_sha256': oracle.identity, 'k': k,
            'prior_study_sha256': file_sha256(references/'study.json'),
            'headroom_source': 'independently reverified existing reference study; not new BnB runs',
            'prior_reference_verification': prior_verification, 'headroom': headroom,
            'fresh_completed_baseline_matches_saved_reference': True,
            'census': census, 'neutral_component': plateau,
            'neutral_member_radius_checks': member_radii, 'minimum_loss_escape': barrier,
            'witnesses_checked_against_independent_exact_dag': len(groups),
            'max_abs_difference_from_production_scorer': disagreement,
            'model_calls': 0, 'evolved_descendants': 0, 'validation_test_evaluations': 0,
            'evaluator_or_fitness_modified': False,
            'scope': 'Exact offline development-case landscape; no anytime speedup or evolutionary claim'}


def run(suite_path: Path, references: Path, output: Path, *, dataset='SiouxFalls', k=6) -> dict:
    suite_path, references, output = [Path(p).resolve() for p in (suite_path, references, output)]
    if output.exists():
        raise FileExistsError('preserve previous evidence; choose a new output directory')
    before = {p: file_sha256(ROOT/p) for p in [*SOURCES, *FROZEN]}
    output.mkdir(parents=True)
    started = perf_counter()
    write(output/'status.json', {'status': 'incomplete', 'model_calls': 0,
                                'validation_test_evaluations': 0})
    science = compute(suite_path, references, dataset, k)
    if any(file_sha256(ROOT/p) != digest for p, digest in before.items()):
        raise RuntimeError('source or frozen campaign files changed during the study')
    record = {'science': science, 'execution': {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
        'platform': platform.platform(), 'source_sha256': {p: before[p] for p in SOURCES},
        'frozen_inputs_sha256': {p: before[p] for p in FROZEN},
        'wall_seconds_including_reference_verification_and_preparation': perf_counter()-started,
        'timing_scope': 'entire offline diagnostic, NOT a campaign quality-runtime comparison'}}
    write(output/'study.json', record)
    write(output/'status.json', {'status': 'complete', 'study_sha256': file_sha256(output/'study.json'),
                                'model_calls': 0, 'validation_test_evaluations': 0})
    return record


def verify(suite_path: Path, references: Path, output: Path) -> dict:
    suite_path, references, output = [Path(p).resolve() for p in (suite_path, references, output)]
    record = json.loads((output/'study.json').read_text()); science = record['science']
    status = json.loads((output/'status.json').read_text())
    if status['status'] != 'complete' or status['study_sha256'] != file_sha256(output/'study.json'):
        raise ValueError('incomplete or altered saved study')
    for group in ('source_sha256', 'frozen_inputs_sha256'):
        for path, digest in record['execution'][group].items():
            p = (ROOT/path).resolve()
            if not p.is_relative_to(ROOT) or file_sha256(p) != digest:
                raise ValueError('recorded implementation or campaign identity mismatch')
    recomputed = compute(suite_path, references, science['dataset'], science['k'])
    if recomputed != science:
        raise ValueError('scientific record does not exactly reproduce')
    report = {'success': True, 'study_sha256': file_sha256(output/'study.json'),
              'full_census_deployments_recomputed': science['census']['total_deployments'],
              'neutral_component_recomputed': science['neutral_component']['complete'],
              'escape_barrier_proof_verified': science['minimum_loss_escape']['status'] == 'proved',
              'independent_exact_dag_witnesses_checked': science['witnesses_checked_against_independent_exact_dag'],
              'prior_certificates_reverified': science['prior_reference_verification']['verified_certificates'],
              'prior_bound_witnesses_reverified': science['prior_reference_verification']['verified_bound_witnesses'],
              'model_calls': 0, 'evolved_descendants': 0, 'validation_test_evaluations': 0}
    write(output/'verification.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite', type=Path, default=ROOT/'data/commissioning/suite.json')
    p.add_argument('--references', type=Path, default=ROOT/'results/quality-certificates/reference-study')
    p.add_argument('--output', type=Path, default=ROOT/'results/local_exchange_study')
    p.add_argument('--dataset', default='SiouxFalls')
    p.add_argument('--k', type=int, default=6)
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    if not a.verify:
        run(a.suite, a.references, a.output, dataset=a.dataset, k=a.k)
    print(json.dumps(verify(a.suite, a.references, a.output), indent=2))


if __name__ == '__main__':
    main()

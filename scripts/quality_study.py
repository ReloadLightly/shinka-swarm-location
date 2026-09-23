"""Reproducible development-only reference bounds and baseline certificates.

Existing fixed algorithms are allowed to finish; these are not two-second solver
trials or evolutionary results. Supplied holdouts cannot be processed by this
study. --extended-small adds budgets 1..8 only to <=32-node development fixtures;
it never edits the campaign suite. SciPy is optional and needed only for --lp.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_location.anytime_baselines import solve
from swarm_location.certificates import ExactCoverage, MODEL, bound_witness, certificate, verify_bound
from swarm_location.certificate_references import branch_bound, lp_bound
from swarm_location.search import SearchProblem
from swarm_location.suite import file_sha256, load_suite


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def run(suite_path: Path, output: Path, *, exact_small: bool = False, lp: bool = False,
        extended_small: bool = False) -> dict:
    suite_path, output = map(lambda p: Path(p).resolve(), (suite_path, output))
    if output.exists():
        raise FileExistsError('reference study output exists; preserve it and use a new directory')
    suite, data = load_suite(suite_path, 'development')
    report = {'schema_version': 1, 'scope': 'Development-only completed fixed-baseline and offline bound study',
              'model': MODEL, 'suite_sha256': file_sha256(suite_path),
              'created_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
              'options': {'exact_small': exact_small, 'lp': lp, 'extended_small': extended_small},
              'model_calls': 0, 'evolved_descendants': 0, 'validation_test_evaluations': 0,
              'evaluator_or_fitness_modified': False,
              'source_sha256': {p: file_sha256(ROOT / p) for p in
                  ['scripts/quality_study.py','swarm_location/certificates.py','swarm_location/certificate_references.py',
                   'swarm_location/core.py','swarm_location/search.py','swarm_location/anytime_baselines.py']},
              'cases': []}
    output.mkdir(parents=True)
    write(output/'study_incomplete.json', report)
    for entry, instance in data:
        prepared = SearchProblem(instance)
        oracle = ExactCoverage(instance)
        budgets = sorted(set(entry['budgets']) | (set(range(1,min(8,len(instance.nodes))+1))
                         if extended_small and len(instance.nodes) <= 32 else set()))
        for k in budgets:
            print(f"{entry['id']} k={k}: fixed baselines", flush=True)
            methods, groups = {}, []
            for method in ['topk','greedy','greedy_swap']:
                started = perf_counter()
                selected = solve(prepared, k, 0, lambda s: None, 3600.0, method)
                oracle.instance.validate_selection(selected, k)
                groups.append(selected)
                methods[method] = {'selected': selected, 'wall_seconds': perf_counter()-started,
                    'timing_scope': 'completed fixed baseline; not a matched-time campaign trial'}
            witnesses = [bound_witness(oracle,k,groups)]
            failures = []
            if exact_small and len(oracle.nodes) <= 32:
                best = max(groups, key=oracle.score)
                proof = branch_bound(oracle,k,best)
                witnesses.append(proof)
                groups.append(proof['feasible_selected'])
            if lp and len(oracle.nodes) > 32:
                # A failed numerical proposal never becomes a scalar certificate.
                # Keep the already verified DAG bound and record the failure.
                try:
                    witnesses.append(lp_bound(oracle,k))
                except RuntimeError as exc:
                    failures.append({'method':'route_dual','status':'unavailable','reason':str(exc)})
            for witness in witnesses:
                verify_bound(oracle,k,witness)
            artifact = {'schema_version':1,'model':MODEL,'instance_sha256':oracle.identity,
                        'dataset':entry['id'],'dataset_sha256':entry['sha256'],'k':k,
                        'witnesses':witnesses,'feasible_references':groups}
            filename = f"{entry['id']}-k{k}.json"
            refpath = output/'references'/filename
            write(refpath,artifact)
            for values in methods.values():
                values['certificate'] = certificate(oracle,values['selected'],k,
                                                   witnesses=witnesses,feasible_references=groups)
            reference_best = max(groups,key=oracle.score)
            case = {'dataset':entry['id'],'source_graph':entry['source_graph'],'k':k,
                    'in_campaign_budget_list':k in entry['budgets'],'instance_sha256':oracle.identity,
                    'reference_file':f'references/{filename}','reference_sha256':file_sha256(refpath),
                    'methods':methods,'reference_best':certificate(oracle,reference_best,k,
                        witnesses=witnesses,feasible_references=groups),'unavailable_methods':failures}
            report['cases'].append(case)
            write(output/'study_incomplete.json',report)
            print('  swap quality >= '+methods['greedy_swap']['certificate']['quality_lower_bound_pct']+'%',flush=True)
    write(output/'study.json',report)
    (output/'study_incomplete.json').unlink()
    table = ['| Development network | Monitors | Completed swap coverage (%) | Verified optimum upper bound (%) | Quality guarantee (%) | Remaining gain at most (pp) |',
             '|---|---:|---:|---:|---:|---:|']
    from fractions import Fraction
    from swarm_location.certificates import decimal_bound
    for case in report['cases']:
        c = case['methods']['greedy_swap']['certificate']
        table.append(f"| {case['dataset']} | {case['k']} | {c['coverage_pct']:.6f} | "
                     f"{decimal_bound(100*Fraction(c['optimum_upper_bound_exact']),upper=True)} | "
                     f"{c['quality_lower_bound_pct']} | {c['remaining_gain_upper_pp']} |")
    (output/'table.md').write_text('\n'.join(table)+'\n')
    return report


def verify_study(suite_path: Path, directory: Path) -> dict:
    from certify import read_references
    from fractions import Fraction
    _, data = load_suite(suite_path,'development')
    oracles = {r['id']:ExactCoverage(i) for r,i in data}
    report = json.loads((directory/'study.json').read_text())
    if report['suite_sha256'] != file_sha256(suite_path):
        raise ValueError('study/suite identity mismatch')
    count, proof_count, max_float_error = 0, 0, 0.0
    for case in report['cases']:
        oracle = oracles[case['dataset']]
        ref = (directory/case['reference_file']).resolve()
        if not ref.is_relative_to(directory.resolve()) or file_sha256(ref) != case['reference_sha256']:
            raise ValueError('study reference hash mismatch')
        witnesses, feasible = read_references(ref,oracle,case['k'])
        proof_count += len(witnesses)
        for c in [*(v['certificate'] for v in case['methods'].values()),case['reference_best']]:
            recomputed = certificate(oracle,c['selected'],case['k'],witnesses=witnesses,feasible_references=feasible)
            if c != recomputed:
                raise ValueError('study certificate differs from recomputation')
            max_float_error = max(max_float_error,abs(float(Fraction(c['coverage_exact'])) - oracle.oracle.score(c['selected'])))
            count += 1
    return {'verified_certificates':count,'verified_bound_witnesses':proof_count,
            'development_cases':len(report['cases']),'max_abs_difference_from_production_scorer':max_float_error,
            'validation_test_evaluations':0,'model_calls':0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exact-small',action='store_true')
    p.add_argument('--extended-small',action='store_true')
    p.add_argument('--lp',action='store_true')
    p.add_argument('--verify',action='store_true')
    a = p.parse_args()
    if not a.verify:
        run(a.suite,a.output,exact_small=a.exact_small,lp=a.lp,extended_small=a.extended_small)
    print(json.dumps(verify_study(a.suite,a.output),indent=2))

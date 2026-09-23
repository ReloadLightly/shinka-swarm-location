"""Annotate completed anytime traces with posthoc quality certificates.

No candidate is executed, no timer changed, no fitness recalculated for selection.
Use the same hash-verified suite and separately verified reference witnesses.
Writes a new sidecar only. Default split is development; no holdout is opened
unless explicitly selected and a completed, matching trace already exists.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
from time import perf_counter

from swarm_location.anytime import score_trace
from swarm_location.certificates import ExactCoverage, MODEL, certificate, verify_bound
from swarm_location.suite import file_sha256, load_suite


def read_references(path: Path, oracle: ExactCoverage, k: int) -> tuple[list[dict], list[list[int]]]:
    data = json.loads(path.read_text())
    if (data.get('schema_version') != 1 or data.get('model') != MODEL
            or data.get('instance_sha256') != oracle.identity
            or type(data.get('k')) is not int or data['k'] != k):
        raise ValueError('reference artifact model/instance/budget mismatch')
    for witness in data['witnesses']:
        verify_bound(oracle, k, witness)
    for selected in data['feasible_references']:
        oracle.instance.validate_selection(selected, k)
    return data['witnesses'], data['feasible_references']


def annotate(suite_path: Path, traces_path: Path, output: Path, reference_dir: Path | None = None,
             split: str = 'development') -> dict:
    suite_path, traces_path, output = map(lambda p: Path(p).resolve(), (suite_path, traces_path, output))
    if output.exists():
        raise FileExistsError('sidecar already exists; use a new output path')
    started = perf_counter()
    original = traces_path.read_bytes()
    traces = json.loads(original)
    # Validate completed source metadata BEFORE opening the requested partition.
    if traces.get('stage') != 'm2_complete' or traces.get('split') != split:
        raise ValueError('a completed trace on the explicitly requested split is required')
    if traces.get('suite_sha256') != file_sha256(suite_path):
        raise ValueError('trace suite hash mismatch')
    protocol, instances = load_suite(suite_path, split)
    if traces.get('protocol') != protocol:
        raise ValueError('trace protocol does not match supplied suite')
    exact = {record['id']: ExactCoverage(instance) for record, instance in instances}
    expected = {(r['id'], k, seed) for r, _ in instances for k in r['budgets'] for seed in protocol['seeds']}
    source_groups = {r['id']: r['source_graph'] for r, _ in instances}
    seen, rows, reference_hashes = set(), [], {}
    for case in traces['cases']:
        key = (case['dataset'], case['k'], case['seed'])
        if (key not in expected or key in seen or type(key[1]) is not int or type(key[2]) is not int
                or case.get('source_graph') != source_groups[key[0]]
                or not isinstance(case.get('methods'), dict) or not case['methods']):
            raise ValueError('duplicate or unexpected trace case')
        seen.add(key)
        oracle, k = exact[key[0]], key[1]
        witnesses, feasible = [], []
        if reference_dir is not None:
            # dataset IDs come from a manifest, not arbitrary path authorization.
            ref = (Path(reference_dir) / f'{key[0]}-k{k}.json').resolve()
            if not ref.is_relative_to(Path(reference_dir).resolve()):
                raise ValueError('reference path escapes directory')
            witnesses, feasible = read_references(ref, oracle, k)
            reference_hashes[ref.name] = file_sha256(ref)
        for method, measured in case['methods'].items():
            if measured.get('correct') is not True:
                rows.append({'dataset': key[0], 'k': k, 'seed': key[2], 'method': method,
                             'status': 'not_certified_invalid_trial', 'error': measured.get('error')})
                continue
            replay = score_trace(oracle.instance, k, protocol['checkpoints_seconds'],
                                 measured['events'], oracle.oracle)
            recorded = measured['coverage_at_checkpoints']
            if (len(recorded) != len(replay['coverage_at_checkpoints'])
                    or measured['selected'] != replay['selected']
                    or not isclose(replay['mean_checkpoint_coverage'], measured['mean_checkpoint_coverage'], rel_tol=0, abs_tol=1e-12)
                    or measured['checkpoints_seconds'] != protocol['checkpoints_seconds']
                    or not isclose(replay['final_coverage'], measured['final_coverage'], rel_tol=0, abs_tol=1e-12)
                    or any(not isclose(a, b, rel_tol=0, abs_tol=1e-12)
                           for a, b in zip(recorded, replay['coverage_at_checkpoints']))):
                raise ValueError('source scores do not match independent event replay')
            checkpoints = []
            for t, old_coverage in zip(protocol['checkpoints_seconds'], recorded):
                available = [v for v in replay['improvements'] if v['received_seconds'] <= t]
                chosen = available[-1]['selected']
                cert = certificate(oracle, chosen, k, witnesses=witnesses, feasible_references=feasible)
                if not isclose(float(cert['coverage_pct']) / 100, old_coverage, rel_tol=0, abs_tol=1e-12):
                    raise ValueError('exact underlying coverage disagrees with source scorer')
                checkpoints.append({'seconds': t, 'recorded_coverage': old_coverage, 'certificate': cert})
            final = certificate(oracle, replay['selected'], k, witnesses=witnesses, feasible_references=feasible)
            rows.append({'dataset': key[0], 'source_graph': case['source_graph'], 'k': k,
                         'seed': key[2], 'method': method, 'status': 'certified',
                         'checkpoints': checkpoints, 'final': final})
    if seen != expected:
        raise ValueError('completed trace is missing expected cases')
    if traces_path.read_bytes() != original or traces['suite_sha256'] != file_sha256(suite_path):
        raise RuntimeError('source trace or suite changed during post-processing')
    result = {'schema_version': 1, 'kind': 'posthoc_quality_certificates', 'model': MODEL,
              'source_trace_sha256': sha256(original).hexdigest(), 'suite_sha256': traces['suite_sha256'],
              'split': split, 'reference_sha256': reference_hashes,
              'evaluated_utc': datetime.now(timezone.utc).isoformat(),
              'postprocessing_seconds': perf_counter() - started,
              'timing_scope': 'Offline bound known after search, not certified quality available to the solver at checkpoint time.',
              'candidate_executions': 0, 'model_calls': 0,
              'fitness_and_source_trace_modified': False, 'trials': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting an existing original or sidecar.
    with output.open('x') as file:
        json.dump(result, file, indent=2, allow_nan=False)
        file.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--traces', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-dir', type=Path)
    parser.add_argument('--split', choices=['development', 'validation', 'test'], default='development')
    args = parser.parse_args()
    result = annotate(args.suite, args.traces, args.output, args.reference_dir, args.split)
    print(json.dumps({'trials': len(result['trials']), 'candidate_executions': 0,
                      'postprocessing_seconds': result['postprocessing_seconds']}, indent=2))

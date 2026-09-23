"""Replay M4 development integration evidence and optionally update its README block.

No model calls, no solver reruns, no validation/test transportation scoring.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_anytime import write_json
from swarm_location.anytime import score_trace
from swarm_location.comparisons import comparison_spec, paired_comparisons, load_profile
from swarm_location.core import ShortestPathCoverage
from swarm_location.suite import file_sha256, load_suite

START, END = '<!-- M4-INTEGRATION:START -->', '<!-- M4-INTEGRATION:END -->'


def report(evidence: Path, suite: Path) -> dict:
    evidence, suite = Path(evidence), Path(suite)
    load = lambda p: json.loads((evidence/p).read_text())
    tests = (evidence/'tests.txt').read_text()
    matches = re.findall(r'Ran (\d+) tests? in', tests)
    if not matches or not re.search(r'^OK\s*$', tests, re.M):
        raise ValueError('full tests did not pass')
    continuity = load('continuity.json')
    native = load('native/native_seed_check.json')
    native_config = load('native/native_config_check.json')
    metrics = load('native/seed/metrics.json')
    correct = load('native/seed/correct.json')
    traces = load('native/seed/traces.json')
    protocol, instances = load_suite(suite, 'development')
    spec = comparison_spec(protocol, 'development')
    if (spec is None or protocol['comparison_profile']['definition_sha256'] != load_profile(ROOT/'configs/comparisons_m4.json')['definition_sha256']
            or traces['stage'] != 'm2_complete' or traces['split'] != 'development'
            or traces['suite_sha256'] != file_sha256(suite) or traces['protocol'] != protocol
            or metrics['private']['suite_sha256'] != file_sha256(suite)
            or native['suite_sha256'] != file_sha256(suite)):
        raise ValueError('integration suite/profile mismatch')
    if (metrics['private']['candidate_sha256'] != file_sha256(ROOT/'anytime_initial.py')
            or native['installed_commit'] != json.loads((ROOT/'configs/evolution_m3.json').read_text())['framework_commit']
            or native_config['installed_commit'] != native['installed_commit']
            or native['combined_score'] != metrics['combined_score']):
        raise ValueError('native seed/framework identity mismatch')
    if (not continuity['success'] or not native['correct'] or not correct['correct']
            or native['model_calls'] != 0 or native['evolved_descendants'] != 0
            or native_config['model_calls'] != 0 or metrics['public']['failed_cases'] != 0
            or metrics['private']['docker_image_id'] is None):
        raise ValueError('cannot report a contained no-model integration success')
    catalog = json.loads((ROOT/'configs/source_catalog_m3.json').read_text())
    allowed = {r['source_graph'] for r in catalog['datasets'] if r['split'] == 'development'}
    if {e['source_graph'] for e, _ in instances} != allowed:
        raise ValueError('commissioning must use exactly the original development sources')
    lookup = {e['id']: (e, instance, ShortestPathCoverage(instance)) for e, instance in instances}
    expected = {(e['id'], k, seed) for e, _ in instances for k in e['budgets'] for seed in protocol['seeds']}
    cases = traces['cases']
    if len(cases) != len(expected) or {(r['dataset'],r['k'],r['seed']) for r in cases} != expected:
        raise ValueError('missing or duplicate integration cases')
    rescored = 0
    for row in cases:
        e, instance, oracle = lookup[row['dataset']]
        if row['source_graph'] != e['source_graph'] or set(row['methods']) != set(spec['baselines']) | {'candidate'}:
            raise ValueError('incomplete integration comparison')
        for result in row['methods'].values():
            if (not result['correct'] or result['isolation']['mode'] != 'docker'
                    or result['isolation']['image_id'] != metrics['private']['docker_image_id']):
                raise ValueError('failed/noncontained trial')
            score = score_trace(instance, row['k'], protocol['checkpoints_seconds'], result['events'], oracle)
            if any(score[key] != result[key] for key in score):
                raise ValueError('independent trajectory rescore mismatch')
            rescored += len(result['events'])
    comparisons = paired_comparisons(cases, 'candidate', spec)
    if comparisons != metrics['extra_data']['comparisons'] or comparisons != load('native/seed/comparisons.json'):
        raise ValueError('paired comparison report mismatch')
    delta = next(r['delta_mean_checkpoint_pp'] for r in comparisons['rows'] if r['scope']=='overall' and r['baseline']=='greedy')
    if abs(metrics['combined_score'] - (100 + delta)) > 1e-12:
        raise ValueError('scalar fitness changed')
    result = {'schema_version': 1, 'success': True, 'stage': 'm4_comparator_integration',
              'test_count': int(matches[-1]), 'protected_historical_files': continuity['protected_file_count'],
              'historical_readme_blocks_unchanged': continuity['historical_readme_blocks_unchanged'],
              'paired_development_cases': len(cases), 'solver_trials': sum(len(r['methods']) for r in cases),
              'failed_trials': 0, 'deployments_independently_rescored': rescored,
              'native_scheduler': native['native_scheduler'], 'framework_commit': native['installed_commit'],
              'docker_image_id': metrics['private']['docker_image_id'],
              'comparison_profile': spec, 'mean_checkpoint_coverage_pct': metrics['public']['mean_checkpoint_coverage_pct'],
              'combined_score': metrics['combined_score'], 'model_calls': 0, 'evolved_descendants': 0,
              'research_validation_solver_trials': 0, 'research_test_solver_trials': 0,
              'scope': 'Contained development seed and profile plumbing; synthetic stage tests are not research holdout performance; no evolutionary superiority claim',
              'evidence_sha256': {p: file_sha256(evidence/p) for p in ['tests.txt', 'continuity.json',
                  'native/native_seed_check.json', 'native/native_config_check.json',
                  'native/seed/metrics.json', 'native/seed/traces.json', 'native/seed/comparisons.json']}}
    write_json(evidence/'summary.json', result)
    return result


def readme_block(result: dict) -> str:
    return (f"**Executed integration evidence:** {result['test_count']} tests passed; "
            f"the pinned native scheduler evaluated the unchanged greedy seed on "
            f"{result['paired_development_cases']} development cases with four fixed controls "
            f"(**{result['solver_trials']} Docker-isolated solver trials, zero failures**). "
            f"Independent replay rescored {result['deployments_independently_rescored']} submitted deployments "
            "and checked every staged comparison against its raw trajectories.\n\n"
            f"Continuity checks confirm **{result['protected_historical_files']} protected files** and all "
            "six historical README result blocks are byte-for-byte unchanged. "
            "Validation/test stage routing and fixed-control completeness were exercised only on explicitly "
            "labelled synthetic unit fixtures. **Model calls: 0; evolved descendants: 0; "
            "research validation/test solver trials: 0.**\n\n"
            "[Integration summary](results/step4/integration/summary.json), "
            "[paired screening comparisons](results/step4/integration/native/seed/comparisons.json), "
            "[raw trajectories](results/step4/integration/native/seed/traces.json), "
            "[continuity record](results/step4/integration/continuity.json), "
            "and [test transcript](results/step4/integration/tests.txt).")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--suite', type=Path, required=True)
    p.add_argument('--update-readme', action='store_true')
    a = p.parse_args(); result = report(a.evidence, a.suite)
    if a.update_readme:
        path=ROOT/'README.md'; text=path.read_text()
        if text.count(START) != 1 or text.count(END) != 1:
            raise ValueError('missing or repeated M4 README markers')
        before, rest = text.split(START); _, after = rest.split(END)
        path.write_text(before+START+'\n\n'+readme_block(result)+'\n\n'+END+after)
    print(json.dumps(result, indent=2))

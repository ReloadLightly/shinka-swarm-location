"""Staged-comparator unit/integration fixtures, never research holdout results.

Synthetic graphs, stubbed timings and synthetic databases here test plumbing and
arithmetic only. Real held-out transportation datasets are not opened or scored.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from campaign import checked_request, comparison_profile_path, prepare_stage, start
from evaluate_anytime import evaluate
from run_evo import parser, plan, TASK
from scripts.prepare_research import prepare
from swarm_location.comparisons import (
    ASSESSMENT_RULE, FITNESS, SPLITS, bind_profile, checked_definition,
    comparison_feedback, comparison_plan, comparison_spec, definition_sha256,
    evaluation_methods, load_profile, paired_comparisons, verify_comparison_evidence,
)
from swarm_location.selection import snapshot_population, freeze_champion, evaluate_frozen_test, verify_champion
from swarm_location.suite import file_sha256, load_suite

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT/'configs/comparisons_m4.json'
IMAGE = 'sha256:' + 'a'*64


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def synthetic_catalog(root):
    """Distinct tiny graphs and local TNTP files for stage-routing checks."""
    raw = root/'raw'
    rows = []
    for i, split in enumerate(SPLITS, 1):
        network = (f'<NUMBER OF NODES> 3\n<NUMBER OF LINKS> 2\n<FIRST THRU NODE> 1\n'
                   f'<END OF METADATA>\n1 2 100 1 {i};\n2 3 100 1 {i};\n').encode()
        trips = b'<TOTAL OD FLOW> 5\n<END OF METADATA>\nOrigin 1\n3 : 5;\n'
        files = {}
        for role, content in [('network', network), ('trips', trips)]:
            path = Path(split)/(role+'.tntp')
            (raw/path).parent.mkdir(parents=True, exist_ok=True)
            (raw/path).write_bytes(content)
            files[role] = {'path': str(path), 'git_blob_sha1': blob(content)}
        rows.append({'id': 'unit-'+split, 'source_graph': 'unit-'+split, 'split': split,
                     'expected_nodes': 3, 'expected_edges': 2, 'budgets': [1, 2],
                     'scenario': 'synthetic protocol unit fixture, not a held-out research graph', 'files': files})
    catalog = {'schema_version': 1, 'upstream_repository': 'unit/fixture', 'upstream_commit': 'unit',
               'routing': 'unit fixed routes', 'license': 'unit data', 'checkpoints_seconds': [.1, .3],
               'seeds': {split: [0] for split in SPLITS},
               'header_total_tolerance': {'absolute': '0.000000001', 'relative': '0.000000000001'},
               'datasets': rows, 'excluded': []}
    path = root/'catalog.json'; path.write_text(json.dumps(catalog))
    return path, raw


def trace(checkpoints, final=None, correct=True):
    return {'correct': correct, 'error': None if correct else 'unit fixture failure',
            'mean_checkpoint_coverage': sum(checkpoints)/len(checkpoints),
            'final_coverage': checkpoints[-1] if final is None else final,
            'checkpoints_seconds': [.1, .3], 'coverage_at_checkpoints': list(checkpoints)}


def fixed_records(spec):
    controls = {m: trace([.3, .5]) for m in spec['baselines']}
    controls['greedy'] = trace([.2, .4])
    if 'early_celf_swap' in controls:
        controls['early_celf_swap'] = trace([.6, .8])
    return [{'dataset': 'unit-a', 'source_graph': 'unit-a', 'k': 1, 'seed': 0,
             'methods': {**controls, 'candidate': trace([.4, .6])}}]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(PROFILE)
        self.definition = self.profile['definition']

    def test_explicit_small_screening_and_strong_assessment(self):
        self.assertEqual(self.definition['baseline_sets']['development'],
                         ['greedy', 'greedy_swap', 'topk', 'early_celf_swap'])
        for split in ('validation', 'test'):
            self.assertEqual(self.definition['baseline_sets'][split],
                             ['greedy', 'greedy_swap', 'topk', 'early_celf_swap', 'iterated', 'dfbnb', 'potential'])
        self.assertEqual(self.definition['fitness'], FITNESS)
        self.assertEqual(self.definition['assessment_rule'], ASSESSMENT_RULE)

    def test_bad_control_names_duplicates_and_missing_references_rejected(self):
        for methods in [[], ['greedy'], ['greedy', 'greedy_swap', 'candidate'],
                        ['greedy', 'greedy_swap', 'potentiall'], ['greedy', 'greedy_swap', 'greedy'],
                        ['greedy', 'greedy_swap', []], 'greedy']:
            definition = deepcopy(self.definition)
            definition['baseline_sets']['development'] = methods
            with self.subTest(methods=methods), self.assertRaises(ValueError):
                checked_definition(definition)

    def test_mismatched_assessment_or_unspecified_stage_rejected(self):
        for change in ['test', 'missing', 'subset', 'schema', 'extra', 'fitness']:
            definition = deepcopy(self.definition)
            if change == 'test': definition['baseline_sets']['test'].pop()
            if change == 'missing': del definition['baseline_sets']['validation']
            if change == 'subset': definition['baseline_sets']['development'].append('celf')
            if change == 'schema': definition['schema_version'] = True
            if change == 'extra': definition['typo'] = []
            if change == 'fitness': definition['fitness'] = 'against_best_baseline'
            with self.subTest(change=change), self.assertRaises(ValueError):
                checked_definition(definition)

    def test_legacy_methods_and_order_preserved(self):
        self.assertEqual(evaluation_methods({}, 'development'), ['greedy', 'greedy_swap', 'candidate'])
        self.assertEqual(evaluation_methods({'extra_baselines': ['topk']}, 'test'),
                         ['greedy', 'greedy_swap', 'candidate', 'topk'])
        self.assertEqual(evaluation_methods({}, 'validation', True), ['random', 'topk', 'greedy', 'greedy_swap'])
        self.assertIsNone(comparison_spec({}, 'development'))

    def test_profile_controls_baselines_only_as_well(self):
        for split in SPLITS:
            suite = bind_profile({}, self.profile, split)
            methods = self.definition['baseline_sets'][split]
            self.assertEqual(evaluation_methods(suite, split, True), methods)
            self.assertEqual(evaluation_methods(suite, split), methods + ['candidate'])

    def test_embedded_profile_digest_stage_and_extras_verified(self):
        for change in ['digest', 'stage', 'extras', 'file_digest', 'definition']:
            suite = bind_profile({}, self.profile, 'development')
            if change == 'digest': suite['comparison_profile']['definition_sha256'] = '0'*64
            if change == 'stage': suite['comparison_profile']['stage'] = 'test'
            if change == 'extras': suite['extra_baselines'] = ['topk']
            if change == 'file_digest': suite['comparison_profile']['file_sha256'] = 'bad'
            if change == 'definition': suite['comparison_profile']['definition']['profile_id'] += '-changed'
            with self.subTest(change=change), self.assertRaises(ValueError):
                comparison_spec(suite, 'development')

    def test_trial_plans_are_counts_not_measurements(self):
        screening = comparison_plan(bind_profile({}, self.profile, 'development'), 'development', 24)
        assessment = comparison_plan(bind_profile({}, self.profile, 'test'), 'test', 40)
        self.assertEqual(screening['fixed_control_trials_per_program'], 96)
        self.assertEqual(screening['total_solver_trials_per_program'], 120)
        self.assertEqual(assessment['total_solver_trials_per_program'], 320)

    def test_m3_request_unchanged_and_m4_opt_in(self):
        m3 = checked_request(ROOT/'configs/m3_launch_request.json')
        m4 = checked_request(ROOT/'configs/m4_launch_request.json')
        self.assertIsNone(comparison_profile_path(m3))
        self.assertEqual(comparison_profile_path(m4), PROFILE)
        for key in ['framework_commit', 'generations', 'seed', 'models', 'max_api_cost_usd', 'shortlist_size']:
            self.assertEqual(m3[key], m4[key])

    def test_new_profile_not_accepted_in_legacy_request(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'request.json'
            request = json.loads((ROOT/'configs/m3_launch_request.json').read_text())
            request['comparison_profile'] = 'configs/comparisons_m4.json'
            p.write_text(json.dumps(request))
            with self.assertRaises(ValueError): checked_request(p)
            request['schema_version'] = 2
            for bad in ['../outside.json', '/tmp/outside.json', '', None]:
                request['comparison_profile'] = bad
                p.write_text(json.dumps(request))
                with self.subTest(bad=bad), self.assertRaises(ValueError): checked_request(p)


    def test_new_request_cannot_overwrite_an_existing_preflight_identity(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            old = {'native_runner_started': False, 'request_sha256': '0'*64, 'status': 'blocked_model_access'}
            state_path = out/'campaign_status.json'; state_path.write_text(json.dumps(old))
            original = state_path.read_bytes()
            with patch('campaign.verify_native') as native:
                with self.assertRaisesRegex(ValueError, 'preflight identity changed'):
                    start(ROOT/'configs/m4_launch_request.json', out, None, False, False)
                native.assert_not_called()
            self.assertEqual(state_path.read_bytes(), original)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.catalog, self.raw = synthetic_catalog(self.root)

    def tearDown(self): self.tmp.cleanup()

    def test_stage_profiles_and_identical_source_bytes(self):
        for split in SPLITS:
            legacy = self.root/('legacy-'+split); staged = self.root/('staged-'+split)
            prepare(self.catalog, legacy, self.raw, split)
            prepare(self.catalog, staged, self.raw, split, comparison_profile=PROFILE)
            self.assertEqual((legacy/('unit-'+split+'.json')).read_bytes(),
                             (staged/('unit-'+split+'.json')).read_bytes())
            old, _ = load_suite(legacy/'suite.json', split)
            new, instances = load_suite(staged/'suite.json', split)
            self.assertEqual(old['extra_baselines'], ['topk'])
            for key in ['datasets', 'seeds', 'checkpoints_seconds', 'catalog_sha256']:
                self.assertEqual(old[key], new[key])
            self.assertEqual(len(instances), 1)
            self.assertEqual(len(evaluation_methods(new, split)), 5 if split == 'development' else 8)

    def test_development_does_not_read_other_sources(self):
        from scripts.prepare_research import source_bytes
        with patch('scripts.prepare_research.source_bytes', wraps=source_bytes) as read:
            prepare(self.catalog, self.root/'out', self.raw, 'development', comparison_profile=PROFILE)
        self.assertTrue(all(c.args[0]['path'].startswith('development/') for c in read.call_args_list))

    def test_wrong_stage_fails_before_loading_dataset(self):
        out = self.root/'out'
        prepare(self.catalog, out, self.raw, 'development', comparison_profile=PROFILE)
        with patch('swarm_location.core.Instance.load', side_effect=AssertionError('data must not open')):
            with self.assertRaises(ValueError): load_suite(out/'suite.json', 'test')

    def test_profile_change_or_downgrade_cannot_overwrite_suite(self):
        out = self.root/'out'
        prepare(self.catalog, out, self.raw, 'development', comparison_profile=PROFILE)
        original = (out/'suite.json').read_bytes()
        with self.assertRaises(ValueError): prepare(self.catalog, out, self.raw, 'development')
        self.assertEqual((out/'suite.json').read_bytes(), original)
        changed = self.root/'profile.json'
        definition = load_profile(PROFILE)['definition']; definition['profile_id'] += '-new'
        changed.write_text(json.dumps(definition))
        with self.assertRaises(ValueError):
            prepare(self.catalog, out, self.raw, 'development', comparison_profile=changed)
        self.assertEqual((out/'suite.json').read_bytes(), original)

    def test_campaign_stage_function_propagates_same_profile(self):
        profile = load_profile(PROFILE)
        with patch('campaign.prepare', return_value={}) as prepare_call:
            for split in SPLITS:
                prepare_stage(self.catalog, self.root/'campaign', split, False, PROFILE, profile)
        self.assertEqual([c.args[3] for c in prepare_call.call_args_list], list(SPLITS))
        self.assertTrue(all(c.kwargs['comparison_profile'] == PROFILE for c in prepare_call.call_args_list))
        bad = deepcopy(profile); bad['file_sha256'] = '0'*64
        with patch('campaign.prepare') as prepare_call:
            with self.assertRaises(ValueError):
                prepare_stage(self.catalog, self.root, 'test', False, PROFILE, bad)
            prepare_call.assert_not_called()

    def test_native_plan_uses_profile_without_changing_evolution_settings(self):
        out = self.root/'out'
        prepare(self.catalog, out, self.raw, 'development', comparison_profile=PROFILE)
        resolved = plan(parser().parse_args(['--suite', str(out/'suite.json'), '--config', str(ROOT/'configs/evolution_m3.json')]))
        self.assertFalse(resolved['model_calls_enabled'])
        self.assertEqual(resolved['comparison_plan']['total_solver_trials_per_program'], 10)
        self.assertIn('early_celf_swap', resolved['evo_config']['task_sys_msg'])
        self.assertIn('potential', resolved['evo_config']['task_sys_msg'])
        self.assertTrue(resolved['evo_config']['task_sys_msg'].startswith(TASK))
        self.assertEqual(resolved['evo_config']['llm_dynamic_selection'], 'ucb')
        self.assertEqual(resolved['db_config']['num_islands'], 4)


class ComparisonArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.suite = bind_profile({}, load_profile(PROFILE), 'test')
        self.spec = comparison_spec(self.suite, 'test')
        self.records = fixed_records(self.spec)

    def test_paired_deltas_early_and_final_reported_separately(self):
        report = paired_comparisons(self.records, 'candidate', self.spec)
        rows = {r['baseline']: r for r in report['rows'] if r['scope'] == 'overall'}
        self.assertEqual(set(rows), set(self.spec['baselines']))
        self.assertAlmostEqual(rows['greedy']['delta_mean_checkpoint_pp'], 20)
        self.assertAlmostEqual(rows['early_celf_swap']['delta_mean_checkpoint_pp'], -20)
        self.assertAlmostEqual(rows['iterated']['delta_final_pp'], 10)
        self.assertEqual(len(report['rows']), 3*7)
        self.assertIn('vs potential', comparison_feedback(report))
        self.assertIn('not extra rewards', comparison_feedback(report))

    def test_failed_control_invalidates_not_omitted_or_treated_as_zero(self):
        self.records[0]['methods']['potential'] = trace([0, 0], correct=False)
        report = paired_comparisons(self.records, 'candidate', self.spec)
        self.assertFalse(report['evaluation_valid'])
        row = next(r for r in report['rows'] if r['baseline'] == 'potential')
        self.assertEqual(row['failed_pairs'], 1)
        self.assertNotIn('delta_mean_checkpoint_pp', row)
        self.assertIn('vs potential: INVALID', comparison_feedback(report))

    def test_missing_control_and_mismatched_checkpoints_fail(self):
        records = deepcopy(self.records); del records[0]['methods']['potential']
        with self.assertRaises(ValueError): paired_comparisons(records, 'candidate', self.spec)
        records = deepcopy(self.records); records[0]['methods']['potential']['checkpoints_seconds'] = [.2, .3]
        with self.assertRaises(ValueError): paired_comparisons(records, 'candidate', self.spec)

    def test_screening_feedback_does_not_invent_unexecuted_control_results(self):
        spec = comparison_spec(bind_profile({}, load_profile(PROFILE), 'development'), 'development')
        report = paired_comparisons(fixed_records(spec), 'candidate', spec)
        text = comparison_feedback(report)
        self.assertIn('not executed in this screening evaluation: dfbnb, iterated, potential', text)
        self.assertNotIn('vs potential:', text)

    def test_metrics_evidence_rejects_missing_or_wrong_controls(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'suite.json'; p.write_text(json.dumps(self.suite))
            report = paired_comparisons(self.records, 'candidate', self.spec)
            metrics = {'public': {'failed_cases': 0}, 'extra_data': {'comparisons': report}}
            verify_comparison_evidence(metrics, p, 'test')
            for change in ['missing', 'digest', 'rows', 'correct']:
                modified = deepcopy(metrics)
                if change == 'missing': modified['extra_data'] = {}
                if change == 'digest': modified['extra_data']['comparisons']['definition_sha256'] = '0'*64
                if change == 'rows': modified['extra_data']['comparisons']['rows'].pop(0)
                if change == 'correct': modified['extra_data']['comparisons']['evaluation_valid'] = False
                with self.subTest(change=change), self.assertRaises(ValueError):
                    verify_comparison_evidence(modified, p, 'test')


class EvaluatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        catalog, raw = synthetic_catalog(self.root)
        for split in SPLITS:
            prepare(catalog, self.root/split, raw, split, comparison_profile=PROFILE)

    def tearDown(self): self.tmp.cleanup()

    def test_real_workers_execute_both_profiles_and_all_assessment_methods(self):
        for split in SPLITS:
            out = self.root/('result-'+split)
            suite = self.root/split/'suite.json'
            metrics = evaluate(ROOT/'anytime_initial.py', out, suite, split)
            self.assertTrue(json.loads((out/'correct.json').read_text())['correct'])
            traces = json.loads((out/'traces.json').read_text())
            spec = comparison_spec(json.loads(suite.read_text()), split)
            self.assertTrue(all(set(r['methods']) == set(spec['baselines']) | {'candidate'} for r in traces['cases']))
            self.assertEqual(metrics['public']['solver_trials'], 10 if split == 'development' else 16)
            self.assertAlmostEqual(metrics['combined_score'], 100.)
            self.assertEqual(json.loads((out/'comparisons.json').read_text()), metrics['extra_data']['comparisons'])
            verify_comparison_evidence(metrics, suite, split)

    def test_strong_controls_do_not_replace_fitness_with_best_control(self):
        suite = self.root/'test/suite.json'
        spec = comparison_spec(json.loads(suite.read_text()), 'test')
        fake = fixed_records(spec)[0]['methods']
        def run(*args, **kwargs):
            return deepcopy(fake[kwargs.get('baseline') or 'candidate'])
        with patch('evaluate_anytime.run_anytime', side_effect=run):
            metrics = evaluate(ROOT/'anytime_initial.py', self.root/'out', suite, 'test')
        self.assertAlmostEqual(metrics['combined_score'], 120.)
        self.assertAlmostEqual(metrics['public']['delta_vs_early_celf_swap_pp'], -20.)
        self.assertAlmostEqual(metrics['public']['final_delta_vs_potential_pp'], 10.)

    def test_failed_strong_control_sets_zero_fitness_and_preserves_failure(self):
        suite = self.root/'test/suite.json'; out = self.root/'out'
        spec = comparison_spec(json.loads(suite.read_text()), 'test')
        fake = fixed_records(spec)[0]['methods']; fake['potential'] = trace([0, 0], correct=False)
        with patch('evaluate_anytime.run_anytime', side_effect=lambda *a, **k: deepcopy(fake[k.get('baseline') or 'candidate'])):
            metrics = evaluate(ROOT/'anytime_initial.py', out, suite, 'test')
        self.assertEqual(metrics['combined_score'], 0.)
        self.assertEqual(metrics['public']['failed_cases'], 2)
        self.assertFalse(json.loads((out/'correct.json').read_text())['correct'])
        self.assertEqual(len(metrics['extra_data']['comparisons']['rows']), 28)
        # An aborted rerun cannot leave its previous comparison report active.
        with patch('evaluate_anytime.load_suite', side_effect=ValueError('unit failure')):
            with self.assertRaises(ValueError): evaluate(ROOT/'anytime_initial.py', out, suite, 'test')
        self.assertFalse((out/'comparisons.json').exists())

    def test_legacy_feedback_and_default_control_set_preserved(self):
        suite = self.root/'development/suite.json'
        data = json.loads(suite.read_text()); del data['comparison_profile']; data['extra_baselines'] = ['topk']
        suite.write_text(json.dumps(data))
        metrics = evaluate(ROOT/'anytime_initial.py', self.root/'legacy', suite)
        self.assertNotIn('comparisons', metrics['extra_data'])
        self.assertNotIn('Comparison profile', metrics['text_feedback'])
        self.assertNotIn('solver_trials', metrics['public'])
        self.assertEqual(metrics['public']['stage'], 'm2_anytime_candidate_evaluation')

    def test_freeze_then_test_keeps_profile_and_rejects_changed_assessment(self):
        # Synthetic database used only to exercise selection plumbing, not discovery.
        db = self.root/'unit.sqlite'; seed = ROOT/'anytime_initial.py'
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE programs (id TEXT, code TEXT, generation INTEGER, combined_score REAL, correct INTEGER, metadata TEXT)')
            conn.executemany('INSERT INTO programs VALUES (?,?,?,?,?,?)', [
                ('seed', seed.read_text(), 0, 100., 1, '{}'),
                ('unit-copy', seed.read_text()+'\n# unit fixture, not evolved\n', 1, 100., 1, '{}')])
        out = self.root/'selection'; snapshot_population(db, out, seed, 1)
        champion = freeze_champion(out, self.root/'validation/suite.json', evaluate, None)
        self.assertEqual(champion['comparison_profile']['baselines'], load_profile(PROFILE)['definition']['baseline_sets']['validation'])
        manifest = out/'champion.json'; original_champion = manifest.read_text()
        altered = deepcopy(champion); altered['comparison_profile']['profile_id'] += '-changed'
        manifest.write_text(json.dumps(altered))
        with self.assertRaises(ValueError): verify_champion(out)
        manifest.write_text(original_champion)
        suite = self.root/'test/suite.json'
        original = suite.read_text(); data = json.loads(original)
        changed = deepcopy(load_profile(PROFILE)); changed['definition']['profile_id'] += '-changed'
        changed['definition_sha256'] = definition_sha256(changed['definition'])
        suite.write_text(json.dumps(bind_profile(data, changed, 'test')))
        with self.assertRaises(ValueError): evaluate_frozen_test(out, suite, evaluate, None)
        self.assertFalse((out/'test_opened.json').exists())
        suite.write_text(original)
        metrics = evaluate_frozen_test(out, suite, evaluate, None)
        verify_comparison_evidence(metrics, suite, 'test')
        with self.assertRaises(FileExistsError): evaluate_frozen_test(out, suite, evaluate, None)


if __name__ == '__main__':
    unittest.main()

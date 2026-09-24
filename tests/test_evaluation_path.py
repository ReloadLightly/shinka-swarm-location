"""Evaluator regression tests, not shortened substitutes for the research suite."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from swarm_location.core import Instance, ShortestPathCoverage
from swarm_location.search import SearchProblem
from swarm_location.prepared import ensure_prepared, load_prepared
from swarm_location.persistence import CaseStore, digest, exclusive, atomic_json
from swarm_location.anytime import run_anytime
from swarm_location.isolation import require_isolation
from swarm_location.verification import limits_from
from swarm_location.suite import file_sha256
import evaluate_search as evaluator

ROOT = Path(__file__).resolve().parents[1]


def instance():
    return Instance.from_dict({'schema_version': 2, 'name': 'ties', 'nodes': [0,1,2,3,4],
        'edges': [[0,2,0],[2,1,0],[0,1,0],[1,3,1],[3,4,1]],
        'od': [[0,4,.1],[2,3,.2],[1,4,.3]], 'non_thru_nodes': [0,4]})


def fixture(root, budgets=(1,2)):
    data = root/'instance.json'; atomic_json(data, instance().to_dict())
    protocol = {'schema_version': 2, 'research_protocol': 'chapter-search-v2',
        'checkpoints_seconds': [.1,.3], 'seeds': [0], 'relabel_seed': 5,
        'verification_timeout_seconds': 5, 'verification_memory_mib': 256,
        'fitness': {'coverage_weight':.5, 'certificate_weight':.5},
        'controls': ['greedy','topk'],
        'datasets': [{'id':'fixture','source_graph':'fixture','split':'development',
                      'path':data.name,'sha256':file_sha256(data),'budgets':list(budgets)}]}
    suite = root/'suite.json'; atomic_json(suite, protocol)
    candidate = root/'candidate.py'
    candidate.write_text('def solve(p,k,seed,report,budget):\n report(list(p.nodes)[:k])\n')
    return suite, root/'references.json', candidate


class EvaluationPathTests(unittest.TestCase):
    def test_prepared_roundtrip_exact_ties_scores_gains_and_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            original = instance(); expected = SearchProblem(original)
            path, sha, reused = ensure_prepared(original, d)
            self.assertFalse(reused)
            with patch.object(ShortestPathCoverage, '__init__', side_effect=AssertionError('Dijkstra rebuilt')):
                self.assertTrue(ensure_prepared(original, d)[2])
                loaded = load_prepared(path, sha, original)
                actual = SearchProblem(original, loaded)
            self.assertEqual(actual.dags[0].counts[4], 2)
            for k in range(3):
                for selected in itertools.combinations(original.nodes, k):
                    self.assertEqual(actual.score(selected), expected.score(selected))
                    self.assertEqual(actual.marginal_gains(selected), expected.marginal_gains(selected))
            self.assertEqual(actual.query_work['score_calls'], 16)
            self.assertFalse(path.stat().st_mode & 0o222)

    def test_prepared_large_counts_no_overflow_or_route_enumeration(self):
        layers = [[0]] + [[2*i+1,2*i+2] for i in range(130)] + [[261]]
        data = Instance.from_dict({'schema_version':1,'name':'many-routes','nodes':list(range(262)),
            'edges':[[u,v,1] for left,right in zip(layers,layers[1:]) for u in left for v in right], 'od':[[0,261,1]]})
        with tempfile.TemporaryDirectory() as d:
            path, sha, _ = ensure_prepared(data, d)
            result = load_prepared(path, sha)
            self.assertEqual(result.dags[0].counts[261], 2**130)
            self.assertEqual(result.score([0]), 1)

    def test_prepared_compact_storage_and_private_worker_state(self):
        n = 1050
        data = Instance.from_dict({'schema_version':1,'name':'chain','nodes':list(range(n)),
            'edges':[[v,v+1,1] for v in range(n-1)],'od':[[0,n-1,1]]})
        with tempfile.TemporaryDirectory() as d:
            path, sha, _ = ensure_prepared(data, d)
            first = load_prepared(path, sha)
            first.dags[0].counts._values[10] = 999
            second = load_prepared(path, sha)
            self.assertEqual(second.dags[0].counts[10], 1)
            self.assertEqual(second.score([10]), 1)

    def test_prepared_corruption_and_instance_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path, sha, _ = ensure_prepared(instance(), d)
            changed = Instance.from_dict({**instance().to_dict(), 'name':'another'})
            with self.assertRaisesRegex(ValueError, 'instance mismatch'):
                load_prepared(path, sha, changed)
            path.chmod(0o644); path.write_bytes(path.read_bytes()+b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_prepared(path, sha)
            with self.assertRaisesRegex(ValueError, 'corrupt'):
                ensure_prepared(instance(), d)

    def test_error_feedback_classifies_import_and_runtime_and_redacts(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'candidate.py'
            path.write_text("import deliberately_missing_module\n")
            trace = run_anytime(instance(), 1, [.3], program_path=path)
            self.assertEqual(trace['failure_kind'], 'candidate_import')
            self.assertIn('ModuleNotFoundError', trace['stderr_tail'])
            path.write_text("def solve(*args):\n raise RuntimeError('api_key=abc123 sk-abcdefghijklmnop')\n")
            trace = run_anytime(instance(), 1, [.3], program_path=path)
            self.assertEqual(trace['failure_kind'], 'candidate_runtime')
            self.assertIn('RuntimeError', trace['stderr_tail'])
            self.assertNotIn('abc123', trace['stderr_tail'])
            self.assertNotIn('sk-abcdefghijklmnop', trace['stderr_tail'])

    def test_verbose_stderr_does_not_block_incumbents(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'candidate.py'
            path.write_text("def solve(p,k,seed,report,budget):\n import sys\n report([0])\n sys.stderr.write('x'*200000)\n sys.stderr.flush()\n report([1])\n")
            trace = run_anytime(instance(), 1, [1.], program_path=path)
            self.assertTrue(trace['correct'], trace['error'])
            self.assertEqual(trace['received_deployments'], 2)
            self.assertTrue(trace['stderr_truncated'])
            self.assertEqual(len(trace['stderr_tail']), 16384)

    def test_candidate_failures_are_available_in_native_feedback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); suite, refs, candidate = fixture(root, (1,))
            evaluator.build_references(suite, refs, trusted_local=True)
            candidate.write_text('import missing_evolution_dependency\n')
            with self.assertRaisesRegex(RuntimeError, 'missing_evolution_dependency'):
                evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)
            feedback = json.loads((root/'result/metrics.json').read_text())['text_feedback']
            self.assertIn('ModuleNotFoundError', feedback)
            with patch('evaluate_search.run', side_effect=AssertionError('invalid case retimed')):
                with self.assertRaisesRegex(RuntimeError, 'missing_evolution_dependency'):
                    evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)

    def test_reference_resumes_between_controls(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); suite, refs, _ = fixture(root, (1,))
            real = evaluator.run; count = 0
            def interrupted(*a, **kw):
                nonlocal count
                count += 1
                if count == 2: raise KeyboardInterrupt('host interruption')
                return real(*a, **kw)
            with patch('evaluate_search.run', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    evaluator.build_references(suite, refs, trusted_local=True)
            with patch('evaluate_search.run', wraps=real) as calls:
                cache = evaluator.build_references(suite, refs, trusted_local=True)
                self.assertEqual(calls.call_count, 1)
            with patch('evaluate_search.run', side_effect=AssertionError('references retimed')):
                self.assertEqual(evaluator.build_references(suite, refs, trusted_local=True), cache)

    def test_candidate_resumes_only_unfinished_cases(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); suite, refs, candidate = fixture(root)
            evaluator.build_references(suite, refs, trusted_local=True)
            real = evaluator.run; count = 0
            def interrupted(*a, **kw):
                nonlocal count
                count += 1
                if count == 2: raise KeyboardInterrupt('host interruption')
                return real(*a, **kw)
            with patch('evaluate_search.run', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)
            completed = list((root/'result/cases').glob('*.case.json'))
            self.assertEqual(len(completed), 1)
            preserved = completed[0].read_bytes()
            result = evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)
            self.assertEqual(result['public']['completed_cases_reused'], 1)
            self.assertEqual(result['public']['solver_runs_this_evaluation'], 1)
            self.assertEqual(completed[0].read_bytes(), preserved)
            with patch('evaluate_search.run', side_effect=AssertionError('completed case retimed')):
                repeat = evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)
            self.assertEqual(result['combined_score'], repeat['combined_score'])
            self.assertEqual(repeat['public']['completed_cases_reused'], 2)

    def test_changed_candidate_and_tampered_reference_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); suite, refs, candidate = fixture(root, (1,))
            evaluator.build_references(suite, refs, trusted_local=True)
            evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)
            candidate.write_text(candidate.read_text()+'\n# changed\n')
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                evaluator.evaluate(candidate, root/'result', suite, refs, trusted_local=True)
            cache = json.loads(refs.read_text()); next(iter(cache['cases'].values()))['best_known_feasible'] = .01
            atomic_json(refs, cache)
            with self.assertRaisesRegex(ValueError, 'cache mismatch'):
                evaluator.evaluate(candidate, root/'other', suite, refs, trusted_local=True)

    def test_atomic_store_checksum_identity_and_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); store = CaseStore(root/'cases', {'program':'a'})
            store.put(['case',1], {'score':.5})
            with self.assertRaisesRegex(ValueError, 'replace'):
                store.put(['case',1], {'score':.6})
            with self.assertRaisesRegex(ValueError, 'identity'):
                CaseStore(root/'cases', {'program':'b'})
            with exclusive(root/'lock'):
                with self.assertRaisesRegex(RuntimeError, 'in use'):
                    with exclusive(root/'lock'): pass
            path = store.path(['case',1]); data = json.loads(path.read_text()); data['payload']['score'] = 1
            atomic_json(path, data)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                store.get(['case',1])

    def test_verifier_timeout_replays_capture_without_rerunning_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); _, _, candidate = fixture(root, (1,))
            prepared = ensure_prepared(instance(), root/'prepared')
            kwargs = dict(program_path=candidate, allow_candidate_bounds=True,
                prepared_path=prepared[0], prepared_sha256=prepared[1], capture_path=root/'capture.json')
            limited = limits_from({'verification_timeout_seconds':.001,'verification_memory_mib':256})
            first = run_anytime(instance(), 1, [.3], verification_limits=limited, **kwargs)
            self.assertFalse(first['correct'])
            self.assertEqual(first['failure_kind'], 'verification_timeout')
            self.assertEqual(first['verified_search_bounds'], [])
            saved = (root/'capture.json').read_bytes()
            with patch('swarm_location.anytime._capture_anytime', side_effect=AssertionError('candidate reran')):
                retry = run_anytime(instance(), 1, [.3], verification_limits=limits_from(
                    {'verification_timeout_seconds':5,'verification_memory_mib':256}), **kwargs)
            self.assertTrue(retry['correct'], retry['error'])
            self.assertTrue(retry['capture_reused'])
            self.assertEqual((root/'capture.json').read_bytes(), saved)

    def test_invalid_certificate_is_not_accepted_by_limited_checker(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bad.py'; p.write_text('def solve(p,k,s,r,t):\n r([0])\n r.bound({"kind":"universal_v1","upper":"0","selected":[0]})\n')
            trace = run_anytime(instance(),1,[.3],program_path=p,allow_candidate_bounds=True,
                verification_limits=limits_from({'verification_timeout_seconds':5,'verification_memory_mib':256}))
            self.assertFalse(trace['correct'])
            self.assertEqual(trace['failure_kind'], 'invalid_certificate')
            self.assertFalse(trace['retryable'])
            self.assertEqual(trace['verified_search_bounds'], [])

    def test_generated_runs_fail_closed_but_explicit_debug_remains(self):
        from run_evo import parser, plan
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Docker'):
                require_isolation()
            self.assertEqual(require_isolation(True)['mode'], 'trusted-local-debug')
            with tempfile.TemporaryDirectory() as d:
                root = Path(d); suite, _, _ = fixture(root)
                args = parser().parse_args(['--run','--suite',str(suite),'--trusted-local'])
                with self.assertRaisesRegex(ValueError, 'real evolution requires'):
                    plan(args)
                args = parser().parse_args(['--native-seed','--suite',str(suite),'--trusted-local'])
                resolved = plan(args)
                self.assertTrue(resolved['job_config']['extra_cmd_args']['trusted-local'])
        with patch.dict(os.environ, {'SWARM_DOCKER_IMAGE':'sha256:'+'a'*64}), patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                require_isolation(True, check_available=True)

    def test_cli_accepts_native_scheduler_boolean_value(self):
        # Pinned native JobScheduler always emits --key str(value), even booleans.
        process = subprocess.run([sys.executable, str(ROOT/'evaluate_search.py'),
                                  '--trusted-local', 'True', '--help'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(evaluator.debug_boolean('True'))
        self.assertFalse(evaluator.debug_boolean('false'))

    def test_assessment_requires_frozen_code_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); suite, refs, candidate = fixture(root)
            with self.assertRaisesRegex(ValueError, 'frozen program'):
                evaluator.evaluate(candidate, root/'result', suite, refs, 'test', trusted_local=True)

    def test_complete_protocol_has_independent_families_and_opt_in_hour(self):
        catalog = json.loads((ROOT/'configs/source_catalog_search.json').read_text())
        by_split = {name:{v['source_graph'] for v in catalog['datasets'] if v['split']==name}
                    for name in ('development','validation','test')}
        self.assertGreaterEqual(len(by_split['validation']), 2)
        self.assertGreaterEqual(len(by_split['test']), 2)
        for a,b in itertools.combinations(by_split.values(), 2): self.assertFalse(a & b)
        self.assertEqual(catalog['time_profiles']['standard'][-1], 60)
        self.assertEqual(catalog['time_profiles']['chapter-hour'][-1], 3600)
        self.assertEqual(len(catalog['time_profiles']['chapter-hour']), 12)
        self.assertTrue(all(v['budgets']==[20,40,60,80,100] for v in catalog['datasets']))


if __name__ == '__main__': unittest.main()

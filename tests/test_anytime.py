"""Mathematical, protocol and split-boundary checks for the M2 experiment."""
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from swarm_location.anytime import checkpoints_checked, run_anytime, score_trace
from swarm_location.core import Instance, ShortestPathCoverage
from swarm_location.search import SearchProblem
from swarm_location.suite import file_sha256, load_suite
from evaluate_anytime import evaluate
from test_core import make, independent_routes

ROOT = Path(__file__).resolve().parents[1]


def diamond():
    return make([1, 2, 3, 4], [(1, 2, 1), (1, 3, 1), (2, 4, 1), (3, 4, 1)], [(1, 4, 10)])


class MarginalTests(unittest.TestCase):
    def test_all_subsets_against_independent_routes(self):
        for seed in range(10):
            rng = random.Random(seed + 100)
            n = 6
            edges = {(v, (v + 1) % n): rng.randint(1, 4) for v in range(n)}
            edges.update({(u, v): rng.randint(1, 4) for u in range(n) for v in range(n)
                          if u != v and rng.random() < .3})
            instance = make(list(range(n)), [(u, v, w) for (u, v), w in edges.items()],
                            [(s, t, rng.randint(1, 9)) for s in range(n) for t in range(n) if s != t])
            problem = SearchProblem(instance)
            routes = independent_routes(instance)
            for k in range(n + 1):
                for selected in combinations(instance.nodes, k):
                    actual = problem.marginal_gains(selected)
                    for node, gain in actual.items():
                        expected = sum(q for route, q in routes if not route.intersection(selected) and node in route)
                        self.assertAlmostEqual(gain, expected, places=12)

    def test_centroids_decimal_ties_and_weights(self):
        instance = make([1, 2, 3, 4, 5], [(1, 2, '.1'), (2, 4, '.1'), (1, 3, '.2'),
                        (3, 4, '.2'), (1, 5, '.3'), (5, 4, '.1')], [(1, 4, 9), (1, 5, 1)], 3)
        problem, oracle = SearchProblem(instance), ShortestPathCoverage(instance)
        for selected in [[], [1], [2], [3], [3, 5], [4, 5]]:
            base = oracle.score(selected)
            for v, gain in problem.marginal_gains(selected).items():
                self.assertAlmostEqual(gain, oracle.score([*selected, v]) - base, places=12)

    def test_exponential_paths_without_compilation(self):
        layers = 1100  # More than a double can represent as an unscaled path count.
        edges = [(0, 1, 1), (0, 2, 1)]
        for layer in range(1, layers):
            edges.extend((u, v, 1) for u in [2*layer-1, 2*layer]
                         for v in [2*layer+1, 2*layer+2])
        target = 2*layers + 1
        edges.extend([(target-2, target, 1), (target-1, target, 1)])
        problem = SearchProblem(make(list(range(target+1)), edges, [(0, target, 1)]))
        self.assertEqual(problem.dags[0].counts[target], 2**layers)
        gains = problem.marginal_gains([])
        self.assertEqual(gains[0], 1)
        self.assertEqual(gains[1], .5)
        self.assertEqual(problem.marginal_gains([1])[2], .5)
        with self.assertRaises(ValueError):
            problem.compile_routes()


class TraceTests(unittest.TestCase):
    def test_checkpoint_step_function(self):
        actual = score_trace(diamond(), 2, [.1, .2, .3], [(0.05, [2]), (.2, [2, 3])])
        self.assertEqual(actual['coverage_at_checkpoints'], [.5, 1, 1])
        self.assertAlmostEqual(actual['mean_checkpoint_coverage'], 5/6)

    def test_worse_and_late_values_do_not_replace_incumbent(self):
        actual = score_trace(diamond(), 2, [.1, .2], [(.01, [2]), (.04, []), (.21, [1])])
        self.assertEqual(actual['coverage_at_checkpoints'], [.5, .5])
        self.assertEqual(actual['selected'], [2])

    def test_invalid_deployments_and_timestamps(self):
        for event in [(float('nan'), [1]), (-1, []), (.1, [1, 1]), (.1, [True]), (.1, [99]), (.1, [1, 2, 3])]:
            with self.subTest(event=event), self.assertRaises(ValueError):
                score_trace(diamond(), 2, [.1], [event])
        with self.assertRaises(ValueError):
            score_trace(diamond(), 2, [.2], [(.1, [2]), (.05, [3])])
        with self.assertRaises(ValueError):
            score_trace(diamond(), 99, [.2], [])

    def test_invalid_checkpoints(self):
        for checkpoints in [[], [0], [-1], [.2, .1], [.1, .1], [True], [float('nan')], [float('inf')]]:
            with self.subTest(checkpoints=checkpoints), self.assertRaises(ValueError):
                checkpoints_checked(checkpoints)


class WorkerTests(unittest.TestCase):
    def candidate(self, source, checkpoints=(.1, .3), **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / 'test_candidate.py'
            candidate.write_text(source)
            return run_anytime(diamond(), 2, checkpoints, program_path=candidate, **kwargs)

    def test_seed_and_fixed_controls(self):
        result = run_anytime(diamond(), 2, [.1, .3], program_path=ROOT/'anytime_initial.py')
        self.assertTrue(result['correct'], result)
        self.assertEqual(result['final_coverage'], 1)
        for method in ['random', 'topk', 'greedy', 'greedy_swap']:
            self.assertTrue(run_anytime(diamond(), 2, [.1, .3], baseline=method)['correct'])

    def test_deadline_retains_incumbent(self):
        result = self.candidate('def solve(p,k,s,report,b):\n report([2])\n while True: pass\n')
        self.assertTrue(result['correct'], result)
        self.assertEqual(result['termination'], 'deadline')
        self.assertEqual(result['final_coverage'], .5)

    def test_late_better_solution_not_counted(self):
        result = self.candidate('import time\ndef solve(p,k,s,report,b):\n report([2])\n time.sleep(b+1)\n report([1])\n')
        self.assertEqual(result['final_coverage'], .5)

    def test_candidate_import_work_is_timed(self):
        result = self.candidate('import time\ntime.sleep(5)\ndef solve(p,k,s,r,b): return [1]\n')
        self.assertTrue(result['correct'])
        self.assertEqual(result['termination'], 'deadline')
        self.assertEqual(result['final_coverage'], 0)

    def test_invalid_output_is_failure(self):
        for selected in ['[99]', '[1,1]', '[True]', '[1,2,3]']:
            result = self.candidate(f'def solve(p,k,s,r,b): return {selected}\n')
            self.assertFalse(result['correct'], result)

    def test_worker_crash_is_failure_not_better_incumbent(self):
        result = self.candidate('def solve(p,k,s,r,b):\n r([1])\n raise RuntimeError("deliberate")\n')
        self.assertFalse(result['correct'])

    def test_candidate_clock_and_reward_not_accepted(self):
        result = self.candidate('import sys\ndef solve(p,k,s,r,b):\n sys.__stdout__.write(\'{"selected":[1],"score":1,"time":0}\\n\')\n sys.__stdout__.flush()\n')
        self.assertFalse(result['correct'], result)

    def test_output_limit(self):
        result = self.candidate('def solve(p,k,s,r,b):\n for _ in range(100): r([])\n', max_messages=5)
        self.assertFalse(result['correct'])
        self.assertIn('limit', result['error'])

    def test_parent_secret_not_in_environment(self):
        source = 'import os\ndef solve(p,k,s,r,b):\n assert "SWARM_TEST_SECRET" not in os.environ\n return [1]\n'
        with patch.dict('os.environ', {'SWARM_TEST_SECRET': 'not-a-real-secret'}):
            self.assertTrue(self.candidate(source)['correct'])


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        fixture = self.root/'network.json'
        fixture.write_text(json.dumps(diamond().to_dict()))
        self.record = {'id': 'a', 'source_graph': 'source-a', 'split': 'development',
                       'path': 'network.json', 'sha256': file_sha256(fixture), 'budgets': [1, 2]}
        self.suite = {'schema_version': 2, 'checkpoints_seconds': [.1,.3], 'seeds': [0], 'datasets': [self.record]}
        self.path = self.root/'suite.json'

    def tearDown(self):
        self.directory.cleanup()

    def write(self):
        self.path.write_text(json.dumps(self.suite))
        return self.path

    def test_valid_and_hash_verified(self):
        self.assertEqual(len(load_suite(self.write())[1]), 1)
        (self.root/'network.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            load_suite(self.path)

    def test_whole_source_and_identical_file_cannot_cross_splits(self):
        for same in ['source_graph', 'sha256']:
            other = dict(self.record, id='b', source_graph='b', sha256='0'*64, split='test')
            other[same] = self.record[same]
            self.suite['datasets'] = [self.record, other]
            with self.subTest(same=same), self.assertRaisesRegex(ValueError, 'crosses split'):
                load_suite(self.write())

    def test_heldout_bytes_not_read(self):
        self.suite['datasets'].append(dict(self.record,id='b',source_graph='b',sha256='0'*64,
                                           path='does-not-exist.json',split='test'))
        self.assertEqual(len(load_suite(self.write())[1]), 1)

    def test_empty_split_and_duplicate_budget_fail(self):
        with self.assertRaisesRegex(ValueError, 'no source networks'):
            load_suite(self.write(), 'test')
        self.record['budgets'] = [1,1]
        with self.assertRaises(ValueError):
            load_suite(self.write())

    def test_native_metric_artifacts_and_independent_scores(self):
        result = evaluate(ROOT/'anytime_initial.py', self.root/'results', self.write())
        self.assertAlmostEqual(result['combined_score'], 100)
        self.assertEqual(result['public']['paired_cases'], 2)
        self.assertTrue(json.loads((self.root/'results/correct.json').read_text())['correct'])
        self.assertTrue((self.root/'results/traces.json').is_file())

    def test_failure_replaces_stale_success(self):
        output = self.root/'results'
        output.mkdir()
        (output/'correct.json').write_text('{"correct":true}')
        self.record['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            evaluate(ROOT/'anytime_initial.py', output, self.write())
        self.assertFalse(json.loads((output/'correct.json').read_text())['correct'])
        self.assertEqual(json.loads((output/'metrics.json').read_text())['combined_score'], 0)


class LauncherTests(unittest.TestCase):
    def test_plan_is_no_model_calls_by_default(self):
        from run_evo import parser, plan
        # Use a small local manifest; launcher configuration itself needs no Shinka.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root/'network.json'
            fixture.write_text(json.dumps(diamond().to_dict()))
            suite = root/'suite.json'
            suite.write_text(json.dumps({'schema_version': 2, 'checkpoints_seconds': [.1],
                'seeds': [0], 'datasets': [{'id':'a', 'source_graph':'a', 'split':'development',
                    'path':'network.json', 'sha256':file_sha256(fixture), 'budgets':[1]}]}))
            args = parser().parse_args(['--suite',str(suite)])
            p = plan(args)
            self.assertFalse(p['model_calls_enabled'])
            self.assertEqual(p['db_config']['num_islands'],4)
            self.assertEqual(p['evo_config']['llm_dynamic_selection'],'ucb')
            self.assertEqual(p['evo_config']['meta_rec_interval'],10)
            args.run = True
            with self.assertRaises(ValueError):
                plan(args)
            args.models = ['mutation-a','mutation-b']
            args.meta_model = 'interpretation'
            args.novelty_model = 'novelty'
            args.embedding_model = 'embedding'
            args.max_api_cost = 1
            p = plan(args)
            self.assertEqual(p['evo_config']['meta_llm_models'],['interpretation'])
            self.assertEqual(p['evo_config']['llm_models'],['mutation-a','mutation-b'])
            args.max_api_cost = float('nan')
            with self.assertRaises(ValueError):
                plan(args)


class DataParserTests(unittest.TestCase):
    def test_parser_rejects_silent_demand_loss(self):
        from scripts.prepare_suite import parse_tntp
        network = "<NUMBER OF NODES> 2\n<NUMBER OF LINKS> 1\n<FIRST THRU NODE> 1\n<END OF METADATA>\n1 2 100 1 1;\n"
        trips = "<TOTAL OD FLOW> 5\n<END OF METADATA>\nOrigin 1\n 2 : 5;\n"
        result = parse_tntp(network,trips,'tiny')
        self.assertEqual(result['od'],[[1,2,5]])
        for broken in [trips.replace('2 : 5;','2 : 4;'),trips.replace('2 : 5;','1 : 5;'),
                       trips.replace('2 : 5;','2 : -5;'),trips+'garbage']:
            with self.subTest(broken=broken),self.assertRaises(ValueError):
                parse_tntp(network,broken,'tiny')


if __name__ == '__main__':
    unittest.main()

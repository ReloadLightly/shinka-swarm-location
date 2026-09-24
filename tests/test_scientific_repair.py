import itertools
import json
from fractions import Fraction
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from swarm_location.core import Instance, ShortestPathCoverage
from swarm_location.search import SearchProblem
from swarm_location.relabel import relabel
from swarm_location.dag_bounds import DagPartition, IntervalOracle, SCALE, verify_dag_bounds
from swarm_location.certificates import ExactCoverage
from swarm_location.anytime import run_anytime
from swarm_location.tntp_v2 import parse_documented
from evaluate_search import build_references, evaluate, family_mean

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return Instance.from_dict({'schema_version': 2, 'name': 'diamond', 'nodes': list(range(6)),
        'edges': [[0, 4, 0], [0, 2, 0], [4, 1, 0], [2, 1, 0], [1, 3, 1], [3, 5, 1], [2, 5, 2]],
        'od': [[0, 5, .1], [2, 3, .2], [4, 5, .3]], 'non_thru_nodes': [0, 5]})


class RepairTests(unittest.TestCase):
    def test_configurable_docker_memory_and_current_launcher(self):
        from swarm_location.isolation import command
        from run_evo import parser, plan
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root/'swarm_location'; package.mkdir()
            image = 'sha256:' + 'a'*64
            with patch.dict('os.environ', {'SWARM_DOCKER_IMAGE': image, 'SWARM_WORKER_MEMORY_MIB': '4096'}), patch('shutil.which', return_value='/usr/bin/docker'):
                argv, _, metadata = command(root, package)
                self.assertIn('--memory=4096m', argv)
                self.assertIn('--memory-swap=4096m', argv)
                self.assertEqual(metadata['memory_mib'], 4096)
            with patch.dict('os.environ', {'SWARM_DOCKER_IMAGE': image, 'SWARM_WORKER_MEMORY_MIB': '0'}), patch('shutil.which', return_value='/usr/bin/docker'):
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    command(root, package)
            from swarm_location.suite import file_sha256
            data = root/'network.json'; data.write_text(json.dumps(sample().to_dict()))
            suite = root/'suite.json'
            suite.write_text(json.dumps({'schema_version': 2, 'research_protocol': 'chapter-search-v2',
                'checkpoints_seconds': [.05, .2], 'seeds': [0], 'datasets': [
                    {'id': 'unit', 'source_graph': 'unit', 'split': 'development',
                     'path': data.name, 'sha256': file_sha256(data), 'budgets': [2]}]}))
            resolved = plan(parser().parse_args(['--suite', str(suite)]))
            self.assertEqual(Path(resolved['job_config']['eval_program_path']).name, 'evaluate_search.py')
            self.assertEqual(Path(resolved['evo_config']['init_program_path']).name, 'search_initial.py')
            self.assertEqual(resolved['db_config']['num_islands'], 2)
            self.assertEqual(resolved['evo_config']['num_generations'], 200)
            self.assertFalse(resolved['model_calls_enabled'])

    def test_compact_storage_preserves_counts(self):
        n = 1050
        instance = Instance.from_dict({'schema_version':1,'name':'long-chain','nodes':list(range(n)),
            'edges':[[i,i+1,1] for i in range(n-1)],'od':[[0,n-1,1]]})
        problem = SearchProblem(instance)
        self.assertEqual(problem.dags[0].counts[n-1], 1)
        self.assertEqual(problem.dags[0].predecessors[100], (99,))
        self.assertEqual(problem.score([500]), 1)
        self.assertEqual(problem.marginal_gains([])[500], 1)
        self.assertEqual(type(problem.dags[0].counts).__name__, 'CompactCounts')

    def test_zero_ties_and_relabel(self):
        instance = sample()
        oracle = ShortestPathCoverage(instance)
        self.assertEqual(oracle.dags[0].counts[5], 3)
        for seed in range(10):
            changed, mapping = relabel(instance, seed)
            alternate = ShortestPathCoverage(Instance.from_dict(changed.to_dict()))
            for selected in itertools.combinations(instance.nodes, 2):
                self.assertAlmostEqual(oracle.score(selected), alternate.score([mapping[v] for v in selected]), places=14)
            self.assertEqual(changed.non_transit, frozenset(mapping[v] for v in instance.non_transit))
            self.assertEqual(changed.name, 'anonymized-network')

    def test_zero_centroid_connector_not_cycle(self):
        data = {'schema_version': 2, 'name': 'centroids', 'nodes': [1, 2, 10],
                'edges': [[1, 10, 0], [10, 1, 0], [10, 2, 1], [2, 10, 1]],
                'od': [[1, 2, 1], [2, 1, 1]], 'first_thru_node': 10}
        oracle = ShortestPathCoverage(Instance.from_dict(data))
        self.assertEqual(oracle.score([10]), 1)
        data['schema_version'] = 1
        with self.assertRaises(ValueError):
            Instance.from_dict(data)

    def test_relevant_zero_cycle_is_rejected(self):
        data = {'schema_version': 2, 'name': 'cycle', 'nodes': [0, 1, 2, 3],
                'edges': [[0, 1, 1], [1, 2, 0], [2, 1, 0], [2, 3, 1]], 'od': [[0, 3, 1]]}
        with self.assertRaisesRegex(ValueError, 'zero-cost'):
            ShortestPathCoverage(Instance.from_dict(data))
        data['od'] = [[0, 0, 0], [0, 1, 0], [0, 3, 1]]
        data['edges'] = [[0, 3, 1], [0, 1, 1], [1, 2, 0], [2, 1, 0]]
        self.assertEqual(ShortestPathCoverage(Instance.from_dict(data)).score([3]), 1)

    def test_declared_minimum_hops_resolves_zero_cycles_and_keeps_equal_routes(self):
        # Independent simple routes: 0-1-3, 0-2-3 and 0-1-2-3 all take two
        # time units. The first two have two links; the third has three.
        data = {'schema_version': 2, 'name': 'zero-pair', 'nodes': [0, 1, 2, 3],
                'edges': [[0, 1, 1], [0, 2, 1], [1, 2, 0], [2, 1, 0],
                          [1, 3, 1], [2, 3, 1]], 'od': [[0, 3, 1]],
                'shortest_path_ties': 'min_time_min_hops'}
        instance = Instance.from_dict(data)
        oracle = ShortestPathCoverage(instance)
        self.assertEqual(oracle.dags[0].counts[3], 2)
        self.assertEqual(oracle.score([1]), .5)
        self.assertEqual(oracle.score([1, 2]), 1)
        self.assertEqual(Instance.from_dict(instance.to_dict()), instance)
        for seed in range(3):
            changed, mapping = relabel(instance, seed)
            self.assertEqual(changed.shortest_path_ties, 'min_time_min_hops')
            self.assertEqual(ShortestPathCoverage(changed).score([mapping[1]]), .5)

    def test_compact_kernel_matches_route_fraction_and_marginals(self):
        data = {'schema_version': 2, 'name': 'padded-zero-pair',
                'nodes': list(range(1050)), 'edges': [[0, 1, 1], [0, 2, 1],
                [1, 2, 0], [2, 1, 0], [1, 3, 1], [2, 3, 1]],
                'od': [[0, 3, 2]], 'shortest_path_ties': 'min_time_min_hops'}
        instance = Instance.from_dict(data)
        problem = SearchProblem(instance)
        self.assertEqual(problem.dags[0].counts[3], 2)
        self.assertEqual(problem.score([1]), .5)
        self.assertEqual(problem.marginal_gains([])[1], .5)
        self.assertEqual(problem.marginal_gains([1])[2], .5)
        self.assertEqual(problem.score_origins([1], [0]), .5)
        from swarm_location.prepared import ensure_prepared, load_prepared
        with tempfile.TemporaryDirectory() as folder:
            path, checksum, reused = ensure_prepared(instance, folder)
            self.assertFalse(reused)
            restored = load_prepared(path, checksum, instance)
            replay = SearchProblem(instance, prepared=restored)
            self.assertEqual(replay.score([1]), .5)
            self.assertEqual(replay.marginal_gains([1])[2], .5)

    def test_source_specific_zone_override_is_audited(self):
        network = ('<NUMBER OF NODES> 4\n<NUMBER OF ZONES> 2\n<FIRST THRU NODE> 1\n'
                   '<END OF METADATA>\n1 3 1 1 0 0 1 0 0 1;\n'
                   '3 1 1 1 0 0 1 0 0 1;\n3 2 1 1 1 0 1 0 0 1;\n')
        trips = '<TOTAL OD FLOW> 1\n<END OF METADATA>\nOrigin 1\n2 : 1;\n'
        data, audit = parse_documented(network, trips, 'zones', {'relative':'0','absolute':'0'},
            shortest_path_ties='min_time_min_hops', centroid_override='zones_endpoint_only')
        self.assertEqual((audit['header_first_thru_node'], audit['effective_first_thru_node']), (1, 3))
        self.assertEqual(data['first_thru_node'], 3)
        self.assertEqual(ShortestPathCoverage(Instance.from_dict(data)).score([3]), 1)
        with self.assertRaisesRegex(ValueError, 'centroid override'):
            parse_documented(network.replace('NODE> 1', 'NODE> 3'), trips, 'zones',
                             {'relative':'0','absolute':'0'}, centroid_override='zones_endpoint_only')

    def test_header_rounding_does_not_change_trip_rows(self):
        network = '<NUMBER OF NODES> 2\n<END OF METADATA>\n1 2 1 1 1 0 1 0 0 1;\n'
        trips = '<TOTAL OD FLOW> 1000000.00001\n<END OF METADATA>\nOrigin 1\n2 : 1000000;\n'
        data, audit = parse_documented(network, trips, 'rounded',
                                        {'relative':'0.000000001','absolute':'0'})
        self.assertEqual(data['od'], [[1, 2, 1000000]])
        self.assertEqual(audit['header_discrepancy_exact'], '1/100000')
        with self.assertRaisesRegex(ValueError, 'OD total'):
            parse_documented(network, trips.replace('1000000.00001', '1000000.01'),
                             'rounded', {'relative':'0.000000001','absolute':'0'})

    def test_origin_queries_partition_full_objective(self):
        problem = SearchProblem(sample())
        for selected in [[], [1], [2, 4]]:
            scores = sum(problem.score_origins(selected, [d.source]) for d in problem.dags)
            self.assertAlmostEqual(scores, problem.score(selected), places=14)
            parts = [problem.marginal_gains_origins(selected, [d.source]) for d in problem.dags]
            for v, gain in problem.marginal_gains(selected).items():
                self.assertAlmostEqual(sum(p[v] for p in parts), gain, places=14)
        with self.assertRaises(ValueError):
            problem.score_origins([], [0, 0])

    def test_outward_intervals_and_partition_bounds(self):
        instance = sample()
        exact = ExactCoverage(instance)
        interval = IntervalOracle(instance)
        for size in range(4):
            for group in itertools.combinations(instance.nodes, size):
                low, high, gains = interval.intervals(group, gains=True)
                value = exact.score(group)
                self.assertLessEqual(Fraction(low, SCALE), value)
                self.assertGreaterEqual(Fraction(high, SCALE), value)
                for v, upper in gains.items():
                    self.assertGreaterEqual(Fraction(upper, SCALE), exact.score((*group, v))-value)
        tree = DagPartition(instance, 2)
        rng = random.Random(4)
        events = [(0., tree.snapshot([]))]
        while True:
            eligible = [(i, s) for i, s in tree.leaves.items() if not s.terminal]
            for state in tree.leaves.values():
                opt = max(exact.score(state.selected + group)
                          for group in itertools.combinations(state.remaining, min(2-len(state.selected), len(state.remaining))))
                self.assertGreaterEqual(Fraction(state.upper, SCALE), opt)
            if not eligible:
                break
            parent, state = rng.choice(eligible)
            tree.split(parent, rng.choice(state.remaining))
            events.append((len(events)*.001, tree.snapshot([0, 2])))
        verified = verify_dag_bounds(instance, 2, events)
        self.assertEqual(verified[-1]['partition_splits_verified'], len(tree.ops))
        bad = json.loads(json.dumps(events))
        bad[-1][1]['upper'] = '0'
        with self.assertRaises(ValueError):
            verify_dag_bounds(instance, 2, bad)
        bad = json.loads(json.dumps(events))
        bad[1][1]['ops'][0][0] = 123456
        with self.assertRaises(ValueError):
            verify_dag_bounds(instance, 2, bad)

    def test_interrupted_split_retains_complete_partition(self):
        tree = DagPartition(sample(), 2)
        original = dict(tree.leaves)
        compute = tree.oracle.intervals
        count = 0
        def interrupted(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise TimeoutError('interrupted child')
            return compute(*args, **kwargs)
        with patch.object(tree.oracle, 'intervals', side_effect=interrupted):
            with self.assertRaises(TimeoutError):
                tree.split(0, 1)
        self.assertEqual(tree.leaves, original)
        self.assertEqual(tree.ops, [])

    def test_exponentially_many_routes_need_no_enumeration(self):
        # 2**24 routes; >80 times the old 200,000-route limit.
        layers = [[0]] + [[2*i+1, 2*i+2] for i in range(24)] + [[49]]
        edges = [[u, v, 1] for left, right in zip(layers, layers[1:]) for u in left for v in right]
        instance = Instance.from_dict({'schema_version': 1, 'name': 'path-explosion', 'nodes': list(range(50)),
                                     'edges': edges, 'od': [[0, 49, 1]]})
        with patch.object(ShortestPathCoverage, 'compile_routes', side_effect=AssertionError('must not enumerate')):
            tree = DagPartition(instance, 2)
            tree.split(0, 1)
            verified = verify_dag_bounds(instance, 2, [(0., tree.snapshot([0, 49]))])
        self.assertEqual(tree.oracle.problem.dags[0].counts[49], 2**24)
        self.assertEqual(verified[-1]['quality_lower_bound_exact'], '1')

    def test_explicit_intrazonal_exclusion_mass(self):
        network = '<NUMBER OF NODES> 2\n<FIRST THRU NODE> 1\n<END OF METADATA>\n1 2 1 1 0 0 1 0 0 1;\n2 1 1 1 1 0 1 0 0 1;\n'
        trips = '<TOTAL OD FLOW> 12\n<END OF METADATA>\nOrigin 1\n1 : 9; 2 : 3;\n'
        data, audit = parse_documented(network, trips, 'fixture', {'absolute':'0','relative':'0'}, schema_version=2, intrazonal='exclude')
        self.assertEqual(data['od'], [[1, 2, 3]])
        self.assertEqual(audit['excluded_intrazonal_demand_exact'], '9')
        self.assertEqual(audit['retained_interzonal_demand_exact'], '3')
        self.assertEqual(ShortestPathCoverage(Instance.from_dict(data)).score([1]), 1)

    def test_candidates_can_certify_and_false_certificate_fails(self):
        result = run_anytime(sample(), 2, [.05, .15, .4], program_path=ROOT/'search_initial.py', allow_candidate_bounds=True)
        self.assertTrue(result['correct'], result['error'])
        self.assertTrue(result['verified_search_bounds'])
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory)/'fake.py'
            candidate.write_text('def solve(p,k,seed,report,budget):\n report([0])\n report.bound({"kind":"dag_partition_v2","upper":"0","ops":[],"splits":0,"selected":[0]})\n')
            result = run_anytime(sample(), 2, [.05, .2], program_path=candidate, allow_candidate_bounds=True)
            self.assertFalse(result['correct'])

    def test_candidate_only_cache_and_source_balancing(self):
        from swarm_location.suite import file_sha256
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'instance.json';path.write_text(json.dumps(sample().to_dict()))
            suite = {'schema_version':2, 'research_protocol':'chapter-search-v2', 'checkpoints_seconds':[.025,.05,.1,.2],
                     'seeds':[0], 'relabel_seed':15, 'fitness':{'coverage_weight':.5,'certificate_weight':.5},
                     'controls':['greedy','program:controls/dag_potential.py'],
                     'datasets':[{'id':'example','source_graph':'family','split':'development','path':path.name,
                                  'sha256':file_sha256(path),'budgets':[2]}]}
            suite_path = root/'suite.json';suite_path.write_text(json.dumps(suite))
            cache = root/'references.json'
            build_references(suite_path, cache, trusted_local=True)
            with patch('evaluate_search.build_references', side_effect=AssertionError('must not retime controls')):
                result = evaluate(ROOT/'search_initial.py', root/'result', suite_path, cache, trusted_local=True)
            self.assertEqual(result['public']['solver_runs_this_evaluation'], 1)
            self.assertEqual(result['public']['fixed_control_runs_this_evaluation'], 0)
            self.assertGreater(result['combined_score'], 0)
            suite['fitness']['coverage_weight'] = 1
            suite['fitness']['certificate_weight'] = 0
            suite_path.write_text(json.dumps(suite))
            with self.assertRaisesRegex(ValueError, 'cache mismatch'):
                evaluate(ROOT/'search_initial.py', root/'result', suite_path, cache, trusted_local=True)
            self.assertFalse(json.loads((root/'result/correct.json').read_text())['correct'])
        self.assertEqual(family_mean([{'source_graph':'A','v':1},{'source_graph':'A','v':1},{'source_graph':'B','v':0}], 'v'), .5)


if __name__ == '__main__':
    unittest.main()

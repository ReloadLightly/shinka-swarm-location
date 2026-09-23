"""Independent small-state enumeration and proof tampering tests for diagnostics."""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
from pathlib import Path
import random
import unittest

from swarm_location.core import Instance
from swarm_location.certificates import ExactCoverage
from swarm_location.exchange_landscape import (ExchangeProblem, exchange_census,
    neutral_component, minimum_loss_escape, verify_escape)

ROOT = Path(__file__).resolve().parents[1]


def fixture(seed, n=7):
    rng = random.Random(seed)
    edges = {(u, v): rng.randint(1, 4) for u in range(1, n+1) for v in range(1, n+1)
             if u != v and (abs(u-v) == 1 or rng.random() < .35)}
    return Instance.from_dict({'schema_version': 1, 'name': f'unit-{seed}',
        'nodes': list(range(1, n+1)), 'edges': [[u, v, w] for (u, v), w in edges.items()],
        'od': [[u, v, rng.randint(1, 9)/8] for u in range(1, n+1) for v in range(1, n+1) if u != v]})


def brute_escape(oracle, k, root):
    """Independent threshold connectivity, using only rational avoiding-DAG scores."""
    groups = list(combinations(oracle.nodes, k))
    scores = {g: oracle.score(g) for g in groups}
    if max(scores.values()) <= scores[root]:
        return None
    for level in sorted({v for v in scores.values() if v <= scores[root]}, reverse=True):
        reached = {root}; todo = [root]
        while todo:
            group = todo.pop()
            if scores[group] > scores[root]:
                return scores[root]-level
            for neighbor in groups:
                if (neighbor not in reached and scores[neighbor] >= level
                        and len(set(group)-set(neighbor)) == 1):
                    reached.add(neighbor); todo.append(neighbor)
    raise AssertionError('full fixed-cardinality exchange graph should be connected')


class CensusTests(unittest.TestCase):
    def test_160_small_censuses_against_independent_full_subsets(self):
        cases = 0
        for seed in range(10):
            oracle = ExactCoverage(fixture(seed))
            for k in range(1, 5):
                groups = list(combinations(oracle.nodes, k))
                scores = {g: oracle.score(g) for g in groups}
                p = ExchangeProblem(oracle, k)
                for root in groups[:4]:
                    result = exchange_census(p, root)
                    self.assertEqual(result['total_deployments'], len(groups))
                    self.assertEqual(Fraction(result['global_optimum_units'], p.scale), max(scores.values()))
                    for row in result['spheres']:
                        values = [v for g, v in scores.items() if len(set(root)-set(g)) == row['radius']]
                        self.assertEqual(row['evaluated'], len(values))
                        self.assertEqual(row['worse'], sum(v < scores[root] for v in values))
                        self.assertEqual(row['equal'], sum(v == scores[root] for v in values))
                        self.assertEqual(row['better'], sum(v > scores[root] for v in values))
                        self.assertEqual(Fraction(row['best_units'], p.scale), max(values))
                    cases += 1
        self.assertEqual(cases, 160)

    def test_zero_and_full_budgets(self):
        o = ExactCoverage(fixture(1, 4))
        for k, root in [(0, ()), (4, o.nodes)]:
            p = ExchangeProblem(o, k)
            r = exchange_census(p, root)
            self.assertEqual(r['total_deployments'], 1)
            self.assertEqual(r['spheres'], [])
            self.assertIsNone(r['smallest_improving_radius'])
            self.assertTrue(neutral_component(p, root)['no_neutral_then_strict_single_exchange_escape_proved'])

    def test_invalid_groups_radii_and_exhaustive_size_limit(self):
        p = ExchangeProblem(ExactCoverage(fixture(2, 5)), 2)
        for group in [[1], [1, 1], [1, 6], [True, 2], [1, 2, 3]]:
            with self.assertRaises(ValueError): exchange_census(p, group)
        for radius in [0, 3, True, 1.5]:
            with self.assertRaises(ValueError): list(p.neighbors([1, 2], radius))
        with self.assertRaises(ValueError): exchange_census(p, [1, 2], max_deployments=2)
        with self.assertRaises(ValueError): exchange_census(p, [1, 2], sample_limit=0)

    def test_exact_comparisons_do_not_treat_tiny_gains_as_neutral(self):
        instance = Instance.from_dict({'schema_version': 1, 'name': 'tiny-gap',
            'nodes': [1, 2, 3], 'edges': [[1, 3, 1], [2, 3, 1]],
            'od': [[1, 3, 1.0], [2, 3, 1.0+2**-40]]})
        p = ExchangeProblem(ExactCoverage(instance), 1)
        row = exchange_census(p, [1])['spheres'][0]
        self.assertEqual(row['better'], 2)
        self.assertEqual(row['equal'], 0)

    def test_census_digest_reproducible(self):
        o = ExactCoverage(fixture(3, 5))
        self.assertEqual(exchange_census(ExchangeProblem(o, 2), [1, 2]),
                         exchange_census(ExchangeProblem(o, 2), [2, 1]))


class PlateauAndBarrierTests(unittest.TestCase):
    def test_neutral_component_limit_does_not_claim_no_escape(self):
        instance = Instance.from_dict({'schema_version': 1, 'name': 'flat',
            'nodes': [1, 2, 3], 'edges': [[1, 2, 1], [2, 3, 1]], 'od': [[1, 3, 1]]})
        p = ExchangeProblem(ExactCoverage(instance), 1)
        r = neutral_component(p, [1], max_states=1)
        self.assertFalse(r['complete'])
        self.assertFalse(r['no_neutral_then_strict_single_exchange_escape_proved'])
        full = neutral_component(p, [1])
        self.assertEqual(len(full['members']), 3)
        self.assertTrue(full['no_neutral_then_strict_single_exchange_escape_proved'])

    def test_barriers_match_independent_threshold_connectivity(self):
        for seed in range(10):
            o = ExactCoverage(fixture(seed, 6)); p = ExchangeProblem(o, 3)
            for root in list(combinations(o.nodes, 3))[:2]:
                expected = brute_escape(o, 3, root)
                result = minimum_loss_escape(p, root)
                if expected is None:
                    self.assertEqual(result['status'], 'no_better_deployment')
                else:
                    self.assertEqual(result['status'], 'proved')
                    checked = verify_escape(p, result['proof'])
                    self.assertEqual(Fraction(checked['minimum_loss_coverage_exact']), expected)

    def test_expansion_limit_is_not_a_proof(self):
        p = ExchangeProblem(ExactCoverage(fixture(4, 6)), 3)
        result = minimum_loss_escape(p, [1, 2, 3], max_expansions=1)
        self.assertEqual(result['status'], 'expansion_limit')
        self.assertIsNone(result['proof'])

    def test_zero_loss_witness(self):
        p = ExchangeProblem(ExactCoverage(fixture(1, 5)), 1)
        root = min(p.nodes, key=lambda v: p.units((v,)))
        result = minimum_loss_escape(p, [root])
        self.assertEqual(result['verification']['minimum_loss_coverage_exact'], '0')
        self.assertEqual(result['proof']['strict_superlevel_cut'], [])


class SiouxFallsRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = ExactCoverage(Instance.load(ROOT/'data/sioux_falls.json'))
        cls.p = ExchangeProblem(cls.oracle, 6)
        cls.initial = (8, 10, 11, 13, 17, 22)
        cls.result = minimum_loss_escape(cls.p, cls.initial)

    def test_complete_census_and_published_three_exchange_trap(self):
        result = exchange_census(self.p, self.initial)
        self.assertEqual(result['total_deployments'], 134596)
        self.assertEqual([r['evaluated'] for r in result['spheres']], [108, 2295, 16320, 45900, 51408, 18564])
        self.assertEqual([r['better'] for r in result['spheres']], [0, 0, 0, 1, 2, 0])
        self.assertEqual([r['equal'] for r in result['spheres']], [1, 0, 0, 0, 0, 0])
        self.assertEqual(result['smallest_improving_radius'], 4)
        self.assertEqual(result['global_optimum_units'], 9540)

    def test_neutral_single_exchange_component_closed(self):
        result = neutral_component(self.p, self.initial)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['members']), 2)
        self.assertEqual(result['strict_exit_transitions'], 0)

    def test_proved_positive_minimum_loss_and_independent_path_scores(self):
        self.assertEqual(self.result['status'], 'proved')
        checked = verify_escape(self.p, self.result['proof'])
        self.assertEqual(Fraction(checked['minimum_loss_coverage_exact']), Fraction(150, 10818))
        for group, value in zip(self.result['proof']['path'], checked['path_coverages_exact']):
            self.assertEqual(self.oracle.score(group), Fraction(value))

    def test_missing_cut_state_rejected(self):
        proof = deepcopy(self.result['proof'])
        cut = proof['strict_superlevel_cut']
        cut.remove(next(g for g in cut if tuple(g) != self.initial))
        with self.assertRaises(ValueError): verify_escape(self.p, proof)

    def test_changed_path_bottleneck_or_problem_rejected(self):
        for field, value in [('bottleneck_units', self.result['proof']['bottleneck_units']+1),
                             ('scale', 1), ('instance_sha256', 'wrong'), ('k', True)]:
            proof = deepcopy(self.result['proof']); proof[field] = value
            with self.assertRaises(ValueError): verify_escape(self.p, proof)
        proof = deepcopy(self.result['proof']); proof['path'] = proof['path'][::2]
        with self.assertRaises(ValueError): verify_escape(self.p, proof)

    def test_duplicate_cut_and_invalid_path_group_rejected(self):
        proof = deepcopy(self.result['proof'])
        proof['strict_superlevel_cut'].append(proof['strict_superlevel_cut'][0])
        with self.assertRaises(ValueError): verify_escape(self.p, proof)
        proof = deepcopy(self.result['proof']); proof['path'][1] = [1, 1, 2, 3, 4, 5]
        with self.assertRaises(ValueError): verify_escape(self.p, proof)

    def test_cut_state_limit_fails_without_certificate(self):
        with self.assertRaises(ValueError):
            minimum_loss_escape(self.p, self.initial, max_cut_states=1)


if __name__ == '__main__':
    unittest.main()

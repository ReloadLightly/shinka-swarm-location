"""Mathematical checks independent of Shinka and of external packages."""
from fractions import Fraction
from itertools import combinations
import random
import unittest

from swarm_location import Instance, ShortestPathCoverage
from swarm_location.baselines import greedy, greedy_swap, exhaustive
from initial import solve


def make(nodes, edges, od, first_thru_node=None):
    return Instance.from_dict(dict(schema_version=1, name='test', nodes=nodes,
                                   edges=edges, od=od, first_thru_node=first_thru_node))


def independent_routes(instance):
    """Enumerate ALL simple paths, then apply the declared route convention.

    Does not use the production shortest-path algorithm or its predecessor DAG.
    """
    adjacency = {v: [] for v in instance.nodes}
    for u, v, w in instance.edges:
        adjacency[u].append((v, w))
    non_transit = (set(instance.non_thru_nodes) if instance.non_thru_nodes is not None
                   else {n for n in instance.nodes
                         if instance.first_thru_node is not None and n < instance.first_thru_node})
    weighted = []
    total = sum(q for _, _, q in instance.od)
    for source, target, demand in instance.od:
        if not demand:
            continue
        paths = []
        stack = [(source, (source,), Fraction(0))]
        while stack:
            v, path, length = stack.pop()
            if v == target:
                key = ((length, len(path) - 1)
                       if instance.shortest_path_ties == 'min_time_min_hops' else length)
                paths.append((key, set(path)))
                continue
            if v != source and v in non_transit:
                continue
            for u, w in adjacency[v]:
                if u not in path:
                    stack.append((u, (*path, u), length + w))
        distance = min(length for length, _ in paths)
        shortest = [p for length, p in paths if length == distance]
        weighted.extend((p, demand / total / len(shortest)) for p in shortest)
    return weighted


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.instance = make([1, 2, 3, 4], [(1, 2, 1), (1, 3, 1), (2, 4, 1), (3, 4, 1)], [(1, 4, 10)])
        self.problem = ShortestPathCoverage(self.instance)

    def test_empty(self):
        self.assertEqual(self.problem.score([]), 0)

    def test_endpoints(self):
        self.assertEqual(self.problem.score([1]), 1)
        self.assertEqual(self.problem.score([4]), 1)

    def test_ties_and_overlap(self):
        self.assertEqual(self.problem.score([2]), 0.5)
        self.assertEqual(self.problem.score([2, 3]), 1)
        self.assertEqual(self.problem.score([1, 2, 3, 4]), 1)

    def test_path_not_branch_uniformity(self):
        inst = make(list(range(1, 7)), [(1, 2, 1), (1, 3, 2), (2, 4, 1), (2, 5, 1),
                    (4, 6, 1), (5, 6, 1), (3, 6, 1)], [(1, 6, 1)])
        self.assertAlmostEqual(ShortestPathCoverage(inst).score([3]), 1 / 3)

    def test_exact_decimal_ties(self):
        inst = make([1, 2, 3], [(1, 2, '0.1'), (2, 3, '0.2'), (1, 3, '0.3')], [(1, 3, 1)])
        self.assertEqual(ShortestPathCoverage(inst).score([2]), 0.5)

    def test_nearly_equal_is_not_equal(self):
        inst = make([1, 2, 3], [(1, 2, '0.1'), (2, 3, '0.2'), (1, 3, '0.30000000001')], [(1, 3, 1)])
        self.assertEqual(ShortestPathCoverage(inst).score([2]), 1)

    def test_no_rerouting(self):
        inst = make([1, 2, 3, 4], [(1, 2, 1), (2, 4, 1), (1, 3, 5), (3, 4, 5)], [(1, 4, 1)])
        problem = ShortestPathCoverage(inst)
        self.assertEqual(problem.score([2]), 1)
        self.assertEqual(problem.score([3]), 0)

    def test_weighted_demand_and_direction(self):
        inst = make([1, 2, 3], [(1, 2, 1), (2, 3, 1), (3, 1, 1)], [(1, 3, 9), (3, 1, 1)])
        self.assertEqual(ShortestPathCoverage(inst).score([2]), 0.9)

    def test_unreachable_positive_demand(self):
        with self.assertRaises(ValueError):
            ShortestPathCoverage(make([1, 2], [(1, 2, 1)], [(2, 1, 1)]))

    def test_zero_demand_unreachable_is_ignored(self):
        inst = make([1, 2], [(1, 2, 1)], [(1, 2, 1), (2, 1, 0)])
        self.assertEqual(ShortestPathCoverage(inst).score([1]), 1)

    def test_centroid_not_intermediate(self):
        inst = make([1, 2, 3, 4], [(1, 2, 1), (2, 4, 1), (1, 3, 2), (3, 4, 2)], [(1, 4, 1)], 3)
        problem = ShortestPathCoverage(inst)
        self.assertEqual(problem.score([2]), 0)
        self.assertEqual(problem.score([3]), 1)

    def test_invalid_edges(self):
        for edges in [[(1, 2, 0)], [(1, 2, -1)], [(1, 1, 1)], [(1, 3, 1)], [(1, 2, 1), (1, 2, 2)]]:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                make([1, 2], edges, [(1, 2, 1)])

    def test_invalid_od(self):
        for od in [[(1, 2, -1)], [(1, 1, 1)], [(1, 2, 0)], [(1, 2, float('nan'))], [(1, 3, 1)], [(1, 2, 1), (1, 2, 1)]]:
            with self.subTest(od=od), self.assertRaises(ValueError):
                make([1, 2], [(1, 2, 1)], od)

    def test_invalid_selections(self):
        for selection in [[1, 1], [9], [True], [1.0], ['1']]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.problem.score(selection)

    def test_invalid_budget(self):
        for k in [-1, 5, True, 1.5]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                self.instance.validate_budget(k)
        with self.assertRaises(ValueError):
            self.instance.validate_selection([1, 2], 1)

    def test_roundtrip(self):
        self.assertEqual(Instance.from_dict(self.instance.to_dict()), self.instance)

    def test_route_limit_does_not_sample(self):
        with self.assertRaises(ValueError):
            self.problem.compile_routes(max_routes=1)

    def test_exponential_paths_stay_compact(self):
        edges = [(0, 1, 1), (0, 2, 1)]
        for layer in range(1, 26):
            edges += [(u, v, 1) for u in [2 * layer - 1, 2 * layer] for v in [2 * layer + 1, 2 * layer + 2]]
        edges += [(51, 53, 1), (52, 53, 1)]
        problem = ShortestPathCoverage(make(list(range(54)), edges, [(0, 53, 1)]))
        self.assertEqual(problem.dags[0].counts[53], 2 ** 26)
        self.assertEqual(problem.score([1]), 0.5)
        with self.assertRaises(ValueError):
            problem.compile_routes()

    def test_all_subsets_against_independent_enumeration(self):
        for seed in range(10):
            rng = random.Random(seed)
            n = 6
            edges = {(v, (v + 1) % n): rng.randint(1, 4) for v in range(n)}
            edges.update({(u, v): rng.randint(1, 4) for u in range(n) for v in range(n) if u != v and rng.random() < 0.25})
            inst = make(list(range(n)), [(u, v, w) for (u, v), w in edges.items()],
                        [(s, t, rng.randint(1, 9)) for s in range(n) for t in range(n) if s != t])
            dag = ShortestPathCoverage(inst)
            fast = dag.compile_routes()
            routes = independent_routes(inst)
            values = {}
            for k in range(n + 1):
                for selected in combinations(inst.nodes, k):
                    expected = sum(q for path, q in routes if path.intersection(selected))
                    self.assertAlmostEqual(dag.score(selected), expected, places=12)
                    self.assertAlmostEqual(fast.score(selected), expected, places=12)
                    values[frozenset(selected)] = expected
            # Every one-step extension must be monotone on each tested graph.
            for selected, value in values.items():
                for v in set(inst.nodes) - selected:
                    self.assertGreaterEqual(values[selected | {v}] + 1e-12, value)
            for k in range(n + 1):
                self.assertEqual(solve(fast, k), greedy(fast, k))
                self.assertGreaterEqual(fast.score(exhaustive(fast, k)) + 1e-12, fast.score(greedy_swap(fast, k)))
                self.assertGreaterEqual(fast.score(greedy_swap(fast, k)) + 1e-12, fast.score(greedy(fast, k)))


if __name__ == '__main__':
    unittest.main()

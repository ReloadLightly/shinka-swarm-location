"""Scalable, independently replayable branch-partition certificates.

No route enumeration. Fixed-point directed rounding bounds exact rational
coverage/gains from the loaded OD weights. Rounding is outward at EVERY division;
integers (not a floating tolerance) establish admissibility. This representation
supports arbitrary branch/frontier policies; it does not prescribe search order.
"""
from dataclasses import dataclass
from fractions import Fraction
import heapq
from math import isfinite

from .core import ShortestPathCoverage

SCALE = 1 << 60


def ceil_div(a, b):
    return -(-a // b)


class IntervalOracle:
    def __init__(self, instance, problem=None):
        self.instance = instance
        self.problem = problem if problem is not None else ShortestPathCoverage(instance)
        if self.problem.instance != instance:
            raise ValueError("oracle instance mismatch")
        # Match ExactCoverage: floats denote their loaded binary rational values.
        # Decimal string reinterpretation can round below a true marginal gain.
        total = sum((Fraction(q) for _, _, q in instance.od), Fraction())
        self.units = {}
        for s, t, q in instance.od:
            if q:
                mass = Fraction(q) / total * SCALE
                self.units[s, t] = (mass.numerator // mass.denominator,
                                    ceil_div(mass.numerator, mass.denominator))

    def intervals(self, selected, *, gains=False):
        selected = set(self.instance.validate_selection(selected))
        lower, upper = 0, 0
        additions = {v: 0 for v in self.instance.nodes if v not in selected} if gains else None
        for dag in self.problem.dags:
            avoid = {}
            for v in dag.order:
                avoid[v] = (0 if v in selected else 1 if v == dag.source else
                            sum(avoid[u] for u in dag.predecessors[v]))
            dependency = {}
            for t, _ in dag.destinations:
                lo, hi = self.units[dag.source, t]
                hit, count = dag.counts[t] - avoid[t], dag.counts[t]
                lower += lo * hit // count
                upper += ceil_div(hi * hit, count)
                if gains:
                    dependency[t] = hi
            if gains:
                for v in reversed(dag.order):
                    if v in selected:
                        continue
                    mass = dependency.get(v, 0)
                    additions[v] += ceil_div(avoid[v] * mass, dag.counts[v])
                    for u in dag.predecessors[v]:
                        if u not in selected:
                            dependency[u] = dependency.get(u, 0) + ceil_div(mass * dag.counts[u], dag.counts[v])
        return lower, min(SCALE, upper), additions


@dataclass(frozen=True)
class Node:
    selected: tuple
    remaining: tuple
    upper: int
    terminal: bool
    lower: int


class DagPartition:
    """A complete partition of feasible subsets, including closed/pruned leaves.

    A split becomes visible only after BOTH children are bounded. Search policies
    choose any live parent and any remaining NODE ID. They may use other search
    procedures in parallel and may ignore this helper altogether. No split-count,
    frontier-size or route-enumeration cap is imposed here.
    """
    def __init__(self, instance, k, problem=None):
        instance.validate_budget(k)
        self.oracle = IntervalOracle(instance, problem)
        self.k = k
        self.leaves = {0: self._node((), tuple(sorted(instance.nodes)), SCALE)}
        self.heap = [(-self.leaves[0].upper, 0)]
        self.ops = []
        self.sent = 0
        self.next_id = 1

    def _node(self, selected, remaining, inherited):
        slots = self.k - len(selected)
        if slots < 0:
            raise ValueError("cardinality exceeded")
        if slots == 0 or len(remaining) <= slots:
            group = selected if slots == 0 else selected + remaining
            lower, upper, _ = self.oracle.intervals(group)
            return Node(selected, remaining, min(inherited, upper), True, lower)
        lower, upper, gains = self.oracle.intervals(selected, gains=True)
        upper = min(inherited, SCALE, upper + sum(heapq.nlargest(slots, (gains[v] for v in remaining))))
        return Node(selected, remaining, upper, False, lower)

    def split(self, parent, node_id):
        if type(parent) is not int or type(node_id) is not int or parent not in self.leaves:
            raise ValueError("unknown partition parent or noninteger split")
        node = self.leaves[parent]
        if node.terminal or node_id not in node.remaining:
            raise ValueError("terminal node or invalid split variable")
        rest = tuple(v for v in node.remaining if v != node_id)
        children = (self._node(node.selected + (node_id,), rest, node.upper),
                    self._node(node.selected, rest, node.upper))
        # Never delete a subtree while an interrupted expansion is incomplete.
        del self.leaves[parent]
        ids = (self.next_id, self.next_id + 1)
        for index, child in zip(ids, children):
            self.leaves[index] = child
            heapq.heappush(self.heap, (-child.upper, index))
        self.next_id += 2
        self.ops.append([parent, node_id])
        return ids

    def upper(self):
        while self.heap and self.heap[0][1] not in self.leaves:
            heapq.heappop(self.heap)
        return -self.heap[0][0]

    def snapshot(self, selected):
        self.oracle.instance.validate_selection(selected, self.k)
        result = {"kind": "dag_partition_v2", "ops": self.ops[self.sent:],
                  "splits": len(self.ops), "selected": list(selected),
                  "upper": str(Fraction(self.upper(), SCALE))}
        self.sent = len(self.ops)
        return result


def verify_dag_bounds(instance, k, events, problem=None):
    """Recompute every partition split against evaluator-owned graph and demand."""
    partition = None
    oracle = None
    previous_time, previous_upper = -1., Fraction(1)
    verified = []
    for elapsed, event in events:
        if isinstance(elapsed, bool) or not isfinite(elapsed) or elapsed < 0 or elapsed < previous_time:
            raise ValueError("invalid external timestamp")
        previous_time = elapsed
        if not isinstance(event, dict):
            raise ValueError("malformed certificate")
        selected = instance.validate_selection(event.get("selected", []), k)
        claimed = event.get("upper")
        if isinstance(claimed, bool) or not isinstance(claimed, (int, str)):
            raise ValueError("upper bound must be a rational string or integer")
        claimed = Fraction(claimed)
        if event.get("kind") == "universal_v1":
            if partition is not None or event.get("ops") or claimed != (1 if k else 0):
                raise ValueError("invalid universal bound")
            oracle = oracle or IntervalOracle(instance, problem)
        elif event.get("kind") == "dag_partition_v2":
            if partition is None:
                partition = DagPartition(instance, k, problem)
                oracle = partition.oracle
            ops = event.get("ops")
            if not isinstance(ops, list):
                raise ValueError("missing split journal")
            for op in ops:
                if not isinstance(op, list) or len(op) != 2:
                    raise ValueError("malformed split operation")
                partition.split(*op)
            if type(event.get("splits")) is not int or event["splits"] != len(partition.ops):
                raise ValueError("split count mismatch")
            if claimed < Fraction(partition.upper(), SCALE):
                raise ValueError("claimed bound is tighter than the replayed partition")
        else:
            raise ValueError("unknown DAG certificate kind")
        low, _, _ = oracle.intervals(selected)
        low = Fraction(low, SCALE)
        if not 0 <= low <= claimed <= previous_upper:
            raise ValueError("invalid or increasing upper bound")
        previous_upper = claimed
        verified.append({"received_seconds": elapsed, "upper_exact": str(claimed),
                         "feasible_coverage_lower_exact": str(low),
                         "quality_lower_bound_exact": str(low / claimed if claimed else Fraction(1)),
                         "selected": list(selected), "optimality_proved": low == claimed,
                         "partition_splits_verified": 0 if partition is None else len(partition.ops),
                         "arithmetic": "outward-rounded dyadic intervals; not sampled routes"})
    return verified

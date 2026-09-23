"""Timed, guarded exact-route interface for fixed controls and candidate reuse.

No route is sampled. Loaded float demand is represented by its exact binary
rational, as in certificates.py. Construction uses the already prepared original
DAGs and belongs INSIDE the search budget. This is not a cached optimum service.
"""
from fractions import Fraction
from functools import lru_cache
from math import lcm
from time import perf_counter

MAX_ROUTES = 20_000
MAX_VISITS = 1_000_000
MAX_SCALE_BITS = 4096


class RouteLimit(ValueError):
    """Exact representation is too large; use the unchanged DAG solver."""


class SearchDeadline(Exception):
    """Advisory deadline; the parent independently enforces the hard deadline."""


def check_time(deadline):
    if perf_counter() >= deadline:
        raise SearchDeadline()


class RouteSearch:
    def __init__(self, problem, *, deadline=float('inf'), max_routes=MAX_ROUTES,
                 max_visits=MAX_VISITS):
        if type(max_routes) is not int or not 1 <= max_routes <= MAX_ROUTES:
            raise ValueError('route limit must be in [1, 20000]')
        if type(max_visits) is not int or not 1 <= max_visits <= MAX_VISITS:
            raise ValueError('positive route traversal limit required')
        self.instance = problem.instance
        self.nodes = tuple(sorted(problem.nodes))
        self.index = {v:i for i,v in enumerate(self.nodes)}
        self.raw_routes = sum(d.counts[t] for d in problem.dags for t,_ in d.destinations)
        if self.raw_routes > max_routes:
            raise RouteLimit('exact shortest-route count exceeds guard')
        demands = {(s,t):Fraction(q) for s,t,q in self.instance.od if q > 0}
        total = sum(demands.values(), Fraction())
        masses, visits = {}, 0
        for dag in problem.dags:
            check_time(deadline)
            for target,_ in dag.destinations:
                weight = demands[dag.source,target] / dag.counts[target] / total
                stack = [(target, 1 << self.index[target])]
                while stack:
                    visits += 1
                    if visits > max_visits:
                        raise RouteLimit('exact route traversal exceeds guard')
                    if visits % 256 == 0:
                        check_time(deadline)
                    v, mask = stack.pop()
                    if v == dag.source:
                        masses[mask] = masses.get(mask, Fraction()) + weight
                    else:
                        stack.extend((u,mask | (1 << self.index[u])) for u in dag.predecessors[v])
        self.routes = tuple(sorted(masses.items()))
        if sum(masses.values(), Fraction()) != 1:
            raise ArithmeticError('route mass does not sum exactly to one')
        self.scale = 1
        for _,mass in self.routes:
            self.scale = lcm(self.scale,mass.denominator)
            if self.scale.bit_length() > MAX_SCALE_BITS:
                raise RouteLimit('integer mass scale exceeds guard')
        self.weights = tuple(int(mass*self.scale) for _,mass in self.routes)
        covers = [0]*len(self.nodes)
        for j,(mask,_) in enumerate(self.routes):
            if j % 256 == 0:
                check_time(deadline)
            while mask:
                bit = mask & -mask
                covers[bit.bit_length()-1] |= 1 << j
                mask ^= bit
        self.covers = tuple(covers)
        self.all_routes = (1 << len(self.routes))-1
        self.weight_calls = 0
        self.weight = lru_cache(maxsize=8192)(self._weight)
        self.visits = visits
        check_time(deadline)

    def _weight(self,bits):
        self.weight_calls += 1
        value = 0
        while bits:
            bit = bits & -bits
            value += self.weights[bit.bit_length()-1]
            bits ^= bit
        return value

    def covered(self,selected):
        mask=0
        for i in selected:
            mask |= self.covers[i]
        return mask

    def score(self,selected):
        return self.weight(self.covered(selected))

    def ids(self,selected):
        return sorted(self.nodes[i] for i in selected)

    def indices(self,selected):
        return tuple(self.index[v] for v in self.instance.validate_selection(selected))

    def gains(self,covered,remaining):
        uncovered = self.all_routes & ~covered
        return [(self.weight(self.covers[v] & uncovered),v) for v in remaining]

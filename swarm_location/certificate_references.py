"""Optional proof-producing small-instance search and exactly checked LP bounds.

Reference calculations only. Neither replaces the external scorer, enters its
mutable region, nor receives credit under its search-time fitness. The search
is a project DFBnB implementation, not the chapter authors' recovered program.
"""
from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
from math import isfinite, lcm
from time import perf_counter

from .certificates import ExactCoverage, MODEL, rational


class _IntegerRoutes:
    def __init__(self, oracle: ExactCoverage, max_routes: int = 200_000):
        self.oracle = oracle
        routes = oracle.exact_routes(max_routes)
        self.scale = 1
        for _, weight in routes:
            self.scale = lcm(self.scale, weight.denominator)
            if self.scale.bit_length() > 8192:
                raise ValueError('reference integer scale exceeds 8192 bits; use DAG bounds')
        self.weights = tuple(int(w * self.scale) for _, w in routes)
        self.covers = tuple(sum(1 << j for j, (mask, _) in enumerate(routes) if mask & (1 << v))
                            for v in range(len(oracle.nodes)))
        self.all_routes = (1 << len(routes)) - 1
        self.weight = lru_cache(maxsize=20_000)(self._weight)

    def _weight(self, bits: int) -> int:
        result = 0
        while bits:
            bit = bits & -bits
            result += self.weights[bit.bit_length() - 1]
            bits ^= bit
        return result

    def group_score(self, group: tuple[int, ...]) -> int:
        covered = 0
        for v in group:
            covered |= self.covers[v]
        return self.weight(covered)

    def inspect(self, state, k):
        selected, remaining, uncovered, value, inherited = state
        slots = k - len(selected)
        if not slots or not remaining:
            return value, (), True
        if len(remaining) <= slots:
            covered = 0
            for v in remaining:
                covered |= self.covers[v]
            return value + self.weight(covered & uncovered), (), True
        gains = sorted(((self.weight(self.covers[v] & uncovered), v) for v in remaining),
                       key=lambda t: (-t[0], t[1]))
        upper = min(inherited, value + sum(g for g, _ in gains[:slots]))
        return upper, gains, False


def branch_bound(oracle: ExactCoverage, k: int, initial=(), *, max_expansions: int = 100_000,
                 max_nodes: int = 32, max_routes: int = 200_000) -> dict:
    """Deterministic expansion-limited DFBnB, with a replayable partition proof.

    A nonnegative proof token splits on that node INDEX; -1 closes a subtree
    with its admissible bound. All feasible subsets are covered by the binary
    partition, including unexpanded frontier leaves when the work limit is hit.
    The independent verifier derives each leaf bound; scalar claims alone have
    no evidentiary value. No time-to-solution claim excludes preparation silently.
    """
    started = perf_counter()
    oracle.instance.validate_budget(k)
    group = oracle.instance.validate_selection(initial, k)
    if type(max_nodes) is not int or not 1 <= max_nodes <= 64 or len(oracle.nodes) > max_nodes:
        raise ValueError('small-instance node limit exceeded')
    if type(max_expansions) is not int or not 0 <= max_expansions <= 1_000_000:
        raise ValueError('expansion limit must be in [0, 1000000]')
    problem = _IntegerRoutes(oracle, max_routes)
    indices = {v: i for i, v in enumerate(oracle.nodes)}
    best_group = tuple(indices[v] for v in group)
    best = problem.group_score(best_group)
    prep_seconds = perf_counter() - started
    stack = [((), tuple(range(len(oracle.nodes))), problem.all_routes, 0, problem.scale)]
    tokens, expanded, frontier, leaves = [], 0, 0, 0
    while stack:
        state = stack.pop()
        selected, remaining, uncovered, value, inherited = state
        if expanded >= max_expansions:
            # Each pending subtree remains in the full proof, never discarded.
            tokens.extend([-1] * (1 + len(stack)))
            frontier = 1 + len(stack)
            stack.clear()
            break
        upper, gains, terminal = problem.inspect(state, k)
        if value > best:
            best, best_group = value, selected
        if terminal:
            candidate = selected + remaining if len(selected) + len(remaining) <= k else selected
            candidate_value = problem.group_score(candidate)
            if candidate_value > best:
                best, best_group = candidate_value, candidate
            tokens.append(-1)
            leaves += 1
        elif upper <= best:
            tokens.append(-1)
            leaves += 1
        else:
            gain, v = gains[0]
            tokens.append(v)
            expanded += 1
            rest = tuple(x for x in remaining if x != v)
            stack.append((selected, rest, uncovered, value, upper))
            stack.append((selected + (v,), rest, uncovered & ~problem.covers[v], value + gain, upper))
    witness = {'kind': 'branch_partition', 'model': MODEL, 'instance_sha256': oracle.identity,
               'k': k, 'tokens': tokens, 'feasible_selected': sorted(oracle.nodes[v] for v in best_group),
               'max_routes': max_routes}
    verify_started = perf_counter()
    upper = verify_reference_bound(oracle, k, witness)
    lower = oracle.score(witness['feasible_selected'])
    if lower > upper:
        raise ArithmeticError('branch proof is below its feasible solution')
    witness.update(upper_bound=str(upper), lower_bound=str(lower),
                   optimality_proved=upper == lower,
                   diagnostics={'expanded_nodes': expanded, 'closed_leaves': leaves,
                                'frontier_leaves_at_limit': frontier,
                                'max_expansions': max_expansions,
                                'preparation_seconds': prep_seconds,
                                'independent_verification_seconds': perf_counter() - verify_started,
                                'total_seconds_including_preparation_and_verification': perf_counter() - started})
    return witness


def verify_reference_bound(oracle: ExactCoverage, k: int, witness: dict) -> Fraction:
    """Independent proof replay / rational dual feasibility, not solver trust."""
    limit = witness.get('max_routes', 200_000)
    if type(limit) is not int or not 1 <= limit <= 200_000:
        raise ValueError('invalid reference route limit')
    if witness['kind'] == 'route_dual':
        routes = oracle.exact_routes(limit)
        entries = witness.get('alpha')
        if not isinstance(entries, list) or len(entries) != len(routes):
            raise ValueError('dual route dimension mismatch')
        loads, remainder = [Fraction() for _ in oracle.nodes], Fraction()
        for (mask, weight), entry in zip(routes, entries):
            alpha = rational(entry)
            if not 0 <= alpha <= weight:
                raise ValueError('dual coefficients must be in [0, route weight]')
            remainder += weight - alpha
            for index in range(len(oracle.nodes)):
                if mask & (1 << index):
                    loads[index] += alpha
        return min(Fraction(1), k * max(loads) + remainder) if k else Fraction()
    if witness['kind'] != 'branch_partition' or len(oracle.nodes) > 64:
        raise ValueError('unsupported reference proof')
    tokens = witness.get('tokens')
    if not isinstance(tokens, list) or not 1 <= len(tokens) <= 2_000_001:
        raise ValueError('missing or excessive partition proof')
    p = _IntegerRoutes(oracle, limit)
    # The verifier does not use solver incumbents, pruning choices, scores, or
    # counters. It checks a complete include/exclude partition and bounds leaves.
    stack = [((), tuple(range(len(oracle.nodes))), p.all_routes, 0, p.scale)]
    global_upper = 0
    for token in tokens:
        if not stack or type(token) is not int:
            raise ValueError('extra or malformed partition token')
        selected, remaining, uncovered, value, inherited = stack.pop()
        slots = k - len(selected)
        if slots < 0:
            raise ValueError('partition exceeded cardinality')
        if not slots or not remaining:
            upper = value
        elif len(remaining) <= slots:
            union = 0
            for index in remaining:
                union |= p.covers[index]
            upper = value + p.weight(union & uncovered)
        else:
            gains = [p.weight(p.covers[index] & uncovered) for index in remaining]
            upper = min(inherited, value + sum(sorted(gains, reverse=True)[:slots]))
        if token == -1:
            global_upper = max(global_upper, upper)
        else:
            if not slots or token not in remaining:
                raise ValueError('invalid split variable')
            rest = tuple(i for i in remaining if i != token)
            gain = p.weight(p.covers[token] & uncovered)
            stack.append((selected, rest, uncovered, value, upper))
            stack.append((selected + (token,), rest, uncovered & ~p.covers[token], value + gain, upper))
    if stack:
        raise ValueError('truncated proof leaves feasible subtrees unaccounted for')
    return Fraction(global_upper, p.scale)


def lp_bound(oracle: ExactCoverage, k: int, *, seconds: float = 15.0,
             max_routes: int = 200_000) -> dict:
    """Optional SciPy proposal of dual coefficients; exact verification is required.

    For alpha_p in [0,w_p], lambda=max_v sum_{p contains v} alpha_p is feasible
    for the coverage relaxation dual. U=k*lambda+sum_p(w_p-alpha_p) is an upper
    bound regardless of numerical solver tolerances. No MILP claim is needed.
    """
    oracle.instance.validate_budget(k)
    if isinstance(seconds, bool) or not isfinite(seconds) or seconds <= 0:
        raise ValueError('positive finite LP time limit required')
    import numpy as np
    import scipy
    from scipy.optimize import linprog
    from scipy.sparse import coo_matrix, csr_matrix, eye, hstack, vstack

    started = perf_counter()
    routes = oracle.exact_routes(max_routes)
    m, n = len(routes), len(oracle.nodes)
    rr, cc = [], []
    for r, (mask, _) in enumerate(routes):
        for v in range(n):
            if mask & (1 << v):
                rr.append(r)
                cc.append(v)
    incidence = coo_matrix((np.ones(len(rr)), (rr, cc)), shape=(m, n)).tocsr()
    matrix = vstack([hstack([-incidence, eye(m)]), csr_matrix([[1] * n + [0] * m])], format='csr')
    result = linprog(np.r_[np.zeros(n), -np.array([float(w) for _, w in routes])],
                     A_ub=matrix, b_ub=np.r_[np.zeros(m), k],
                     bounds=[(0, None)] * n + [(0, 1)] * m,
                     method='highs', options={'time_limit': seconds})
    if not result.success or result.ineqlin.marginals is None:
        raise RuntimeError(f'LP bound proposal unavailable (solver status {result.status}); use DAG bound')
    # Clipping is a construction step. Verification NEVER repairs a received proof.
    alpha = [min(w, max(Fraction(), Fraction(float(-v)).limit_denominator(10**9)))
             for (_, w), v in zip(routes, result.ineqlin.marginals[:m])]
    witness = {'kind': 'route_dual', 'model': MODEL, 'instance_sha256': oracle.identity,
               'k': k, 'alpha': [str(a) for a in alpha], 'max_routes': max_routes,
               'diagnostics': {'proposal_solver': 'scipy.linprog/highs', 'scipy': scipy.__version__,
                               'solver_status': int(result.status),
                               'solver_objective_is_not_the_certificate': True}}
    upper = verify_reference_bound(oracle, k, witness)
    # A second rational reconstruction may be tighter, but is accepted only after
    # the same complete exact verification. It is never an LP tolerance shortcut.
    lattice = 1
    for _, w in routes:
        lattice = lcm(lattice, w.denominator)
        if lattice.bit_length() > 1024:
            break
    if lattice.bit_length() <= 1024:
        snapped = [min(w, max(Fraction(), Fraction(float(-v * lattice)).limit_denominator(10**4) / lattice))
                   for (_, w), v in zip(routes, result.ineqlin.marginals[:m])]
        alternative = dict(witness, alpha=[str(a) for a in snapped])
        other_upper = verify_reference_bound(oracle, k, alternative)
        if other_upper < upper:
            witness, upper = alternative, other_upper
    witness['upper_bound'] = str(upper)
    witness['diagnostics']['total_seconds_including_exact_verification'] = perf_counter() - started
    return witness

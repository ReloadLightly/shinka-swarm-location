"""Exact, independently recomputable quality bounds for the fixed-route model.

This is post-processing, never evolutionary fitness or candidate-supplied proof.
Demand is the exact rational value of the already loaded Instance's numbers;
float inputs use their binary values, with no decimal reinterpretation. Coverage
and bounds are rational. The existing floating-point scorer remains unchanged.
"""
from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
from typing import Iterable

from .core import Instance, ShortestPathCoverage

MODEL = 'fixed-directed-shortest-routes/endpoints/loaded-demand-rationals/v1'


def rational(value: object) -> Fraction:
    """Read exact certificate numbers; never silently accept float proof fields."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ValueError('proof numbers must be rational strings or integers')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('invalid rational proof number') from exc


def decimal_bound(value: Fraction, places: int = 6, *, upper: bool = False) -> str:
    """Decimal display with directed rounding, not an overstated guarantee."""
    if type(places) is not int or not 0 <= places <= 20:
        raise ValueError('places must be an integer from 0 to 20')
    scale = 10 ** places
    scaled = value * scale
    integer = (-((-scaled.numerator) // scaled.denominator) if upper
               else scaled.numerator // scaled.denominator)
    sign = '-' if integer < 0 else ''
    integer = abs(integer)
    return f'{sign}{integer // scale}' + (f'.{integer % scale:0{places}d}' if places else '')


class ExactCoverage:
    """Exact score and gains on existing shortest-path DAGs; no route enumeration.

    Rational demand propagation costs more than the production float backend.
    Call after timed execution. One source-DAG interface is built and reused.
    """
    def __init__(self, instance: Instance):
        self.instance = instance
        self.oracle = ShortestPathCoverage(instance)
        self.nodes = tuple(sorted(instance.nodes))
        self.demands = {(s, t): Fraction(q) for s, t, q in instance.od if q > 0}
        self.total = sum(self.demands.values(), Fraction())
        canonical = {'model': MODEL, 'nodes': sorted(instance.nodes),
                     'edges': sorted((u, v, str(w)) for u, v, w in instance.edges),
                     'od': sorted((s, t, str(Fraction(q))) for s, t, q in instance.od),
                     'first_thru_node': instance.first_thru_node}
        if instance.non_thru_nodes is not None or instance.allow_zero_weights:
            canonical.update(non_thru_nodes=instance.non_thru_nodes, allow_zero_weights=instance.allow_zero_weights)
        # Preserve historical time-only identities, but never allow a witness
        # for that route population to masquerade as a fewest-links witness.
        if instance.shortest_path_ties != 'all_min_time':
            canonical['shortest_path_ties'] = instance.shortest_path_ties
        self.identity = sha256(json.dumps(canonical, sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()
        self._score_cache: dict[tuple[int, ...], Fraction] = {}
        self._gains_cache: dict[tuple[int, ...], tuple[Fraction, dict[int, Fraction]]] = {}
        self._routes: tuple[tuple[int, Fraction], ...] | None = None
        self._verified_bounds: dict[tuple[int, str], Fraction] = {}

    def _avoiding(self, dag, selected: set[int]) -> dict[int, int]:
        avoid = {}
        for v in dag.order:
            avoid[v] = (0 if v in selected else 1 if v == dag.source else
                        sum(avoid[u] for u in dag.predecessors[v]))
        return avoid

    def score(self, selected: Iterable[int]) -> Fraction:
        key = self.instance.validate_selection(selected)
        if key not in self._score_cache:
            group, value = set(key), Fraction()
            for dag in self.oracle.dags:
                avoid = self._avoiding(dag, group)
                for t, _ in dag.destinations:
                    value += self.demands[dag.source, t] * Fraction(
                        dag.counts[t] - avoid[t], dag.counts[t])
            self._score_cache[key] = value / self.total
        return self._score_cache[key]

    def score_and_gains(self, selected: Iterable[int]) -> tuple[Fraction, dict[int, Fraction]]:
        key = self.instance.validate_selection(selected)
        if key not in self._gains_cache:
            group = set(key)
            gains = {v: Fraction() for v in self.nodes if v not in group}
            score = Fraction()
            for dag in self.oracle.dags:
                avoid = self._avoiding(dag, group)
                demand = {t: self.demands[dag.source, t] for t, _ in dag.destinations}
                for t, q in demand.items():
                    score += q * Fraction(dag.counts[t] - avoid[t], dag.counts[t])
                for v in reversed(dag.order):
                    if v in group:
                        continue
                    dependency = demand.get(v, Fraction())
                    gains[v] += Fraction(avoid[v], dag.counts[v]) * dependency
                    for u in dag.predecessors[v]:
                        if u not in group:
                            demand[u] = demand.get(u, Fraction()) + dependency * Fraction(
                                dag.counts[u], dag.counts[v])
            score /= self.total
            gains = {v: g / self.total for v, g in gains.items()}
            if self.score(key) != score or any(g < 0 for g in gains.values()):
                raise ArithmeticError('exact coverage/dependency disagreement')
            self._gains_cache[key] = (score, gains)
        score, gains = self._gains_cache[key]
        return score, dict(gains)  # A caller cannot corrupt the cached witness.

    def submodular_upper(self, k: int, anchor: Iterable[int] = ()) -> Fraction:
        self.instance.validate_budget(k)
        if k == 0:
            return Fraction()
        value, gains = self.score_and_gains(anchor)
        # k, NOT k-len(anchor): this bounds unrestricted replacement solutions.
        return min(Fraction(1), value + sum(sorted(gains.values(), reverse=True)[:k], Fraction()))

    def exact_routes(self, max_routes: int = 200_000) -> tuple[tuple[int, Fraction], ...]:
        """Optional reference representation; refuse large cases, never sample."""
        if type(max_routes) is not int or max_routes < 1:
            raise ValueError('positive integer route limit required')
        count = sum(d.counts[t] for d in self.oracle.dags for t, _ in d.destinations)
        if count > max_routes:
            raise ValueError(f'{count} routes exceed reference limit {max_routes}; use DAG bounds')
        if self._routes is None:
            bits = {v: 1 << i for i, v in enumerate(self.nodes)}
            masses: dict[int, Fraction] = {}
            for dag in self.oracle.dags:
                for target, _ in dag.destinations:
                    weight = self.demands[dag.source, target] / dag.counts[target] / self.total
                    stack = [(target, bits[target])]
                    while stack:
                        v, mask = stack.pop()
                        if v == dag.source:
                            masses[mask] = masses.get(mask, Fraction()) + weight
                        else:
                            stack.extend((u, mask | bits[u]) for u in dag.predecessors[v])
            self._routes = tuple(sorted(masses.items()))
            if sum((w for _, w in self._routes), Fraction()) != 1:
                raise ArithmeticError('reference route mass is not exactly one')
        return self._routes


def bound_witness(oracle: ExactCoverage, k: int, anchors: Iterable[Iterable[int]] = ()) -> dict:
    """Global upper bound from the minimum of independently valid anchor bounds."""
    oracle.instance.validate_budget(k)
    groups = sorted({(), *(oracle.instance.validate_selection(a) for a in anchors)})
    upper = min(oracle.submodular_upper(k, a) for a in groups)
    return {'kind': 'submodular', 'model': MODEL, 'instance_sha256': oracle.identity,
            'k': k, 'anchors': [list(a) for a in groups], 'upper_bound': str(upper)}


def verify_bound(oracle: ExactCoverage, k: int, witness: dict) -> Fraction:
    """Recompute a witness. Never trust its supplied scalar or solver status."""
    oracle.instance.validate_budget(k)
    if (witness.get('model') != MODEL or witness.get('instance_sha256') != oracle.identity
            or type(witness.get('k')) is not int or witness['k'] != k):
        raise ValueError('bound model, instance or budget mismatch')
    cache_key = (k, sha256(json.dumps(witness, sort_keys=True, allow_nan=False).encode()).hexdigest())
    if cache_key in oracle._verified_bounds:
        return oracle._verified_bounds[cache_key]
    kind = witness.get('kind')
    if kind == 'submodular':
        anchors = witness.get('anchors')
        if not isinstance(anchors, list) or not anchors:
            raise ValueError('nonempty anchor witness required')
        upper = min(oracle.submodular_upper(k, a) for a in anchors)
    elif kind in ('route_dual', 'branch_partition'):
        from .certificate_references import verify_reference_bound
        upper = verify_reference_bound(oracle, k, witness)
    else:
        raise ValueError('unknown bound witness type')
    if upper != rational(witness['upper_bound']) or not 0 <= upper <= 1:
        raise ValueError('claimed upper bound does not match independently verified witness')
    if kind == 'branch_partition':
        selected = oracle.instance.validate_selection(witness.get('feasible_selected', ()), k)
        lower = oracle.score(selected)
        if (lower > upper or lower != rational(witness.get('lower_bound', str(lower)))
                or witness.get('optimality_proved', lower == upper) is not (lower == upper)):
            raise ValueError('branch reference lower bound or optimality claim is inconsistent')
    oracle._verified_bounds[cache_key] = upper
    return upper


def certificate(oracle: ExactCoverage, selected: Iterable[int], k: int, *,
                witnesses: Iterable[dict] = (), feasible_references: Iterable[Iterable[int]] = ()) -> dict:
    """Certify ANY feasible deployment, not just greedy or a reference solver.

    L <= OPT <= U gives L/U <= L/OPT <= 1. OPT's lower bound B comes only
    from independently scored feasible groups. A loose U is not evidence of
    exploitable headroom. No reference witness is accepted on its scalar alone.
    """
    selected = oracle.instance.validate_selection(selected, k)
    value = oracle.score(selected)
    lower = max([value, *(oracle.score(oracle.instance.validate_selection(s, k))
                         for s in feasible_references)])
    own = bound_witness(oracle, k, [selected])
    sources = [own, *witnesses]
    checked = [(w['kind'], verify_bound(oracle, k, w)) for w in sources]
    upper = min(u for _, u in checked)
    if lower > upper:
        raise ArithmeticError('feasible solution exceeds verified upper bound')
    quality = value / upper if upper else Fraction(1)  # Only the zero optimum.
    return {'schema_version': 1, 'model': MODEL, 'instance_sha256': oracle.identity,
            'k': k, 'selected': list(selected), 'coverage_exact': str(value),
            'coverage_pct': float(100 * value),
            'optimum_lower_bound_exact': str(lower), 'optimum_upper_bound_exact': str(upper),
            'quality_lower_bound_exact': str(quality),
            'quality_lower_bound_pct': decimal_bound(100 * quality),
            'remaining_gain_lower_pp': decimal_bound(100 * (lower - value)),
            'remaining_gain_upper_pp': decimal_bound(100 * (upper - value), upper=True),
            'relative_gap_upper_exact': str(1 - quality),
            'optimum_value_proved': lower == upper,
            'deployment_optimality_proved': value == upper,
            'bound_methods': [kind for kind, u in checked if u == upper],
            'timing_scope': 'posthoc certificate work; not part of candidate search or fitness'}

"""Offline exact exchange geometry for a fixed-cardinality coverage problem.

This diagnoses an existing deployment; it is NOT a campaign solver, an evolved
program, or a timed fitness change. Reuse the certificate route representation.
All move comparisons use integer mass; route limits fail rather than sample.
"""
from __future__ import annotations

from collections import deque
from fractions import Fraction
from hashlib import sha256
from heapq import heappop, heappush
from itertools import combinations
import json
from math import comb
from typing import Iterable

from .certificates import ExactCoverage, MODEL
from .certificate_references import _IntegerRoutes


class ExchangeProblem:
    """Small-instance adapter around the already verified integer route backend."""

    def __init__(self, oracle: ExactCoverage, k: int, *, max_routes: int = 200_000):
        oracle.instance.validate_budget(k)
        self.oracle, self.k, self.nodes = oracle, k, oracle.nodes
        self.routes = _IntegerRoutes(oracle, max_routes)
        self.scale = self.routes.scale
        self.index = {v: i for i, v in enumerate(self.nodes)}

    def group(self, selected: Iterable[int]) -> tuple[int, ...]:
        selected = self.oracle.instance.validate_selection(selected, self.k)
        if len(selected) != self.k:
            raise ValueError('exchange geometry requires exactly k distinct locations')
        return selected

    def units(self, selected: tuple[int, ...]) -> int:
        return self.routes.group_score(tuple(self.index[v] for v in selected))

    def coverage(self, selected: Iterable[int]) -> Fraction:
        return Fraction(self.units(self.group(selected)), self.scale)

    def neighbors(self, selected: Iterable[int], radius: int = 1):
        selected = self.group(selected)
        if type(radius) is not int or not 1 <= radius <= min(self.k, len(self.nodes)-self.k):
            raise ValueError('exchange radius outside the fixed-cardinality domain')
        inside = set(selected)
        outside = tuple(v for v in self.nodes if v not in inside)
        for removed in combinations(selected, radius):
            remaining = inside.difference(removed)
            for added in combinations(outside, radius):
                yield tuple(sorted(remaining.union(added)))


def _limit(value: int, name: str, maximum: int = 1_000_000) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{name} must be an integer in [1, {maximum}]')


def _record(digest, group, units):
    digest.update((json.dumps([list(group), units], separators=(',', ':'))+'\n').encode())


def exchange_census(problem: ExchangeProblem, initial: Iterable[int], *,
                    max_deployments: int = 1_000_000, sample_limit: int = 16) -> dict:
    """Enumerate all k-subsets, partitioned by simultaneous replacements from S.

    Counts are exhaustive; only example lists are capped. A digest commits to the
    deterministic integer-valued enumeration stream; verification reruns it.
    """
    _limit(max_deployments, 'max_deployments')
    _limit(sample_limit, 'sample_limit', 1000)
    initial = problem.group(initial)
    n, k = len(problem.nodes), problem.k
    total = comb(n, k)
    if total > max_deployments:
        raise ValueError(f'exact census requires {total} deployments; no sampling fallback')
    value = problem.units(initial)
    best, best_groups, best_count = value, [list(initial)], 1
    stream = sha256(); _record(stream, initial, value)
    rows, first_improving_radius = [], None
    for radius in range(1, min(k, n-k)+1):
        counts = {'worse': 0, 'equal': 0, 'better': 0}
        examples = {'equal': [], 'better': []}
        maximum, best_group, minimum = -1, None, problem.scale
        for group in problem.neighbors(initial, radius):
            score = problem.units(group)
            _record(stream, group, score)
            kind = 'better' if score > value else 'equal' if score == value else 'worse'
            counts[kind] += 1
            if kind in examples and len(examples[kind]) < sample_limit:
                examples[kind].append(list(group))
            if score > maximum or (score == maximum and group < best_group):
                maximum, best_group = score, group
            minimum = min(minimum, score)
            if score > best:
                best, best_groups, best_count = score, [list(group)], 1
            elif score == best:
                best_count += 1
                if len(best_groups) < sample_limit:
                    best_groups.append(list(group))
        expected = comb(k, radius)*comb(n-k, radius)
        if sum(counts.values()) != expected:
            raise ArithmeticError('incomplete exchange sphere')
        if counts['better'] and first_improving_radius is None:
            first_improving_radius = radius
        rows.append({'radius': radius, 'evaluated': expected, **counts,
                     'best_selected': list(best_group), 'best_units': maximum,
                     'worst_units': minimum, 'examples': examples})
    if 1 + sum(r['evaluated'] for r in rows) != total:
        raise ArithmeticError('exchange spheres do not cover the full k-subset space')
    return {'complete': True, 'k': k, 'nodes': n, 'initial': list(initial),
            'scale': problem.scale, 'initial_units': value, 'total_deployments': total,
            'enumeration_sha256': stream.hexdigest(), 'sample_limit': sample_limit,
            'spheres': rows, 'smallest_improving_radius': first_improving_radius,
            'strict_improving_deployments': sum(r['better'] for r in rows),
            'global_optimum_units': best, 'global_optimum_count': best_count,
            'global_optimum_examples': sorted(best_groups)}


def _path(parents, target):
    result = []
    while target is not None:
        result.append(list(target)); target = parents[target]
    return list(reversed(result))


def neutral_component(problem: ExchangeProblem, initial: Iterable[int], *,
                      max_states: int = 10_000) -> dict:
    """Follow every exactly neutral one-for-one move, then inspect strict exits.

    An incomplete component never proves absence of an escape. This is only the
    single-exchange neutral graph, not neutral moves of arbitrary radius.
    """
    _limit(max_states, 'max_states')
    initial = problem.group(initial); value = problem.units(initial)
    parents = {initial: None}; queue = deque([initial])
    checks, strict_exits, exit_path, complete = 0, 0, None, True
    while queue:
        group = queue.popleft()
        for neighbor in problem.neighbors(group) if 0 < problem.k < len(problem.nodes) else ():
            score = problem.units(neighbor); checks += 1
            if score > value:
                strict_exits += 1
                if exit_path is None:
                    exit_path = _path(parents, group) + [list(neighbor)]
            elif score == value and neighbor not in parents:
                if len(parents) >= max_states:
                    complete = False
                else:
                    parents[neighbor] = group; queue.append(neighbor)
    return {'complete': complete, 'initial': list(initial), 'level_units': value,
            'members': [list(g) for g in sorted(parents)], 'neighbor_checks': checks,
            'strict_exit_transitions': strict_exits, 'escape_path': exit_path,
            'no_neutral_then_strict_single_exchange_escape_proved': complete and not strict_exits}


def _strict_cut(problem, initial, level, max_states):
    """Connected component at score > level; its boundary is an exact cut."""
    seen = {initial}; queue = deque([initial])
    while queue:
        group = queue.popleft()
        for neighbor in problem.neighbors(group):
            if neighbor not in seen and problem.units(neighbor) > level:
                if len(seen) >= max_states:
                    raise ValueError('cut witness state limit; no minimal-loss certificate')
                seen.add(neighbor); queue.append(neighbor)
    return [list(g) for g in sorted(seen)]


def minimum_loss_escape(problem: ExchangeProblem, initial: Iterable[int], *,
                        max_expansions: int = 10_000, max_cut_states: int = 10_000) -> dict:
    """Find a single-exchange path to ANY strict improvement with minimal drawdown.

    Maximize the minimum coverage along the path (a widest-path search). A path
    gives an achievable loss, and a separately checked strict-superlevel cut
    proves that no path can avoid at least that loss. Offline diagnosis only.
    """
    _limit(max_expansions, 'max_expansions'); _limit(max_cut_states, 'max_cut_states')
    initial = problem.group(initial); value = problem.units(initial)
    best = {initial: value}; parents = {initial: None}; queue = [(-value, initial)]
    expanded = 0
    while queue and expanded < max_expansions:
        negative, group = heappop(queue); level = -negative
        if level != best[group]:
            continue
        expanded += 1
        if problem.units(group) > value:
            proof = {'kind': 'single_exchange_escape_barrier', 'model': MODEL,
                     'instance_sha256': problem.oracle.identity, 'k': problem.k,
                     'initial': list(initial), 'scale': problem.scale,
                     'bottleneck_units': level, 'path': _path(parents, group),
                     'strict_superlevel_cut': (_strict_cut(problem, initial, level, max_cut_states)
                                               if level < value else [])}
            checked = verify_escape(problem, proof)
            return {'status': 'proved', 'expanded_states': expanded,
                    'discovered_states': len(best), 'proof': proof, 'verification': checked}
        for neighbor in problem.neighbors(group) if 0 < problem.k < len(problem.nodes) else ():
            candidate = min(level, problem.units(neighbor))
            if candidate > best.get(neighbor, -1):
                best[neighbor], parents[neighbor] = candidate, group
                heappush(queue, (-candidate, neighbor))
    return {'status': 'expansion_limit' if queue else 'no_better_deployment',
            'expanded_states': expanded, 'discovered_states': len(best),
            'proof': None, 'minimal_loss_proved': False}


def verify_escape(problem: ExchangeProblem, proof: dict) -> dict:
    """Verify feasibility, path bottleneck and a complete cut, without rerunning search."""
    if (proof.get('kind') != 'single_exchange_escape_barrier' or proof.get('model') != MODEL
            or proof.get('instance_sha256') != problem.oracle.identity
            or type(proof.get('k')) is not int or proof['k'] != problem.k
            or type(proof.get('scale')) is not int or proof['scale'] != problem.scale):
        raise ValueError('escape proof problem identity mismatch')
    initial = problem.group(proof['initial']); initial_value = problem.units(initial)
    level = proof.get('bottleneck_units')
    if type(level) is not int or not 0 <= level <= initial_value:
        raise ValueError('invalid bottleneck value')
    raw_path = proof.get('path')
    if not isinstance(raw_path, list) or not 2 <= len(raw_path) <= 1_000_000:
        raise ValueError('nontrivial finite escape path required')
    path = [problem.group(g) for g in raw_path]
    if path[0] != initial or problem.units(path[-1]) <= initial_value:
        raise ValueError('path must start at the incumbent and end strictly better')
    if any(len(set(a)-set(b)) != 1 for a, b in zip(path, path[1:])):
        raise ValueError('path uses a move other than one-for-one exchange')
    values = [problem.units(g) for g in path]
    if min(values) != level:
        raise ValueError('path does not achieve the stated bottleneck')
    raw_cut = proof.get('strict_superlevel_cut')
    if not isinstance(raw_cut, list) or len(raw_cut) > 1_000_000:
        raise ValueError('finite cut witness required')
    cut = {problem.group(g) for g in raw_cut}
    if len(cut) != len(raw_cut):
        raise ValueError('duplicated cut states')
    boundary_checks = 0
    if level == initial_value:
        if cut:
            raise ValueError('zero-loss proof must use the empty cut')
    else:
        if initial not in cut:
            raise ValueError('cut omits the initial deployment')
        if any(not level < problem.units(g) <= initial_value for g in cut):
            raise ValueError('cut contains a low or strictly improved deployment')
        for group in sorted(cut):
            for neighbor in problem.neighbors(group):
                boundary_checks += 1
                if neighbor not in cut and problem.units(neighbor) > level:
                    raise ValueError('cut omits a reachable superlevel state')
    return {'minimal_loss_proved': True,
            'minimum_loss_coverage_exact': str(Fraction(initial_value-level, problem.scale)),
            'minimum_loss_pp': float(100*Fraction(initial_value-level, problem.scale)),
            'path_coverages_exact': [str(Fraction(v, problem.scale)) for v in values],
            'path_steps': len(path)-1, 'cut_states': len(cut), 'cut_neighbor_checks': boundary_checks}

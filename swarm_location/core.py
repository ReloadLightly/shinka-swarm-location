"""Fixed-route, endpoint-inclusive OD-weighted group coverage.

Chapter 4, sections 4.7.1--4.7.4. See docs/source_fidelity.md for the
explicit emendation of printed Eq. 4.15. Monitors NEVER reroute traffic.
Shortest-path equality uses Fraction, not a floating-point tie tolerance.
Demand aggregation uses double precision. No route sampling is performed.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from math import fsum, isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Iterable
import json


def _integer(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


@dataclass(frozen=True)
class Instance:
    name: str
    nodes: tuple[int, ...]
    edges: tuple[tuple[int, int, Fraction], ...]
    od: tuple[tuple[int, int, float], ...]
    first_thru_node: int | None = None

    def __post_init__(self) -> None:
        if not self.nodes or any(not _integer(v) for v in self.nodes):
            raise ValueError("nodes must be nonempty integer IDs (not booleans)")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("duplicate node ID")
        ns = set(self.nodes)
        seen = set()
        for u, v, w in self.edges:
            if not _integer(u) or not _integer(v) or u not in ns or v not in ns:
                raise ValueError("edge endpoint not in nodes")
            if u == v or w <= 0:
                raise ValueError("positive edge weights and no self-loops required")
            if (u, v) in seen:
                raise ValueError("parallel directed edges not supported; do not silently collapse")
            seen.add((u, v))
        seen.clear()
        for s, t, q in self.od:
            if not _integer(s) or not _integer(t) or s not in ns or t not in ns:
                raise ValueError("OD endpoint not in nodes")
            if not isfinite(q) or q < 0:
                raise ValueError("demand must be finite and nonnegative")
            if s == t and q > 0:
                raise ValueError("positive intrazonal demand unsupported in step 1")
            if (s, t) in seen:
                raise ValueError("duplicate OD record")
            seen.add((s, t))
        if fsum(q for _, _, q in self.od) <= 0:
            raise ValueError("positive total OD demand required")
        if self.first_thru_node is not None and not _integer(self.first_thru_node):
            raise ValueError("first_thru_node must be an integer or null")

    @classmethod
    def from_dict(cls, data: dict) -> Instance:
        if data.get("schema_version") != 1:
            raise ValueError("expected schema_version=1")
        if any(isinstance(w, bool) for _, _, w in data["edges"]):
            raise ValueError("boolean edge weight")
        return cls(
            name=str(data["name"]),
            nodes=tuple(sorted(data["nodes"])),
            edges=tuple((u, v, Fraction(str(w))) for u, v, w in data["edges"]),
            od=tuple((s, t, float(q)) for s, t, q in data["od"]),
            first_thru_node=data.get("first_thru_node"),
        )

    @classmethod
    def load(cls, path: str | Path) -> Instance:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return {"schema_version": 1, "name": self.name, "nodes": list(self.nodes),
                "edges": [[u, v, str(w)] for u, v, w in self.edges],
                "od": [list(x) for x in self.od], "first_thru_node": self.first_thru_node}

    def validate_selection(self, selected: Iterable[int], k: int | None = None) -> tuple[int, ...]:
        values = tuple(selected)
        if any(not _integer(v) for v in values):
            raise ValueError("selected locations must be integer node IDs")
        if len(set(values)) != len(values):
            raise ValueError("duplicate monitoring locations")
        if not set(values).issubset(self.nodes):
            raise ValueError("unknown monitoring location")
        if k is not None:
            self.validate_budget(k)
            if len(values) > k:
                raise ValueError("monitor budget exceeded")
        return tuple(sorted(values))

    def validate_budget(self, k: int) -> None:
        if not _integer(k) or not 0 <= k <= len(self.nodes):
            raise ValueError("k must be an integer between zero and the node count")


@dataclass(frozen=True)
class SourceDAG:
    source: int
    order: tuple[int, ...]
    predecessors: object
    counts: object
    destinations: tuple[tuple[int, float], ...]


class ShortestPathCoverage:
    """Exact shortest-path counting without enumerating paths.

    Counts unmonitored routes on the ORIGINAL shortest-path DAG. Deleting a
    monitored node and recalculating shortest paths would be a different model.
    Memory scales with stored origin DAGs, not with the number of routes.
    """
    def __init__(self, instance: Instance):
        self.instance = instance
        self.nodes = instance.nodes
        self.total_demand = fsum(q for _, _, q in instance.od)
        adjacency = {v: [] for v in instance.nodes}
        for u, v, w in instance.edges:
            adjacency[u].append((v, w))
        for entries in adjacency.values():
            entries.sort()
        origins: dict[int, list] = {}
        for s, t, q in instance.od:
            if q > 0:
                origins.setdefault(s, []).append((t, q))
        dags = []
        for source, destinations in sorted(origins.items()):
            dist = {source: Fraction(0)}
            pred: dict[int, list[int]] = {source: []}
            queue = [(Fraction(0), source)]
            while queue:
                du, u = heappop(queue)
                if du != dist[u]:
                    continue
                # TNTP zone centroids may be endpoints but not intermediate nodes.
                if instance.first_thru_node is not None and u != source and u < instance.first_thru_node:
                    continue
                for v, weight in adjacency[u]:
                    candidate = du + weight
                    if v not in dist or candidate < dist[v]:
                        dist[v] = candidate
                        pred[v] = [u]
                        heappush(queue, (candidate, v))
                    elif candidate == dist[v]:
                        pred[v].append(u)
            order = tuple(sorted(dist, key=lambda v: (dist[v], v)))
            counts = {source: 1}
            for v in order:
                if v != source:
                    counts[v] = sum(counts[u] for u in pred[v])
            for t, _ in destinations:
                if t not in counts:
                    raise ValueError(f"positive-demand OD pair {source}->{t} is unreachable")
            dags.append(SourceDAG(source, order,
                MappingProxyType({v: tuple(sorted(ps)) for v, ps in pred.items()}),
                MappingProxyType(counts), tuple(sorted(destinations))))
        self.dags = tuple(dags)

    def score(self, selected: Iterable[int]) -> float:
        monitored = set(self.instance.validate_selection(selected))
        covered = []
        for dag in self.dags:
            avoid = {}
            for v in dag.order:
                if v in monitored:
                    avoid[v] = 0
                elif v == dag.source:
                    avoid[v] = 1
                else:
                    avoid[v] = sum(avoid[u] for u in dag.predecessors[v])
            for t, q in dag.destinations:
                covered.append(q * ((dag.counts[t] - avoid[t]) / dag.counts[t]))
        return fsum(covered) / self.total_demand

    def marginal_gains(self, selected: Iterable[int]) -> dict[int, float]:
        selected = self.instance.validate_selection(selected)
        base = self.score(selected)
        return {v: self.score((*selected, v)) - base for v in self.nodes if v not in selected}

    def compile_routes(self, max_routes: int = 200_000) -> RouteCoverage:
        """Fast reference backend for SMALL benchmarks; fail instead of sampling."""
        if not _integer(max_routes) or max_routes < 1:
            raise ValueError("max_routes must be a positive integer")
        num_routes = sum(d.counts[t] for d in self.dags for t, _ in d.destinations)
        if num_routes > max_routes:
            raise ValueError(f"{num_routes} exact routes exceed max_routes={max_routes}; use DAG backend")
        bits = {v: 1 << i for i, v in enumerate(self.nodes)}
        route_weights: dict[int, list[float]] = {}
        for dag in self.dags:
            for target, q in dag.destinations:
                per_route = q / dag.counts[target]
                stack = [(target, bits[target])]
                while stack:
                    v, mask = stack.pop()
                    if v == dag.source:
                        route_weights.setdefault(mask, []).append(per_route)
                    else:
                        stack.extend((u, mask | bits[u]) for u in dag.predecessors[v])
        routes = tuple((mask, fsum(ws) / self.total_demand)
                       for mask, ws in sorted(route_weights.items()))
        return RouteCoverage(self.instance, routes, num_routes)


class RouteCoverage:
    """All shortest routes compiled into weighted node-set masks, never sampled.

    Different OD directions/routes with identical node sets may be aggregated
    because the monitoring event depends only on whether a node set is hit.
    """
    def __init__(self, instance: Instance, routes: tuple, num_routes: int):
        self.instance = instance
        self.nodes = instance.nodes
        self.routes = routes
        self.num_routes = num_routes
        self.bits = MappingProxyType({v: 1 << i for i, v in enumerate(self.nodes)})

    def mask(self, selected: Iterable[int]) -> int:
        values = self.instance.validate_selection(selected)
        return sum(self.bits[v] for v in values)

    def score(self, selected: Iterable[int]) -> float:
        mask = self.mask(selected)
        return fsum(q for path, q in self.routes if mask & path)

    def marginal_gains(self, selected: Iterable[int]) -> dict[int, float]:
        selected = self.instance.validate_selection(selected)
        mask = self.mask(selected)
        contributions: list[list[float]] = [[] for _ in self.nodes]
        for route, weight in self.routes:
            if route & mask:
                continue
            rest = route
            while rest:
                bit = rest & -rest
                contributions[bit.bit_length() - 1].append(weight)
                rest ^= bit
        return {v: fsum(contributions[i]) for i, v in enumerate(self.nodes) if v not in selected}

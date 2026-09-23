"""Exact-route search primitives; arbitrary candidate code can also use raw DAGs.

All-origin gains cost O(sum_s (|V_s|+|E_s|)). Origin-subset queries return exact
contributions to the FULL-demand objective, not an implicitly rescaled estimate.
These primitives enable adaptive sampling, stale-gain schedules and incremental
representations without forcing a finite catalogue of search algorithms.
"""
from math import fsum
from .core import ShortestPathCoverage


class SearchProblem(ShortestPathCoverage):
    def __init__(self, instance):
        super().__init__(instance)
        self._by_origin = {dag.source: dag for dag in self.dags}
        self.origin_demand = {d.source: fsum(q for _, q in d.destinations) / self.total_demand
                              for d in self.dags}
        self.origin_arcs = {d.source: sum(len(ps) for ps in d.predecessors.values()) for d in self.dags}
        # Diagnostic only: raw-DAG/custom-kernel work is NOT captured by this.
        self.query_work = {"score_calls": 0, "gain_calls": 0, "origin_dag_arcs": 0}

    def _origins(self, origins):
        if origins is None:
            return self.dags
        values = tuple(origins)
        if any(type(v) is not int or v not in self._by_origin for v in values) or len(set(values)) != len(values):
            raise ValueError("origins must be unique known origin IDs")
        return tuple(self._by_origin[v] for v in sorted(values))

    def score_origins(self, selected, origins=None):
        selected = set(self.instance.validate_selection(selected))
        dags = self._origins(origins)
        self.query_work["score_calls"] += 1
        self.query_work["origin_dag_arcs"] += sum(self.origin_arcs[d.source] for d in dags)
        covered = []
        for dag in dags:
            avoid = {}
            for v in dag.order:
                avoid[v] = (0 if v in selected else 1 if v == dag.source else
                            sum(avoid[u] for u in dag.predecessors[v]))
            for t, q in dag.destinations:
                covered.append(q * ((dag.counts[t] - avoid[t]) / dag.counts[t]))
        return fsum(covered) / self.total_demand

    def score(self, selected):
        return self.score_origins(selected)

    def marginal_gains(self, selected):
        return self.marginal_gains_origins(selected)

    def marginal_gains_origins(self, selected, origins=None):
        selected = set(self.instance.validate_selection(selected))
        dags = self._origins(origins)
        self.query_work["gain_calls"] += 1
        self.query_work["origin_dag_arcs"] += 2 * sum(self.origin_arcs[d.source] for d in dags)
        contributions = {v: [] for v in self.nodes if v not in selected}
        for dag in dags:
            avoid = {}
            for v in dag.order:
                avoid[v] = (0 if v in selected else 1 if v == dag.source else
                            sum(avoid[u] for u in dag.predecessors[v]))
            demand = dict(dag.destinations)
            for v in reversed(dag.order):
                if v in selected:
                    continue
                value = demand.get(v, 0.0)
                contributions[v].append((avoid[v] / dag.counts[v]) * value)
                for u in dag.predecessors[v]:
                    if u not in selected:
                        demand[u] = demand.get(u, 0.0) + value * (dag.counts[u] / dag.counts[v])
        return {v: fsum(xs) / self.total_demand for v, xs in contributions.items()}

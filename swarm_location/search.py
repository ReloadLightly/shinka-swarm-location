"""All-node marginal gains on the original shortest-path DAGs; no path sampling.

Forward unmonitored-prefix counts and reverse demand dependencies give all gains
in O(sum_s (|V_s|+|E_s|)) arithmetic operations. See docs/m2_method.md.
This is a project derivation, not a reproduction of Puzis et al.'s implementation.
"""
from math import fsum
from .core import ShortestPathCoverage


class SearchProblem(ShortestPathCoverage):
    """Same score and routing as M1, without one complete score call per node."""

    def marginal_gains(self, selected):
        selected = set(self.instance.validate_selection(selected))
        contributions = {v: [] for v in self.nodes if v not in selected}
        for dag in self.dags:
            avoid = {}
            for v in dag.order:
                avoid[v] = (0 if v in selected else 1 if v == dag.source else
                            sum(avoid[u] for u in dag.predecessors[v]))
            # demand[v] = sigma_sv * sum_t q_st * sigma_vt(avoiding S) / sigma_st.
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

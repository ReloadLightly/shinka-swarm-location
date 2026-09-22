"""Seed: chapter 4.7.4 marginal group-betweenness deployment.

Future evolution changes the reusable solve() procedure, not monitoring scores,
traffic demand, shortest paths, sampling quality, or the underlying road graph.
"""
from swarm_location.core import Instance, ShortestPathCoverage

# EVOLVE-BLOCK-START
def solve(problem, k: int, random_seed: int = 0) -> list[int]:
    """Construct k locations by largest marginal covered OD demand."""
    problem.instance.validate_budget(k)
    selected = []
    for _ in range(k):
        gains = problem.marginal_gains(selected)
        next_node = min(gains, key=lambda v: (-gains[v], v))
        selected.append(next_node)
    return selected
# EVOLVE-BLOCK-END


def run_experiment(instance_data: dict, k: int, random_seed: int = 0) -> list[int]:
    """Native run_shinka_eval-compatible entrypoint; return locations, not scores."""
    instance = Instance.from_dict(instance_data)
    problem = ShortestPathCoverage(instance).compile_routes()
    return solve(problem, k, random_seed)

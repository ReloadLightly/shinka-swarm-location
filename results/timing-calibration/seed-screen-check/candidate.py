"""M2 mutable greedy seed. The external runner owns the clock and the scorer."""
from time import perf_counter


# EVOLVE-BLOCK-START
def solve(problem, k, random_seed, report, time_budget):
    """Construct a deployment, reporting each feasible best-so-far partial set.

    This is the chapter's marginal greedy rule, not an evolved discovery.
    time_budget is advisory; the independent parent enforces the real deadline.
    """
    end = perf_counter() + time_budget
    selected = []
    report(selected)
    for _ in range(k):
        if perf_counter() >= end:
            break
        gains = problem.marginal_gains(selected)
        selected.append(min(gains, key=lambda v: (-gains[v], v)))
        report(selected)
    return selected
# EVOLVE-BLOCK-END

"""Fixed DAG dfbnb control; same API and timing as evolved candidates."""
# Fixed control
from fractions import Fraction
import random
from time import perf_counter
from swarm_location.dag_bounds import DagPartition, SCALE


def solve(problem, k, random_seed, report, time_budget):
    """All construction, frontier, branching and effort decisions may evolve.

    The helper only maintains a mathematically checkable subset partition. It is
    optional: new code may implement custom representations, origin sampling,
    local search, populations, restarts or another complete search procedure.
    """
    start = perf_counter()
    end = start + time_budget
    rng = random.Random(random_seed)
    nodes = list(problem.nodes)
    # MODE is a fixed-control variant only; the seed and its entire body evolve.
    mode = "dfbnb"
    rank = sorted(nodes, key=lambda v: (-problem.origin_demand.get(v, 0.0), v))
    best = rank[:k]
    report(best)
    report.bound({"kind": "universal_v1", "upper": "1" if k else "0", "selected": best})
    if not k:
        return best
    best_value = problem.score(best)

    def offer(group):
        nonlocal best, best_value
        value = problem.score(group)
        if value > best_value:
            best, best_value = list(group), value
            report(best)
            return True
        return False

    # Overlapping singleton sets are not mistaken for independent traffic.
    gains = problem.marginal_gains([])
    rank = sorted(gains, key=lambda v: (-gains[v], v))
    offer(rank[:k])
    chosen = []
    while len(chosen) < k and perf_counter() < start + .35 * time_budget:
        gains = problem.marginal_gains(chosen)
        chosen.append(min(gains, key=lambda v: (-gains[v], v)))
        offer(chosen + [v for v in rank if v not in chosen][:k-len(chosen)])
    if perf_counter() >= end:
        return best

    tree = DagPartition(problem.instance, k, problem)
    lower, _, _ = tree.oracle.intervals(best)
    live = {0}
    stack = [0]
    report.bound(tree.snapshot(best))
    while live and perf_counter() < end:
        if mode == "dfbnb":
            while stack[-1] not in live:
                stack.pop()
            parent = stack[-1]
        else:
            # Utility-potential ordering is an algorithmic control, not a
            # probability estimate. The admissible upper remains independent.
            def priority(i):
                state = tree.leaves[i]
                target = lower + 1
                potential = Fraction(state.upper - state.lower, max(1, target - state.lower))
                return (potential, state.upper, state.lower, -i)
            parent = max(live, key=priority)
        state = tree.leaves[parent]
        if state.terminal:
            completion = state.selected
            if len(state.remaining) <= k - len(completion):
                completion += state.remaining
            if offer(completion):
                lower, _, _ = tree.oracle.intervals(best)
            live.remove(parent)
            continue
        if state.upper <= lower:
            live.remove(parent)  # Its leaf remains in the certificate partition.
            continue
        gains = problem.marginal_gains(state.selected)
        branch = max(state.remaining, key=lambda v: (gains[v], -v))
        children = tree.split(parent, branch)
        live.remove(parent)
        live.update(children)
        stack.extend(reversed(children))
        report.bound(tree.snapshot(best))
    report.bound(tree.snapshot(best))
    report.diagnostic({"partition_splits": len(tree.ops), "open_search_nodes": len(live),
                       "origin_query_work": problem.query_work})
    return best
# End fixed control

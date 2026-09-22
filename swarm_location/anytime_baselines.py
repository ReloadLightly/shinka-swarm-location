"""Fixed same-budget controls. Not Shinka-generated discoveries."""
import random
from time import perf_counter


def solve(problem, k, random_seed, report, time_budget, method="greedy"):
    end = perf_counter() + time_budget
    selected = []
    report(selected)
    if method == "random":
        selected = random.Random(random_seed).sample(problem.nodes, k)
        report(selected)
        return selected
    if method == "topk":
        gains = problem.marginal_gains([])
        selected = sorted(gains, key=lambda v: (-gains[v], v))[:k]
        report(selected)
        return selected
    if method not in ("greedy", "greedy_swap"):
        raise ValueError(f"unknown fixed method {method}")
    for _ in range(k):
        if perf_counter() >= end:
            return selected
        gains = problem.marginal_gains(selected)
        selected.append(min(gains, key=lambda v: (-gains[v], v)))
        report(selected)
    if method == "greedy":
        return selected
    value = problem.score(selected)
    while selected and perf_counter() < end:
        best, best_value = selected, value
        # One reverse-dependency pass per removed monitor, not per replacement.
        for removed in sorted(selected):
            if perf_counter() >= end:
                break
            rest = sorted(set(selected) - {removed})
            base = problem.score(rest)
            for added, gain in sorted(problem.marginal_gains(rest).items()):
                if added not in selected and base + gain > best_value + 1e-12:
                    best, best_value = sorted([*rest, added]), base + gain
        if best_value <= value + 1e-12:
            break
        selected, value = best, problem.score(best)
        report(selected)
    return selected

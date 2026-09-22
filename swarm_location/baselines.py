"""Reference solvers. They optimize the same immutable coverage function."""
from itertools import combinations
from math import comb
import random


def greedy(problem, k: int, seed: int = 0) -> list[int]:
    """Chapter 4.7.4 marginal GBC; ties use the smallest node ID."""
    problem.instance.validate_budget(k)
    selected = []
    for _ in range(k):
        gains = problem.marginal_gains(selected)
        selected.append(min(gains, key=lambda v: (-gains[v], v)))
    return selected


def topk_bc(problem, k: int, seed: int = 0) -> list[int]:
    """Rank singleton OD-weighted BC; deliberately ignores group overlap."""
    problem.instance.validate_budget(k)
    gains = problem.marginal_gains([])
    return sorted(gains, key=lambda v: (-gains[v], v))[:k]


def random_deployment(problem, k: int, seed: int = 0) -> list[int]:
    problem.instance.validate_budget(k)
    return random.Random(seed).sample(problem.nodes, k)


def greedy_swap(problem, k: int, seed: int = 0) -> list[int]:
    """Additional control, NOT a chapter reconstruction: best 1-for-1 exchange."""
    selected = greedy(problem, k, seed)
    value = problem.score(selected)
    while selected:
        best_value, best = value, selected
        for removed in sorted(selected):
            rest = sorted(set(selected) - {removed})
            for added in problem.nodes:
                if added in selected:
                    continue
                candidate = sorted([*rest, added])
                trial = problem.score(candidate)
                if trial > best_value + 1e-12:
                    best_value, best = trial, candidate
        if best_value <= value + 1e-12:
            return selected
        value, selected = best_value, best
    return selected


def exhaustive(problem, k: int, max_combinations: int = 100_000) -> list[int]:
    """Small-instance exact enumeration, NOT DFBnB or Potential Search."""
    problem.instance.validate_budget(k)
    count = comb(len(problem.nodes), k)
    if count > max_combinations:
        raise ValueError(f"exhaustive search needs {count} groups; limit={max_combinations}")
    best, score = [], -1.0
    for group in combinations(problem.nodes, k):
        value = problem.score(group)
        if value > score:
            best, score = list(group), value
    return best

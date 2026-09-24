"""Trusted protocol driver. Process isolation is NOT a hostile-code sandbox."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys

# This script is copied with the trusted package into an ephemeral working dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from swarm_location.core import Instance
from swarm_location.search import SearchProblem


def main():
    request = json.loads(sys.stdin.readline())
    if request.get('prepared_file'):
        from swarm_location.prepared import load_prepared
        prepared = load_prepared(request['prepared_file'], request['prepared_sha256'])
        problem = SearchProblem(prepared.instance, prepared=prepared)
    else:
        problem = SearchProblem(Instance.load(request['instance_file']))
    output = sys.stdout

    def emit(message):
        output.write(json.dumps(message, allow_nan=False, separators=(",", ":")) + "\n")
        output.flush()

    def report(selected):
        emit({"selected": list(selected)})

    if request.get("allow_candidate_bounds"):
        report.bound = lambda data: emit({"search_bound": data})
        report.diagnostic = lambda data: emit({"diagnostic": data})
    emit({"ready": True})
    if sys.stdin.readline().strip() != "go":
        raise RuntimeError("missing external start signal")
    # Candidate-specific imports/compilation and all search work are timed.
    with contextlib.redirect_stdout(sys.stderr):
        if request["baseline"] is not None:
            emit({"phase": "search"})
            if request["baseline"] not in ("random", "topk", "greedy", "greedy_swap"):
                from swarm_location.strong_baselines import BOUND_METHODS
                from swarm_location.strong_baselines import solve
                report.diagnostic = lambda data: emit({"diagnostic": data})
                if request["baseline"] in BOUND_METHODS:
                    report.bound = lambda data: emit({"search_bound": data})
            else:
                from swarm_location.anytime_baselines import solve
            result = solve(problem, request["k"], request["seed"], report,
                           request["budget"], request["baseline"])
        else:
            emit({'phase': 'candidate_import'})
            spec = importlib.util.spec_from_file_location("candidate", "candidate.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            emit({'phase': 'search'})
            result = module.solve(problem, request["k"], request["seed"], report,
                                  request["budget"])
        if result is not None:
            report(result)
    emit({"done": True})


if __name__ == "__main__":
    main()

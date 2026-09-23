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


PHASE = "setup"


def main():
    global PHASE
    request = json.loads(sys.stdin.readline())
    problem = SearchProblem(Instance.from_dict(request["instance"]))
    output = sys.stdout

    def emit(message):
        output.write(json.dumps(message, allow_nan=False, separators=(",", ":")) + "\n")
        output.flush()

    def report(selected):
        emit({"selected": list(selected)})

    emit({"ready": True})
    if sys.stdin.readline().strip() != "go":
        raise RuntimeError("missing external start signal")
    # Candidate-specific imports/compilation and all search work are timed.
    with contextlib.redirect_stdout(sys.stderr):
        if request["baseline"] is not None:
            PHASE = "baseline_import"
            if request["baseline"] not in ("random", "topk", "greedy", "greedy_swap"):
                from swarm_location.strong_baselines import BOUND_METHODS
                from swarm_location.strong_baselines import solve
                report.diagnostic = lambda data: emit({"diagnostic": data})
                if request["baseline"] in BOUND_METHODS:
                    report.bound = lambda data: emit({"search_bound": data})
            else:
                from swarm_location.anytime_baselines import solve
            PHASE = "baseline_solve"
            result = solve(problem, request["k"], request["seed"], report,
                           request["budget"], request["baseline"])
        else:
            PHASE = "candidate_import"
            spec = importlib.util.spec_from_file_location("candidate", "candidate.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            PHASE = "candidate_solve"
            result = module.solve(problem, request["k"], request["seed"], report,
                                  request["budget"])
        PHASE = "baseline_return" if request["baseline"] is not None else "candidate_return"
        if result is not None:
            report(result)
    emit({"done": True})


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:
        # Imported only on failure; stdout remains the deployment protocol.
        from swarm_location.diagnostics import PREFIX, exception_record
        sys.__stderr__.write(PREFIX + json.dumps(exception_record(exc, PHASE), ensure_ascii=True) + "\n")
        sys.__stderr__.flush()
        raise SystemExit(1)

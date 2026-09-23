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
    problem = SearchProblem(Instance.from_dict(request["instance"]))
    output = sys.stdout
    diagnostic_enabled = request.get("feedback_profile") == "m7-evidence-v1"
    phase = ["setup"]

    def emit(message):
        output.write(json.dumps(message, allow_nan=False, separators=(",", ":")) + "\n")
        output.flush()

    def report(selected):
        previous = phase[0]
        phase[0] = "report"
        emit({"selected": list(selected)})
        phase[0] = previous

    emit({"ready": True})
    if sys.stdin.readline().strip() != "go":
        raise RuntimeError("missing external start signal")
    try:
        # Candidate-specific imports/compilation and all search work are timed.
        with contextlib.redirect_stdout(sys.stderr):
            if request["baseline"] is not None:
                phase[0] = "baseline_import"
                if request["baseline"] not in ("random", "topk", "greedy", "greedy_swap"):
                    from swarm_location.strong_baselines import BOUND_METHODS
                    from swarm_location.strong_baselines import solve
                    report.diagnostic = lambda data: emit({"diagnostic": data})
                    if request["baseline"] in BOUND_METHODS:
                        report.bound = lambda data: emit({"search_bound": data})
                else:
                    from swarm_location.anytime_baselines import solve
                phase[0] = "baseline_run"
                result = solve(problem, request["k"], request["seed"], report,
                               request["budget"], request["baseline"])
            else:
                phase[0] = "candidate_import"
                spec = importlib.util.spec_from_file_location("candidate", "candidate.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                phase[0] = "candidate_run"
                result = module.solve(problem, request["k"], request["seed"], report,
                                      request["budget"])
            phase[0] = "candidate_return" if request["baseline"] is None else "baseline_run"
            if result is not None:
                report(result)
        emit({"done": True})
    except BaseException as exc:
        if not diagnostic_enabled:
            raise
        from swarm_location.diagnostics import emit_exception
        emit_exception(exc, phase[0], sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

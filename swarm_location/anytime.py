"""External incumbent clock, deadline enforcement, and independent DAG scoring.

Linux/WSL backend. Common fixed preprocessing completes before the external GO.
Only complete messages received by their checkpoint count. Scoring happens AFTER
capture, so evaluator computation does not delay receipt of later incumbents.
"""
from __future__ import annotations

import json
from math import fsum, isfinite
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
from time import perf_counter

from .core import Instance, ShortestPathCoverage
from .isolation import command as worker_command, cleanup as cleanup_container


TRUSTED = ("__init__.py", "core.py", "search.py", "anytime_baselines.py", "anytime_worker.py",
           "route_search.py", "bounded_search.py", "strong_baselines.py", "dag_bounds.py")


def checkpoints_checked(values):
    values = tuple(values)
    if (not values or any(isinstance(v, bool) or not isinstance(v, (int, float))
                         or not isfinite(v) or v <= 0 for v in values)
            or list(values) != sorted(set(values))):
        raise ValueError("checkpoints must be finite, positive, strictly increasing seconds")
    return values


def score_trace(instance, k, checkpoints, events, oracle=None):
    """Score only externally stamped messages, as a best-so-far step function."""
    checkpoints = checkpoints_checked(checkpoints)
    instance.validate_budget(k)
    oracle = oracle or ShortestPathCoverage(instance)
    best, value, previous = (), 0.0, -1.0
    improvements = [{"received_seconds": 0.0, "coverage": 0.0, "selected": []}]
    for elapsed, selected in events:
        if not isfinite(elapsed) or elapsed < previous or elapsed < 0:
            raise ValueError("nonmonotonic or invalid external timestamp")
        previous = elapsed
        group = instance.validate_selection(selected, k)
        if elapsed > checkpoints[-1]:
            continue
        trial = oracle.score(group)
        if trial > value:
            value, best = trial, group
            improvements.append({"received_seconds": elapsed, "coverage": trial,
                                 "selected": list(group)})
    scores = [max(x["coverage"] for x in improvements if x["received_seconds"] <= t)
              for t in checkpoints]
    return {"checkpoints_seconds": list(checkpoints), "coverage_at_checkpoints": scores,
            "mean_checkpoint_coverage": fsum(scores) / len(scores),
            "final_coverage": value, "selected": list(best), "improvements": improvements}


def run_anytime(instance: Instance, k: int, checkpoints, *, program_path=None,
                baseline=None, seed=0, setup_timeout=120.0, oracle=None,
                max_messages=4096, max_output_bytes=4_000_000, allow_candidate_bounds=False):
    """Do not expose results directories, provider credentials, or scored data.

    This minimizes accidental leakage. Same-user subprocesses are not an OS
    security boundary. Use a container/VM for untrusted generated programs.
    """
    if os.name != "posix":
        raise RuntimeError("the external timing backend requires Linux/WSL")
    checkpoints = checkpoints_checked(checkpoints)
    instance.validate_budget(k)
    if (program_path is None) == (baseline is None):
        raise ValueError("supply exactly one candidate path or fixed baseline")
    from .strong_baselines import METHODS, BOUND_METHODS
    if baseline is not None and baseline not in ("greedy", "greedy_swap", "random", "topk", *METHODS):
        raise ValueError("unknown baseline")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if not isfinite(setup_timeout) or setup_timeout <= 0:
        raise ValueError("positive setup timeout required")
    events, failure, reason = [], None, "completed"
    bound_events, diagnostics = [], []
    setup_started = perf_counter()
    setup_seconds = None
    start = None
    with tempfile.TemporaryDirectory(prefix="swarm-location-") as directory:
        work = Path(directory)
        package = work / "swarm_location"
        package.mkdir()
        for name in TRUSTED:
            shutil.copyfile(Path(__file__).parent / name, package / name)
        if program_path is not None:
            shutil.copyfile(Path(program_path).resolve(), work / "candidate.py")
        # Keep logs bounded by discarding them; candidate exceptions are reflected
        # by the nonzero exit status. No provider environment is passed through.
        env = {"PATH": os.defpath, "HOME": directory, "TMPDIR": directory,
               "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        request = {"instance": instance.to_dict(), "k": k, "seed": seed,
                   "budget": checkpoints[-1], "baseline": baseline, "allow_candidate_bounds": allow_candidate_bounds}
        argv, container_name, isolation = worker_command(work, package)
        with subprocess.Popen(argv,
                              cwd=directory, env=env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              start_new_session=True) as proc:
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ)
            os.set_blocking(proc.stdout.fileno(), False)
            buffer, total, done = b"", 0, False
            try:
                proc.stdin.write((json.dumps(request) + "\n").encode())
                proc.stdin.flush()
                while True:
                    now = perf_counter()
                    deadline = setup_started + setup_timeout if start is None else start + checkpoints[-1]
                    if now >= deadline:
                        if start is None:
                            failure, reason = "worker setup timeout", "setup_timeout"
                        else:
                            reason = "deadline"
                        break
                    readable = selector.select(timeout=min(0.05, deadline - now))
                    if not readable:
                        continue
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    received = perf_counter()
                    if not chunk:
                        if buffer:
                            failure = "truncated protocol message"
                        break
                    total += len(chunk)
                    if total > max_output_bytes:
                        failure = "output byte limit exceeded"
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        message = json.loads(line)
                        if start is None:
                            if message != {"ready": True}:
                                raise ValueError("expected a single ready message")
                            setup_seconds = received - setup_started
                            start = perf_counter()
                            proc.stdin.write(b"go\n")
                            proc.stdin.flush()
                            continue
                        elapsed = received - start
                        if elapsed > checkpoints[-1]:
                            reason = "deadline"
                            break
                        if done:
                            raise ValueError("output after done message")
                        if message == {"done": True}:
                            done = True
                        elif ((baseline in BOUND_METHODS or allow_candidate_bounds) and isinstance(message, dict)
                              and set(message) == {"search_bound"}):
                            if len(bound_events) >= max_messages:
                                raise ValueError("bound message limit exceeded")
                            bound_events.append((elapsed, message["search_bound"]))
                        elif ((baseline in METHODS or allow_candidate_bounds) and isinstance(message, dict)
                              and set(message) == {"diagnostic"}):
                            if len(diagnostics) >= 16:
                                raise ValueError("diagnostic message limit exceeded")
                            diagnostics.append((elapsed,message["diagnostic"]))
                        elif isinstance(message, dict) and set(message) == {"selected"}:
                            if not isinstance(message["selected"], list):
                                raise ValueError("selected must be a JSON list")
                            if len(events) >= max_messages:
                                raise ValueError("incumbent message limit exceeded")
                            events.append((elapsed, message["selected"]))
                        else:
                            raise ValueError("invalid protocol; candidate scores/times are not accepted")
                    if reason == "deadline" or failure:
                        break
                if reason == "completed":
                    try:
                        code = proc.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        code = None
                    if code != 0 or not done:
                        failure = failure or f"worker did not finish cleanly (exit={code})"
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                failure = f"{type(exc).__name__}: {exc}"
            finally:
                selector.close()
                # Kill the process group even if its leader has exited.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                cleanup_container(container_name, env)
    elapsed_total = perf_counter() - setup_started
    try:
        scored = score_trace(instance, k, checkpoints, events, oracle)
    except (ValueError, TypeError, OverflowError) as exc:
        failure = f"invalid deployment: {exc}"
        scored = score_trace(instance, k, checkpoints, [], oracle)
    extra = {}
    if baseline in METHODS or allow_candidate_bounds:
        extra = {"solver_diagnostics": diagnostics}
    if baseline in BOUND_METHODS or allow_candidate_bounds:
        from .baseline_proofs import verify_online_bounds
        began = perf_counter()
        try:
            if any(e.get("kind") == "dag_partition_v2" for _, e in bound_events) or (allow_candidate_bounds and baseline is None and not any(e.get("kind") == "online_partition_v1" for _, e in bound_events)):
                from .dag_bounds import verify_dag_bounds
                verified = verify_dag_bounds(instance, k, bound_events, oracle)
            else:
                verified = verify_online_bounds(instance,k,bound_events)
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            failure = f"invalid online bound: {exc}"
            verified = []
        extra.update(search_bound_events=bound_events, verified_search_bounds=verified,
                     bound_verification_seconds=perf_counter()-began)
    return {**scored, **extra, "correct": failure is None, "error": failure,
            "termination": reason, "setup_wall_seconds": setup_seconds,
            "total_wall_seconds_before_scoring": elapsed_total,
            "received_deployments": len(events), "events": events,
            "seed": seed, "k": k, "instance": instance.name, "isolation": isolation}

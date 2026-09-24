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
from .diagnostics import Tail, failure_kind
from .persistence import atomic_json, digest, file_digest
from .isolation import command as worker_command, cleanup as cleanup_container


TRUSTED = ("__init__.py", "core.py", "search.py", "anytime_baselines.py", "anytime_worker.py",
           "route_search.py", "bounded_search.py", "strong_baselines.py", "dag_bounds.py",
           "prepared.py", "persistence.py", "diagnostics.py")


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


def _capture_anytime(instance: Instance, k: int, checkpoints, *, program_path=None,
                baseline=None, seed=0, setup_timeout=120.0, oracle=None,
                max_messages=4096, max_output_bytes=4_000_000, allow_candidate_bounds=False,
                prepared_path=None, prepared_sha256=None):
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
    stderr_tail, phase, code = Tail(), "setup", None
    with tempfile.TemporaryDirectory(prefix="swarm-location-") as directory:
        work = Path(directory)
        package = work / "swarm_location"
        package.mkdir()
        for name in TRUSTED:
            shutil.copyfile(Path(__file__).parent / name, package / name)
        if program_path is not None:
            shutil.copyfile(Path(program_path).resolve(), work / "candidate.py")
        # Read diagnostics on a separate nonblocking pipe. Never let candidate
        # logs fill a pipe or collect the provider environment.
        env = {"PATH": os.defpath, "HOME": directory, "TMPDIR": directory,
               "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
               "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        request = {"k": k, "seed": seed, "budget": checkpoints[-1],
                   "baseline": baseline, "allow_candidate_bounds": allow_candidate_bounds}
        if prepared_path is not None:
            destination = work / 'prepared.jsonl.gz'
            if os.environ.get('SWARM_DOCKER_IMAGE'):
                try:
                    os.link(prepared_path, destination)
                except OSError:
                    shutil.copyfile(prepared_path, destination)
            else:
                # Same-user debug code must not mutate the shared cache via a link.
                shutil.copyfile(prepared_path, destination)
            destination.chmod(0o444)
            request.update(prepared_file=destination.name, prepared_sha256=prepared_sha256)
        else:
            # Keep large instance writes out of the stdin/GO deadline handshake.
            atomic_json(work / 'instance.json', instance.to_dict())
            (work / 'instance.json').chmod(0o444)
            request['instance_file'] = 'instance.json' 
        argv, container_name, isolation = worker_command(work, package)
        with subprocess.Popen(argv,
                              cwd=directory, env=env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              start_new_session=True) as proc:
            selector = selectors.DefaultSelector()
            selector.register(proc.stdout, selectors.EVENT_READ)
            selector.register(proc.stderr, selectors.EVENT_READ)
            os.set_blocking(proc.stderr.fileno(), False)
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
                    stdout_ready = any(key.fileobj is proc.stdout for key, _ in readable)
                    # Stamp stdout before draining stderr; diagnostics never enter
                    # the incumbent protocol or its output-byte allowance.
                    chunk = os.read(proc.stdout.fileno(), 65536) if stdout_ready else None
                    received = perf_counter()
                    for key, _ in readable:
                        if key.fileobj is proc.stderr:
                            diagnostic = os.read(proc.stderr.fileno(), 16384)
                            if diagnostic:
                                stderr_tail.add(diagnostic)
                            else:
                                selector.unregister(proc.stderr)
                    if not stdout_ready:
                        continue
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
                        if (isinstance(message, dict) and set(message) == {'phase'} and
                                message['phase'] in ('candidate_import', 'search')):
                            phase = message['phase']  # Diagnostic, not a trusted score.
                        elif message == {"done": True}:
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
                # Pipes may contain the traceback written immediately before exit.
                while True:
                    try:
                        chunk = os.read(proc.stderr.fileno(), 16384)
                    except (BlockingIOError, OSError):
                        break
                    if not chunk:
                        break
                    stderr_tail.add(chunk)
                cleanup_container(container_name, env)
    return {"checkpoints_seconds": list(checkpoints), "events": events,
            "search_bound_events": bound_events, "solver_diagnostics": diagnostics,
            "failure": failure, "termination": reason, "phase": phase,
            "returncode": code, "stderr_tail": stderr_tail.text(),
            "stderr_bytes": stderr_tail.total, "stderr_truncated": stderr_tail.total > stderr_tail.limit,
            "setup_wall_seconds": setup_seconds,
            "total_wall_seconds_before_scoring": perf_counter() - setup_started,
            "received_deployments": len(events), "seed": seed, "k": k,
            "instance": instance.name, "isolation": isolation}


def postprocess(instance, k, checkpoints, capture, baseline=None, allow_candidate_bounds=False, oracle=None):
    """Trusted scoring only: never imports the candidate. Also used by verifier."""
    failure = capture['failure']
    kind = failure_kind(failure, capture.get('stderr_tail', ''), capture.get('phase'), capture.get('returncode'))
    oracle = oracle or ShortestPathCoverage(instance)
    try:
        scored = score_trace(instance, k, checkpoints, capture['events'], oracle)
    except (ValueError, TypeError, OverflowError) as exc:
        failure, kind = f"invalid deployment: {exc}", 'invalid_deployment'
        scored = score_trace(instance, k, checkpoints, [], oracle)
    from .strong_baselines import BOUND_METHODS
    extra = {}
    if baseline in BOUND_METHODS or allow_candidate_bounds:
        from .baseline_proofs import verify_online_bounds
        began = perf_counter()
        try:
            bound_events = capture['search_bound_events']
            if any(not isinstance(e, dict) for _, e in bound_events):
                raise ValueError('certificate must be an object')
            if (any(e.get('kind') == 'dag_partition_v2' for _, e in bound_events) or
                    (allow_candidate_bounds and baseline is None and
                     not any(e.get('kind') == 'online_partition_v1' for _, e in bound_events))):
                from .dag_bounds import verify_dag_bounds
                verified = verify_dag_bounds(instance, k, bound_events, oracle)
            else:
                verified = verify_online_bounds(instance, k, bound_events)
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            failure, kind, verified = f"invalid online bound: {exc}", 'invalid_certificate', []
        extra.update(verified_search_bounds=verified, bound_verification_seconds=perf_counter()-began)
    trace = {**capture, **scored, **extra, 'correct': failure is None, 'error': failure,
             'failure_kind': kind, 'retryable': kind in ('setup_timeout', 'worker_setup')}
    if allow_candidate_bounds and failure is None:
        from .verification import certificate_curve
        trace['certificate_at_checkpoints'] = certificate_curve(instance, k, trace, oracle)
    return trace


def run_anytime(instance, k, checkpoints, *, program_path=None, baseline=None, seed=0,
                setup_timeout=120., oracle=None, max_messages=4096,
                max_output_bytes=4_000_000, allow_candidate_bounds=False,
                prepared_path=None, prepared_sha256=None, verification_limits=None,
                capture_path=None):
    """Low-level trusted-debug API. Research CLI enforces generated-code isolation.

    Persist capture before verification. A retry after verifier interruption replays
    the SAME timed output, rather than drawing a more favorable timing sample.
    """
    checkpoints = checkpoints_checked(checkpoints)
    stamp = {'instance': digest(instance.to_dict()), 'k': k, 'seed': seed,
             'checkpoints': list(checkpoints), 'baseline': baseline,
             'candidate': file_digest(program_path) if program_path is not None else None,
             'prepared': prepared_sha256, 'bounds': allow_candidate_bounds,
             'source': file_digest(__file__), 'image': os.environ.get('SWARM_DOCKER_IMAGE')}
    resumed = False
    capture_path = Path(capture_path) if capture_path is not None else None
    if capture_path is not None and capture_path.exists():
        saved = json.loads(capture_path.read_text())
        if saved['identity'] != stamp or saved['sha256'] != digest(saved['capture']):
            raise ValueError('capture identity/checksum mismatch')
        capture = saved['capture']
        resumed = True
    else:
        capture = _capture_anytime(instance, k, checkpoints, program_path=program_path,
            baseline=baseline, seed=seed, setup_timeout=setup_timeout, oracle=oracle,
            max_messages=max_messages, max_output_bytes=max_output_bytes,
            allow_candidate_bounds=allow_candidate_bounds,
            prepared_path=prepared_path, prepared_sha256=prepared_sha256)
        if capture_path is not None and capture['phase'] != 'setup':
            atomic_json(capture_path, {'identity': stamp, 'capture': capture, 'sha256': digest(capture)})
    if verification_limits is not None:
        from .verification import verify_capture
        result = verify_capture(instance, k, checkpoints, capture, baseline,
            allow_candidate_bounds, prepared_path, prepared_sha256, verification_limits)
    else:
        result = postprocess(instance, k, checkpoints, capture, baseline, allow_candidate_bounds, oracle)
    result['capture_reused'] = resumed
    return result

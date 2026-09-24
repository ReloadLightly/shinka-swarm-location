"""Independent scoring and certificate replay in a resource-limited process.

The checker runs trusted code only, consumes data-only JSON, receives no provider
credentials, and never imports a candidate. Worker search time and checker costs
are recorded separately. Failure to verify never accepts a claimed bound.
"""
from fractions import Fraction
import json
from math import ceil, isfinite
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from time import perf_counter

from .dag_bounds import IntervalOracle, SCALE
from .diagnostics import redact
from .persistence import atomic_json


def limits_from(protocol):
    seconds = protocol.get('verification_timeout_seconds', 1800)
    memory = protocol.get('verification_memory_mib', int(os.environ.get('SWARM_WORKER_MEMORY_MIB', '768')))
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not isfinite(seconds) or seconds <= 0:
        raise ValueError('positive finite verification_timeout_seconds required')
    if type(memory) is not int or memory < 1:
        raise ValueError('positive integer verification_memory_mib required')
    return {'wall_seconds': seconds, 'cpu_seconds': max(1, ceil(seconds)),
            'memory_mib': memory, 'output_bytes': 64 * 1024 * 1024}


def certificate_curve(instance, k, trace, oracle):
    interval = IntervalOracle(instance, oracle)
    cached = {(): Fraction(0)}
    curve = []
    for time in trace['checkpoints_seconds']:
        best = max((e for e in trace['improvements'] if e['received_seconds'] <= time), key=lambda e: e['coverage'])
        selected = tuple(best['selected'])
        if selected not in cached:
            lower, _, _ = interval.intervals(selected)
            cached[selected] = Fraction(lower, SCALE)
        upper = min([Fraction(1 if k else 0), *(Fraction(e['upper_exact'])
            for e in trace.get('verified_search_bounds', []) if e['received_seconds'] <= time)])
        lower = cached[selected]
        if lower > upper:
            raise ValueError('verified lower bound exceeds verified upper bound')
        curve.append(float(lower / upper) if upper else 1.)
    return curve


def verify_capture(instance, k, checkpoints, capture, baseline, bounds, prepared_path, prepared_sha256, limits):
    began = perf_counter()
    with tempfile.TemporaryDirectory(prefix='swarm-verification-') as directory:
        root = Path(directory)
        request = {'k': k, 'checkpoints': list(checkpoints), 'capture': capture,
                   'baseline': baseline, 'bounds': bounds, 'limits': limits}
        if prepared_path is not None:
            request.update(prepared_path=str(Path(prepared_path).resolve()), prepared_sha256=prepared_sha256)
        else:
            request['instance'] = instance.to_dict()
        atomic_json(root/'request.json', request)
        env = {'PATH': os.defpath, 'HOME': directory, 'TMPDIR': directory,
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0',
               'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
        command = [sys.executable, '-I', '-B', str(Path(__file__).with_name('verification_worker.py')),
                   str(root/'request.json'), str(root/'response.json'),
                   str(limits['memory_mib']), str(limits['cpu_seconds']), str(limits['output_bytes'])]
        with (root/'stderr.log').open('wb') as error_stream:
            proc = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.DEVNULL,
                                    stderr=error_stream, start_new_session=True)
            timed_out = False
            try:
                proc.wait(timeout=limits['wall_seconds'])
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        with (root/'stderr.log').open('rb') as log:
            log.seek(max(0, (root/'stderr.log').stat().st_size - 16384))
            stderr = redact(log.read(16384).decode(errors='replace'))
        result_path = root/'response.json'
        if not timed_out and proc.returncode == 0 and result_path.exists():
            if result_path.stat().st_size > limits['output_bytes']:
                raise ValueError('verifier output limit exceeded')
            result = json.loads(result_path.read_text())
        else:
            kind = 'verification_timeout' if timed_out else 'verification_resource_or_runtime'
            result = {**capture, 'correct': False, 'error': kind + (': ' + stderr if stderr else ''),
                      'failure_kind': kind, 'retryable': True, 'verified_search_bounds': []}
        result['verification'] = {'mode': 'trusted-resource-limited-process', 'limits': limits,
                                  'wall_seconds': perf_counter()-began, 'returncode': proc.returncode,
                                  'timed_out': timed_out}
        return result

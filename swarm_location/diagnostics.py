"""Bounded repair evidence, never a source of scores or successful correctness.

The worker and everything it writes are untrusted. Sanitization is best effort,
not a proof against prompt injection or arbitrary secret encodings. No raw stderr
is persisted. Numerical results and the parent's protocol verdict are separate.
"""
from __future__ import annotations

import json
import re
import unicodedata

PREFIX = 'SWARM_EXCEPTION_V1 '
TAIL_BYTES = 16_384
RENDER_CHARS = 2_048
PHASES = {'setup', 'candidate_import', 'candidate_solve', 'candidate_return',
          'baseline_import', 'baseline_solve', 'baseline_return'}
PARENT_KINDS = {'setup_timeout', 'protocol_violation', 'output_limit',
                'worker_exit', 'infrastructure_error', 'invalid_deployment',
                'invalid_bound', 'deadline_reached', 'completed'}


def sanitize(value: str, limit: int = RENDER_CHARS) -> str:
    """Remove terminal controls, paths and recognizable credentials, then bound.

    Redact before truncation. Do not read the parent's environment to find keys:
    provider secrets must never be copied into worker or feedback processing.
    """
    text = str(value)
    text = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)', '', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = ''.join(c for c in text if c in '\n\t' or unicodedata.category(c)[0] != 'C')
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|$)',
                  '[REDACTED KEY]', text, flags=re.S)
    text = re.sub(r'(?i)\b(?:https?|ssh)://[^\s\"\'<>]+', '[URL]', text)
    text = re.sub(r'(?i)\bBearer\s+[^\s\"\'<>]+', 'Bearer [REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|authorization|password|secret)'
                  r'[\"\']?\s*[:=]\s*[\"\']?)[^\s,\"\'\]}]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{6,}|gh[pousr]_[A-Za-z0-9_]{6,}|'
                  r'github_pat_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16})\b', '[REDACTED]', text)
    # Keep a recognizable Python basename/line location, never a host directory.
    text = re.sub(r'(?:(?:[A-Za-z]:[\\/])|/)(?:[^\s\"\'<>:,()]+[\\/])*'
                  r'[^\s\"\'<>:,()]+',
                  lambda m: ('<path>/' + re.split(r'[/\\]', m[0])[-1]
                             if m[0].endswith('.py') else '<path>'), text)
    return text if len(text) <= limit else text[:max(0, limit-14)] + ' [truncated]'


class StderrTail:
    """A fixed memory tail; excess output is drained, not saved or trusted."""
    def __init__(self, limit: int = TAIL_BYTES):
        if type(limit) is not int or limit < 1:
            raise ValueError('positive stderr tail limit required')
        self.limit, self.total, self.tail = limit, 0, b''

    def feed(self, chunk: bytes) -> None:
        self.total += len(chunk)
        self.tail = (self.tail + chunk)[-self.limit:]


def exception_record(exc: BaseException, phase: str) -> dict:
    """Called in the worker only after failure. Omit locals and source lines."""
    frames, tb = [], exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append({'file': re.split(r'[/\\]', code.co_filename)[-1][:80],
                       'line': tb.tb_lineno, 'function': code.co_name[:80]})
        frames = frames[-8:]
        tb = tb.tb_next
    if isinstance(exc, SyntaxError):
        frames.append({'file': 'candidate.py', 'line': exc.lineno or 0, 'function': '<syntax>'})
    try:
        message = sanitize(str(exc), 512)
    except BaseException:
        message = '[exception message unavailable]'
    return {'phase': phase if phase in PHASES else 'setup',
            'exception_type': type(exc).__name__[:80], 'message': message, 'frames': frames[-8:]}


def repair_diagnostic(tail: StderrTail, parent_kind: str, exit_code: int | None) -> dict:
    """Format captured evidence after timing. Worker phase/type are hints only."""
    if parent_kind not in PARENT_KINDS:
        raise ValueError('unknown parent diagnostic category')
    text = tail.tail.decode('utf-8', errors='replace')
    record = None
    for line in reversed(text.splitlines()):
        if not line.startswith(PREFIX):
            continue
        try:
            raw = json.loads(line[len(PREFIX):])
            if (set(raw) != {'phase','exception_type','message','frames'}
                    or raw['phase'] not in PHASES
                    or not isinstance(raw['exception_type'], str)
                    or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', raw['exception_type'])
                    or not isinstance(raw['message'], str) or not isinstance(raw['frames'], list)):
                continue
            frames = []
            for f in raw['frames'][-8:]:
                if (not isinstance(f, dict) or set(f) != {'file','line','function'}
                        or type(f['line']) is not int or not 0 <= f['line'] <= 10_000_000
                        or not isinstance(f['file'], str) or not isinstance(f['function'], str)):
                    continue
                # Frame names may be forged; reduce them to harmless identifiers.
                basename = re.split(r'[/\\]', f['file'])[-1]
                frames.append({'file': re.sub(r'[^A-Za-z0-9_.-]', '_', basename)[:80],
                               'line': f['line'],
                               'function': re.sub(r'[^A-Za-z0-9_<>]', '_', f['function'])[:80]})
            record = {'phase': raw['phase'], 'exception_type': raw['exception_type'],
                      'message': sanitize(raw['message'], 512), 'frames': frames}
            break
        except (ValueError, TypeError, KeyError):
            continue
    kind = parent_kind
    # Do not let forged stderr reclassify a successful result or parent violation.
    if parent_kind == 'worker_exit' and record:
        if record['phase'].endswith('_import'):
            kind = 'import_failure'
        elif record['phase'].endswith('_return'):
            kind = 'return_failure'
        else:
            kind = 'runtime_exception'
    rendered = ''
    if record:
        rendered = '\n'.join(f"{f['file']}:{f['line']} in {f['function']}" for f in record['frames'])
        rendered += f"\n{record['exception_type']}: {record['message']}"
    elif text:
        rendered = sanitize(text)
    return {'schema_version': 1, 'parent_observation': parent_kind,
            'category': kind, 'category_basis': 'worker_reported_untrusted' if kind != parent_kind else 'parent_observed',
            'exit_code': exit_code, 'stderr_bytes_observed': tail.total,
            'tail_truncated': tail.total > len(tail.tail),
            'worker_exception': record, 'excerpt': sanitize(rendered),
            'trust': 'Untrusted diagnostic data only; cannot award correctness, coverage or fitness.'}

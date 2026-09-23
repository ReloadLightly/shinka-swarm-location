"""Bounded, non-authoritative worker diagnostics; never a scoring input.

Sanitization is deliberately lossy and best effort, not a secrecy or prompt-
injection guarantee. The containment contract, not redaction, excludes secrets.
"""
from __future__ import annotations
import json
import os
import re
import unicodedata

PROFILE = 'm7-evidence-v1'
STDERR_LIMIT = 16_384
EXCERPT_LIMIT = 2_048
EXCEPTION_PREFIX = 'M7_EXCEPTION '
PHASES = {'setup', 'candidate_import', 'candidate_run', 'candidate_return',
          'baseline_import', 'baseline_run', 'report'}


def sanitize(text: object, limit: int = EXCERPT_LIMIT) -> str:
    """Remove common secret/path/control patterns before truncating output."""
    value = str(text)[:STDERR_LIMIT]
    value = re.sub(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|$))', '', value)
    value = ''.join(c for c in value if c in '\n\t' or not unicodedata.category(c).startswith('C'))
    value = re.sub(r'(?i)(?:https?|file)://[^\s<>\"\']+', '<url>', value)
    value = re.sub(r'(?i)\b(?:sk-[a-z0-9_-]+|gh[pousr]_[a-z0-9_]+|github_pat_[a-z0-9_]+|AKIA[A-Z0-9]+)\b', '<secret>', value)
    value = re.sub(r'(?im)(?:[\"\']?[\w.-]*(?:token|password|passwd|secret|api[_-]?key|authorization)[\w.-]*[\"\']?\s*[:=]\s*|\bbearer\s+)[^\n,;}]+', '<credential redacted>', value)
    value = re.sub(r'(?<!\w)(?:[A-Za-z]:\\|/|~/)[^\s\"\'<>:,)\]]+', '<path>', value)
    value = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '<email>', value)
    value = re.sub(r'\b[A-Za-z0-9_+=/-]{48,}\b', '<long token>', value)
    value = re.sub(r'\[\s*-?\d+(?:\s*,\s*-?\d+)+\s*\]', '<node sequence omitted>', value)
    # Escape markup/role delimiters. This does not make arbitrary text trustworthy.
    value = value.replace('```', "''' ").replace('<|', '[role-delimiter ').replace('|>', ' ]')
    if len(value) > limit:
        value = value[:max(0, limit - 16)] + ' ...[truncated]'
    return value


class StderrTail:
    """Constant-memory suffix, drained without blocking the incumbent clock."""
    def __init__(self):
        self.buffer = bytearray()
        self.bytes_read = 0
        self.drain_incomplete = False

    def add(self, data: bytes) -> None:
        self.bytes_read += len(data)
        self.buffer.extend(data[-STDERR_LIMIT:])
        del self.buffer[:-STDERR_LIMIT]

    def read_ready(self, stream) -> bool:
        try:
            data = os.read(stream.fileno(), STDERR_LIMIT)
        except BlockingIOError:
            return True
        if data:
            self.add(data)
        return bool(data)

    def drain(self, stream) -> None:
        # Child has been stopped. Do not wait on descendants keeping a pipe open.
        for _ in range(64):
            try:
                data = os.read(stream.fileno(), STDERR_LIMIT)
            except BlockingIOError:
                self.drain_incomplete = True
                return
            if not data:
                return
            self.add(data)
        self.drain_incomplete = True

    def describe(self) -> dict:
        text = bytes(self.buffer).decode('utf-8', errors='replace')
        # If the retained suffix starts mid-line, drop that fragment, which could
        # otherwise lose the identifying prefix of a secret or structured record.
        if self.bytes_read > len(self.buffer):
            text = text.partition('\n')[2]
        hint = None
        for line in text.splitlines()[-64:]:
            if not line.startswith(EXCEPTION_PREFIX):
                continue
            try:
                raw = json.loads(line[len(EXCEPTION_PREFIX):])
                if not isinstance(raw, dict) or raw.get('phase') not in PHASES:
                    continue
                kind = raw.get('exception_type', '')
                if not isinstance(kind, str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,79}', kind):
                    continue
                frames = []
                for frame in raw.get('frames', [])[-8:]:
                    if (not isinstance(frame, dict) or type(frame.get('line')) is not int
                            or not 0 < frame['line'] < 10_000_000):
                        continue
                    name = frame.get('file', '')
                    function = frame.get('function', '')
                    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.]{0,79}\.py', name)
                            or not isinstance(function, str) or len(function) > 80):
                        continue
                    frames.append({'file': name, 'line': frame['line'], 'function': sanitize(function, 80)})
                hint = {'reported_phase': raw['phase'], 'exception_type': kind,
                        'message': sanitize(raw.get('message', ''), 640), 'frames': frames,
                        'provenance': 'untrusted_worker_exception_hint'}
            except (ValueError, TypeError, KeyError):
                continue
        return {'profile': PROFILE, 'provenance': 'untrusted_worker_stderr',
                'stderr_bytes_read': self.bytes_read,
                'stderr_retained_bytes': len(self.buffer),
                'stderr_truncated': self.bytes_read > len(self.buffer),
                'drain_incomplete': self.drain_incomplete,
                'stderr_excerpt': sanitize(text, EXCERPT_LIMIT), 'exception': hint,
                'scoring_input': False}


def emit_exception(exc: BaseException, phase: str, stream) -> None:
    """Worker hint: no locals, no source lines, basename/line frames only."""
    frames = []
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append({'file': os.path.basename(code.co_filename), 'line': tb.tb_lineno,
                       'function': code.co_name})
        frames = frames[-8:]
        tb = tb.tb_next
    if isinstance(exc, SyntaxError) and exc.lineno:
        frames.append({'file': 'candidate.py', 'line': exc.lineno, 'function': '<module>'})
    # Avoid executing arbitrary __str__ on exception objects supplied by a candidate.
    args = getattr(exc, 'args', ())
    message = ' | '.join(str(a)[:1024] for a in args[:3] if type(a) in (str, int, float))
    payload = {'phase': phase, 'exception_type': type(exc).__name__,
               'message': sanitize(message, 640), 'frames': frames[-8:]}
    stream.write(EXCEPTION_PREFIX + json.dumps(payload, ensure_ascii=True) + '\n')
    stream.flush()


def host_category(error: str | None, termination: str) -> str:
    """Classification based only on parent observations, never stderr claims."""
    if error is None:
        return 'search_deadline' if termination == 'deadline' else 'completed'
    if termination == 'setup_timeout':
        return 'setup_timeout'
    if error.startswith('invalid deployment:'):
        return 'invalid_deployment'
    if error.startswith('invalid online bound:'):
        return 'invalid_bound'
    if 'limit exceeded' in error or 'message limit' in error:
        return 'output_limit'
    if any(s in error for s in ('protocol', 'ready message', 'after done', 'JSON', 'Expecting value', 'selected must')):
        return 'protocol_violation'
    if 'worker did not finish cleanly' in error:
        return 'worker_exit'
    return 'execution_failure'


def repair_hint(diagnostic: dict, correct: bool) -> str:
    """Useful subtype only; it must not change validity or incumbent coverage."""
    category = diagnostic['host_category']
    if correct or category != 'worker_exit':
        return category
    hint = diagnostic.get('exception') or {}
    if hint.get('reported_phase') in ('candidate_import', 'baseline_import'):
        return 'import_failure'
    if hint.get('reported_phase') in ('report', 'candidate_return'):
        return 'invalid_deployment_hint'
    return 'runtime_exception' if hint else 'worker_exit'

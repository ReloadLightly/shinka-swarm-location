"""Size-limited diagnostics; no environment or credential values are collected."""
import re


class Tail:
    def __init__(self, limit=16384):
        self.limit, self.data, self.total = limit, bytearray(), 0

    def add(self, data):
        self.total += len(data)
        self.data.extend(data)
        if len(self.data) > self.limit:
            del self.data[:-self.limit]

    def text(self):
        return redact(self.data.decode('utf-8', errors='replace'))


def redact(text):
    text = re.sub(r'(?i)(?:sk-[A-Za-z0-9_\-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]+)', '[REDACTED]', text)
    text = re.sub(r'(?i)(authorization\s*[:=]\s*[\"\']?\s*(?:bearer|basic)\s+)\S+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[\"\']?\s*[:=]\s*[\"\']?)[^\s\"\',;]+', r'\1[REDACTED]', text)
    text = re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[REDACTED]@', text)
    return text


def failure_kind(error, stderr='', phase=None, returncode=None):
    if not error:
        return None
    if 'MemoryError' in stderr:
        return 'memory_exhaustion'
    if returncode in (-9, 137):
        return 'resource_or_external_kill'  # Not proof of OOM.
    if 'setup timeout' in error:
        return 'setup_timeout'
    if phase == 'setup':
        return 'worker_setup'
    if phase == 'candidate_import':
        return 'candidate_import'
    if 'deployment' in error:
        return 'invalid_deployment'
    if 'bound' in error or 'certificate' in error:
        return 'invalid_certificate'
    if 'protocol' in error or 'message' in error or 'output' in error:
        return 'invalid_protocol'
    return 'candidate_runtime'

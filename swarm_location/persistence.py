"""Atomic, identity-bound storage for prepared data and completed evaluations."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def exclusive(path):
    """Fail promptly on concurrent use; kernel releases the lock after a crash."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'evaluation/cache already in use: {path}') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class CaseStore:
    """Immutable completed trials, not a best-of-retries selection mechanism.

    Successful and invalid candidate trials are terminal. Only unfinished or
    explicitly infrastructure-failed trials may resume. A new independent timing
    repetition needs a new store, never deletion of an inconvenient trial.
    """
    def __init__(self, root, identity):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.identity = digest(identity)
        manifest = self.root / 'identity.json'
        expected = {'schema_version': 1, 'identity': identity, 'sha256': self.identity}
        if manifest.exists():
            if json.loads(manifest.read_text()) != expected:
                raise ValueError('resume identity mismatch; retain this record and use a new output path')
        else:
            if any(self.root.glob('*.case.json')) or any(self.root.glob('*.capture.json')):
                raise ValueError('case files without a resume identity')
            atomic_json(manifest, expected)

    def path(self, key, suffix='case'):
        return self.root / (digest(key) + '.' + suffix + '.json')

    def get(self, key):
        path = self.path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if (data.get('identity') != self.identity or data.get('key') != key or
                data.get('sha256') != digest(data.get('payload'))):
            raise ValueError('completed case checksum or identity mismatch')
        return data['payload']

    def put(self, key, payload):
        existing = self.get(key)
        if existing is not None:
            if existing != payload:
                raise ValueError('refusing to replace a completed trial')
            return
        atomic_json(self.path(key), {'identity': self.identity, 'key': key,
                                    'payload': payload, 'sha256': digest(payload)})

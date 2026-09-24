"""Content-addressed common route DAGs, streamed as data-only JSONL/gzip.

No pickle, code execution, route enumeration, or sampled routes. Only evaluator-
created, checksum-verified artifacts are loaded. Each worker hydrates private
objects; it never returns mutable preparation to the shared cache.
"""
import gzip
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType

from .core import Instance, ShortestPathCoverage, SourceDAG, CompactCounts, CompactPredecessors
from .persistence import atomic_json, canonical, digest, exclusive, file_digest, sync_directory

SCHEMA = 'exact-route-dags-v1'


def preparation_identity(instance):
    return {'schema': SCHEMA, 'instance_sha256': digest(instance.to_dict()),
            'source_sha256': {n: file_digest(Path(__file__).parent / n)
                              for n in ('core.py', 'prepared.py')}}


def load_prepared(path, expected_sha256, expected_instance=None):
    """Load one origin at a time, retaining arbitrarily large integer counts."""
    if file_digest(path) != expected_sha256:
        raise ValueError('prepared DAG checksum mismatch')
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        header = json.loads(stream.readline())
        if header.get('schema') != SCHEMA:
            raise ValueError('unknown prepared DAG schema')
        instance = Instance.from_dict(header['instance'])
        if expected_instance is not None and instance != expected_instance:
            raise ValueError('prepared DAG instance mismatch')
        if header['identity'] != preparation_identity(instance):
            raise ValueError('prepared DAG source/instance identity mismatch')
        index = {v: i for i, v in enumerate(instance.nodes)}
        dags = []
        expected_origins = {}
        for s, t, q in instance.od:
            if q:
                expected_origins.setdefault(s, []).append((t, q))
        for line in stream:
            record = json.loads(line)
            source = record['source']
            order = tuple(record['order'])
            destinations = tuple((t, q) for t, q in record['destinations'])
            if (source not in expected_origins or
                    destinations != tuple(sorted(expected_origins.pop(source))) or
                    len(order) != len(set(order)) or not set(order).issubset(index) or
                    len(order) != len(record['counts']) or len(order) != len(record['predecessors'])):
                raise ValueError('invalid prepared origin DAG')
            # Hex avoids Python's decimal-digit conversion ceiling for huge counts.
            counts = dict(zip(order, (int(v, 16) for v in record['counts'])))
            predecessors = dict(zip(order, (tuple(v) for v in record['predecessors'])))
            seen = set()
            for v in order:
                parents = predecessors[v]
                if (not set(parents).issubset(seen) or len(parents) != len(set(parents)) or
                        counts[v] != (1 if v == source else sum(counts[u] for u in parents)) or
                        counts[v] <= 0 or (v == source and parents)):
                    raise ValueError('invalid prepared path recurrence')
                seen.add(v)
            if not all(t in seen for t, _ in destinations):
                raise ValueError('missing demanded destination')
            if len(index) >= 1024:
                counts = CompactCounts(index, order, counts)
                predecessors = CompactPredecessors(index, order, predecessors, counts)
            else:
                counts, predecessors = MappingProxyType(counts), MappingProxyType(predecessors)
            dags.append(SourceDAG(source, order, predecessors, counts, destinations))
        if expected_origins:
            raise ValueError('prepared cache is missing origins')
    return ShortestPathCoverage.from_dags(instance, tuple(dags))


def ensure_prepared(instance, directory):
    identity = preparation_identity(instance)
    key = digest(identity)
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path, manifest = root / (key + '.jsonl.gz'), root / (key + '.json')
    with exclusive(root / (key + '.lock')):
        if manifest.exists():
            record = json.loads(manifest.read_text())
            if record['identity'] != identity or file_digest(path) != record['sha256']:
                raise ValueError('prepared cache corrupt; preserve it and use a new cache directory')
            return path, record['sha256'], True
        # Incomplete payloads have no manifest and may be replaced after a crash.
        oracle = ShortestPathCoverage(instance)
        fd, temporary = tempfile.mkstemp(prefix='.' + key, dir=root)
        try:
            with os.fdopen(fd, 'wb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as stream:
                    stream.write(canonical({'schema': SCHEMA, 'identity': identity,
                                            'instance': instance.to_dict()}) + b'\n')
                    for dag in oracle.dags:
                        stream.write(canonical({'source': dag.source, 'order': dag.order,
                            'predecessors': [dag.predecessors[v] for v in dag.order],
                            'counts': [hex(dag.counts[v]) for v in dag.order],
                            'destinations': dag.destinations}) + b'\n')
                raw.flush()
                os.fsync(raw.fileno())
            os.chmod(temporary, 0o444)
            os.replace(temporary, path)
            sync_directory(root)
            checksum = file_digest(path)
            atomic_json(manifest, {'identity': identity, 'sha256': checksum})
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path, checksum, False

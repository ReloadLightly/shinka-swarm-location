"""Verify protected historical results, configurations and solver bytes unchanged."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_anytime import write_json

BASE = 'a2f9f268d231ec8caae3b6987392eb643967dd60'
PROTECTED = [
    'results/step1', 'results/step2', 'results/step3', 'results/strong-baselines',
    'results/quality-certificates', 'results/exchange-landscape',
    'configs/evolution.json', 'configs/evolution_m3.json', 'configs/m3_launch_request.json',
    'configs/source_catalog_m3.json', 'configs/strong_baselines.json',
    'initial.py', 'anytime_initial.py', 'evaluate.py', 'benchmark.py',
    'swarm_location/core.py', 'swarm_location/search.py', 'swarm_location/anytime.py',
    'swarm_location/anytime_worker.py', 'swarm_location/anytime_baselines.py',
    'swarm_location/baselines.py', 'swarm_location/strong_baselines.py',
    'swarm_location/bounded_search.py', 'swarm_location/route_search.py',
    'swarm_location/isolation.py', 'swarm_location/certificates.py',
    'swarm_location/certificate_references.py', 'swarm_location/baseline_proofs.py',
    'data/sioux_falls.json', 'requirements-shinka.txt', 'requirements-certificates.txt',
]


def check(base: str = BASE, allow_source_changes=()) -> dict:
    allowed = set(allow_source_changes)
    if not allowed <= {'swarm_location/strong_baselines.py', 'swarm_location/anytime.py', 'swarm_location/anytime_worker.py'}:
        raise ValueError('only declared M6 fixed-method and M7 receiver/diagnostic extensions may be excepted')
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT)
    paths = git('ls-tree', '-r', '--name-only', base, '--', *PROTECTED).decode().splitlines()
    if not paths:
        raise ValueError('historical base not available')
    hashes, source_changes = {}, {}
    for path in paths:
        original = git('show', base+':'+path)
        if not (ROOT/path).is_file() or (ROOT/path).read_bytes() != original:
            if path not in allowed or not (ROOT/path).is_file():
                raise ValueError('protected historical bytes changed: '+path)
            source_changes[path] = {'historical_sha256': hashlib.sha256(original).hexdigest(),
                                    'current_sha256': hashlib.sha256((ROOT/path).read_bytes()).hexdigest()}
            continue
        hashes[path] = hashlib.sha256(original).hexdigest()
    old = git('show', base+':README.md').decode()
    new = (ROOT/'README.md').read_text()
    blocks = re.findall(r'<!-- ([A-Z0-9-]+):START -->', old)
    for name in blocks:
        start, end = '<!-- '+name+':START -->', '<!-- '+name+':END -->'
        if new.count(start) != 1 or new.count(end) != 1:
            raise ValueError('missing/duplicate historical README block: '+name)
        if old.split(start)[1].split(end)[0] != new.split(start)[1].split(end)[0]:
            raise ValueError('historical README result block changed: '+name)
    return {'success': True, 'base_commit': base, 'protected_file_count': len(hashes),
            'protected_file_sha256': hashes, 'declared_source_changes': source_changes, 'historical_readme_blocks_unchanged': blocks,
            'scope': 'Byte preservation, not a new timing run or numerical reproduction'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', default=BASE)
    p.add_argument('--output', type=Path)
    p.add_argument('--allow-source-change', action='append', default=[])
    a = p.parse_args(); result = check(a.base, a.allow_source_change)
    if a.output: write_json(a.output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'protected_file_sha256'}, indent=2))

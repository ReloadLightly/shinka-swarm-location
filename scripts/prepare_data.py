"""Rebuild the development fixture from hash-pinned upstream TNTP bytes.

Use --source-dir for an existing download, or --download explicitly. The source
network is a public debugging benchmark, NOT the chapter's Israeli dataset.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_location import Instance

COMMIT = '977ee75c6906337c0c7d229a1336107c7cdb533e'
FILES = {'SiouxFalls_net.tntp': '66d0eca4ddcfb82f861bea040060deab7a741b2f',
         'SiouxFalls_trips.tntp': 'db70eda57738877811e9ac07c25a567973d3b6a0'}


def blob_sha(content: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()


def prepare(source_dir: Path, output: Path, download: bool = False) -> dict:
    source_dir.mkdir(parents=True, exist_ok=True)
    texts = {}
    for name, expected in FILES.items():
        path = source_dir / name
        if download:
            url = f'https://raw.githubusercontent.com/bstabler/TransportationNetworks/{COMMIT}/SiouxFalls/{name}'
            with urlopen(url, timeout=30) as response:
                content = response.read()
            if blob_sha(content) != expected:
                raise ValueError(f'upstream blob mismatch for {name}')
            path.write_bytes(content)
        content = path.read_bytes()
        if blob_sha(content) != expected:
            raise ValueError(f'wrong source version or modified bytes: {name}')
        texts[name] = content.decode('utf-8')
    net = texts['SiouxFalls_net.tntp']
    meta = dict(re.findall(r'<([^>]+)>\s*([^\n]*)', net))
    edges = []
    for line in net.split('<END OF METADATA>', 1)[1].splitlines():
        line = line.strip()
        if not line or line.startswith('~'):
            continue
        fields = line.rstrip(';').split()
        edges.append([int(fields[0]), int(fields[1]), str(Fraction(fields[4]))])
    od, source = [], None
    trips = texts['SiouxFalls_trips.tntp']
    for line in trips.split('<END OF METADATA>', 1)[1].splitlines():
        origin = re.match(r'\s*Origin\s+(\d+)', line)
        if origin:
            source = int(origin.group(1))
            continue
        for target, value in re.findall(r'(\d+)\s*:\s*([\d.eE+-]+)\s*;', line):
            q = Fraction(value)
            if q > 0:
                if source is None:
                    raise ValueError('demand before Origin')
                od.append([source, int(target), int(q) if q.denominator == 1 else float(q)])
    if len(edges) != int(meta['NUMBER OF LINKS'].strip()):
        raise ValueError('link count mismatch')
    declared = float(re.search(r'<TOTAL OD FLOW>\s*([\d.eE+-]+)', trips)[1])
    if sum(q for _, _, q in od) != declared:
        raise ValueError('OD total mismatch')
    result = {'name': 'SiouxFalls-free-flow', 'schema_version': 1,
              'nodes': list(range(1, int(meta['NUMBER OF NODES'].strip()) + 1)),
              'edges': edges, 'od': od, 'first_thru_node': int(meta['FIRST THRU NODE'].strip()),
              'provenance': {'classification': 'public_benchmark_substitution_not_original_chapter_data',
                  'upstream': 'bstabler/TransportationNetworks', 'commit': COMMIT,
                  'network_path': 'SiouxFalls/SiouxFalls_net.tntp', 'trips_path': 'SiouxFalls/SiouxFalls_trips.tntp',
                  'network_git_blob_sha': FILES['SiouxFalls_net.tntp'], 'trips_git_blob_sha': FILES['SiouxFalls_trips.tntp'],
                  'routing': 'free_flow_time; uniform over all exactly equal shortest routes; endpoints included',
                  'warning': 'Upstream labels Sioux Falls not realistic and suitable for code debugging. Not a large-scale or held-out scientific result. No congestion assignment or current real traffic inferred.'}}
    Instance.from_dict(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, separators=(',', ':')) + '\n', encoding='utf-8')
    print(f'Wrote {output}; sha256={hashlib.sha256(output.read_bytes()).hexdigest()}')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'data/raw')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/sioux_falls.json')
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    prepare(args.source_dir, args.output, args.download)

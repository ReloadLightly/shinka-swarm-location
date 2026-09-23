"""Materialize one whole-network split, or audit all input structure without scoring.

M2 routing/coverage and strict parser are reused. Only rounding-size differences
between a metadata total and its exact OD sum are permitted, explicitly recorded.
Original bytes and individual OD entries are NEVER rewritten or rescaled.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_suite import parse_tntp
from swarm_location.core import Instance, ShortestPathCoverage
from swarm_location.suite import file_sha256
from evaluate_anytime import write_json


def decimal_string(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = max(100, len(str(value.numerator)) + len(str(value.denominator)) + 10)
        text = format(Decimal(value.numerator) / Decimal(value.denominator), 'f')
    if Fraction(text) != value:
        raise ValueError('OD sum is not exactly representable as a finite decimal')
    return text


def parse_documented(network: str, trips: str, name: str, tolerance: dict) -> tuple[dict, dict]:
    """Accept only a documented, bounded header discrepancy; preserve every OD."""
    if trips.count('<END OF METADATA>') != 1:
        raise ValueError('expected exactly one demand metadata boundary')
    # TNTP's documented comment prefix also occurs inside the Chicago trip body.
    # Ignore comment lines in parser input, never in the preserved source bytes.
    comments = sum(line.lstrip().startswith('~') for line in trips.splitlines())
    trips = '\n'.join(line for line in trips.splitlines() if not line.lstrip().startswith('~'))
    body = trips.split('<END OF METADATA>', 1)[1]
    amounts = re.findall(r'\d+\s*:\s*([\d.eE+-]+)\s*;', body)
    total = sum((Fraction(x) for x in amounts), Fraction(0))
    matches = list(re.finditer(r'(<TOTAL OD FLOW>\s*)([\d.eE+-]+)', trips))
    if len(matches) != 1 or total <= 0:
        raise ValueError('missing/ambiguous OD total or nonpositive demand')
    match = matches[0]
    declared = Fraction(match[2])
    difference = total - declared
    absolute, relative = Fraction(tolerance['absolute']), Fraction(tolerance['relative'])
    if absolute < 0 or relative < 0 or declared < 0:
        raise ValueError('nonnegative tolerances and header demand required')
    limit = max(absolute, relative * max(abs(total), abs(declared)))
    if abs(difference) > limit:
        raise ValueError(f'OD header differs substantively: exact sum={decimal_string(total)}, header={match[2]}')
    # Feed an exact HEADER to the unchanged parser, which checks all record syntax,
    # positivity, duplicates, intrazonal demand, directed edges and centroid rules.
    normalized = trips[:match.start(2)] + decimal_string(total) + trips[match.end(2):]
    data = parse_tntp(network, normalized, name)
    note = {'declared_header': match[2], 'exact_od_sum': decimal_string(total),
            'sum_minus_header': decimal_string(difference), 'header_only_roundoff': bool(difference),
            'tolerance': tolerance, 'od_entries_modified': 0, 'od_entries_dropped': 0,
            'source_bytes_modified': False, 'comment_lines_ignored': comments}
    return data, note


def catalog_checked(path: Path) -> dict:
    catalog = json.loads(Path(path).read_text())
    if catalog.get('schema_version') != 1:
        raise ValueError('expected source catalog schema 1')
    ids, groups, source_paths = set(), {}, {}
    for entry in catalog['datasets']:
        if entry['id'] in ids or entry['split'] not in ('development','validation','test'):
            raise ValueError('duplicate dataset ID or invalid split')
        ids.add(entry['id'])
        group = entry['source_graph']
        if group in groups and groups[group] != entry['split']:
            raise ValueError('source family crosses split boundaries')
        groups[group] = entry['split']
        key = entry['files']['network']['git_blob_sha1']
        if key in source_paths and source_paths[key] != entry['split']:
            raise ValueError('same source topology crosses split boundaries')
        source_paths[key] = entry['split']
    return catalog


def source_bytes(item: dict, catalog: dict, raw_dir: Path, download: bool) -> bytes:
    relative = Path(item['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe source path')
    path = raw_dir / relative
    if download and not path.is_file():
        url = f"https://raw.githubusercontent.com/{catalog['upstream_repository']}/{catalog['upstream_commit']}/{item['path']}"
        with urlopen(url, timeout=90) as response:
            data = response.read(20_000_001)
        if len(data) > 20_000_000:
            raise ValueError('source exceeds 20 MB import limit')
    else:
        data = path.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != item['git_blob_sha1']:
        raise ValueError(f"pinned source mismatch: {item['path']}")
    if download and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return data


def prepare(catalog_path: Path, output: Path, raw_dir: Path, split: str, download=False, audit_only=False,
            *, comparison_profile: Path | None = None):
    catalog_path, output, raw_dir = map(Path, (catalog_path, output, raw_dir))
    catalog = catalog_checked(catalog_path)
    from swarm_location.comparisons import load_profile, bind_profile
    profile = load_profile(comparison_profile) if comparison_profile is not None else None
    if split not in ('development','validation','test','all') or (split == 'all' and not audit_only):
        raise ValueError('all splits may only be structurally audited; materialize one split per workspace')
    entries = [e for e in catalog['datasets'] if split == 'all' or e['split'] == split]
    if not entries:
        raise ValueError('requested split has no source networks')
    existing_suite = output/'suite.json'
    expected_comparison = None if profile is None else {**profile, 'stage': split}
    if existing_suite.exists() and json.loads(existing_suite.read_text()).get('comparison_profile') != expected_comparison:
        raise ValueError('cannot replace a prepared suite with another comparator profile; use a new output directory')
    datasets, audit = [], []
    output.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        contents, provenance = {}, {}
        for role, item in entry['files'].items():
            content = source_bytes(item, catalog, raw_dir, download)
            contents[role] = content.decode('utf-8-sig')
            provenance[role] = {**item,'sha256':hashlib.sha256(content).hexdigest()}
        data, rounding = parse_documented(contents['network'], contents['trips'],entry['id'],catalog['header_total_tolerance'])
        instance = Instance.from_dict(data)
        if len(instance.nodes) != entry['expected_nodes'] or len(instance.edges) != entry['expected_edges']:
            raise ValueError(f"unexpected dimensions: {entry['id']}")
        oracle = ShortestPathCoverage(instance)  # Reachability/counting only; no S is scored.
        data['provenance'] = {'catalog_sha256':file_sha256(catalog_path),
            'upstream_commit':catalog['upstream_commit'],'files':provenance,'scenario':entry['scenario'],
            'routing':catalog['routing'],'license':catalog['license'],'header_audit':rounding}
        encoded = (json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode()
        digest = hashlib.sha256(encoded).hexdigest()
        filename = entry['id'] + '.json'
        row = {'id':entry['id'],'source_graph':entry['source_graph'],'split':entry['split'],
            'nodes':len(instance.nodes),'edges':len(instance.edges),'positive_od_pairs':len(instance.od),
            'total_demand':oracle.total_demand,'origins':len(oracle.dags),'first_thru_node':instance.first_thru_node,
            'prepared_sha256':digest,'header_audit':rounding,'files':provenance,
            'shortest_routes':sum(d.counts[t] for d in oracle.dags for t,_ in d.destinations),
            'positive_demand_reachable':True,'solver_evaluations':0}
        audit.append(row)
        write_json(output/'input_audit_progress.json',{'datasets':audit,'solver_evaluations':0,'complete':False})
        if not audit_only:
            target = output / filename
            if target.exists() and target.read_bytes() != encoded:
                raise ValueError(f'refusing to overwrite a different prepared dataset: {target}')
            target.write_bytes(encoded)
            datasets.append({'id':entry['id'],'source_graph':entry['source_graph'],'split':split,
                'path':filename,'sha256':digest,'budgets':entry['budgets']})
    report={'catalog_sha256':file_sha256(catalog_path),'scope':'Input structure, demand and reachability only; no deployment scoring',
            'datasets':audit,'excluded':catalog['excluded'],'solver_evaluations':0}
    write_json(output/'data_audit.json',report)
    (output/'input_audit_progress.json').unlink(missing_ok=True)
    if not audit_only:
        suite={'schema_version':2,'name':f'm3-{split}','catalog_sha256':file_sha256(catalog_path),
            'checkpoints_seconds':catalog['checkpoints_seconds'],'seeds':catalog['seeds'][split],
            'extra_baselines':['topk'],'datasets':datasets,
            'scope':'Whole source-family split; public data may have occurred in model pretraining'}
        if profile is not None:
            suite['name'] = profile['definition']['profile_id'] + '-' + split
            suite = bind_profile(suite, profile, split)
            existing = output/'suite.json'
            if existing.exists() and json.loads(existing.read_text()) != suite:
                raise ValueError('comparison suite already exists with a different protocol; use a new output directory')
        write_json(output/'suite.json',suite)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',type=Path,default=ROOT/'configs/source_catalog_m3.json')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--raw-dir',type=Path,default=ROOT/'data/raw_m3')
    p.add_argument('--split',choices=['development','validation','test','all'],default='development')
    p.add_argument('--download',action='store_true')
    p.add_argument('--audit-only',action='store_true')
    p.add_argument('--comparison-profile',type=Path,help='Versioned staged controls; omitted retains historical M3')
    a=p.parse_args();print(json.dumps(prepare(a.catalog,a.output,a.raw_dir,a.split,a.download,a.audit_only,
        comparison_profile=a.comparison_profile),indent=2))

if __name__=='__main__':main()

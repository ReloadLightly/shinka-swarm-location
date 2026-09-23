"""Versioned TNTP import with exact demand accounting and preserved connectors."""
from fractions import Fraction
import hashlib
from pathlib import Path
import re
import urllib.request
from .core import Instance


def source_bytes(spec, catalog, raw_dir, download=False):
    path = Path(raw_dir) / spec["path"]
    if not path.is_file():
        if not download:
            raise FileNotFoundError(f"Missing pinned source {path}; supply raw files or use --download")
        url = "https://raw.githubusercontent.com/" + catalog["upstream_repository"] + "/" + catalog["upstream_commit"] + "/" + spec["path"]
        with urllib.request.urlopen(url, timeout=120) as response:
            content = response.read()
        digest = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if digest != spec["git_blob_sha1"]:
            raise ValueError("downloaded source blob mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    content = path.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    if digest != spec["git_blob_sha1"]:
        raise ValueError("source blob mismatch: " + spec["path"])
    return content


def parse_documented(network, trips, name, tolerance, *, schema_version=2, intrazonal="exclude"):
    if schema_version != 2 or intrazonal not in ("exclude", "reject"):
        raise ValueError("this importer requires schema 2 and an explicit intrazonal policy")
    metadata = dict(re.findall(r"<([^>]+)>\s*([^\n]*)", network))
    n = int(metadata["NUMBER OF NODES"].strip())
    first = int(metadata.get("FIRST THRU NODE", "1").strip())
    body = network.split("<END OF METADATA>", 1)[1]
    edges = []
    for line in body.splitlines():
        line = line.split("~", 1)[0].strip()
        if not line:
            continue
        fields = line.rstrip(";").split()
        if len(fields) < 5:
            raise ValueError("malformed TNTP edge")
        u, v, weight = int(fields[0]), int(fields[1]), Fraction(fields[4])
        edges.append([u, v, str(weight)])
    if "NUMBER OF LINKS" in metadata and len(edges) != int(metadata["NUMBER OF LINKS"]):
        raise ValueError("TNTP link count mismatch")
    demand_meta = dict(re.findall(r"<([^>]+)>\s*([^\n]*)", trips))
    declared = Fraction(demand_meta["TOTAL OD FLOW"].strip())
    body = trips.split("<END OF METADATA>", 1)[1]
    source, total, dropped, seen, od, dropped_pairs = None, Fraction(), Fraction(), set(), [], 0
    for line in body.splitlines():
        line = line.split("~", 1)[0].strip()
        if not line:
            continue
        origin = re.fullmatch(r"Origin\s+(\d+)", line, re.IGNORECASE)
        if origin:
            source = int(origin[1]); continue
        if source is None:
            raise ValueError("OD records precede their origin")
        matches = list(re.finditer(r"(\d+)\s*:\s*([+\-\d.eE]+)\s*;", line))
        rest = re.sub(r"(\d+)\s*:\s*([+\-\d.eE]+)\s*;", "", line).strip()
        if not matches or rest:
            raise ValueError("malformed OD record")
        for match in matches:
            target, q = int(match[1]), Fraction(match[2])
            if (source, target) in seen or q < 0 or not 1 <= source <= n or not 1 <= target <= n:
                raise ValueError("invalid or duplicate OD record")
            seen.add((source, target)); total += q
            if source == target and q > 0:
                if intrazonal == "reject":
                    raise ValueError("positive intrazonal demand")
                dropped += q; dropped_pairs += 1
            elif q > 0:
                od.append([source, target, int(q) if q.denominator == 1 else float(q)])
    error = abs(total-declared)
    allowed = max(Fraction(str(tolerance.get("absolute", 0))), abs(declared)*Fraction(str(tolerance.get("relative", 0))))
    if error > allowed:
        raise ValueError(f"OD total differs from declared header by {error}")
    data = {"schema_version": 2, "name": name + "-free-flow", "nodes": list(range(1,n+1)),
            "edges": edges, "od": od, "first_thru_node": first}
    Instance.from_dict(data)
    audit = {"declared_total_demand_exact": str(declared), "parsed_total_demand_exact": str(total),
             "header_discrepancy_exact": str(error), "intrazonal_policy": intrazonal,
             "excluded_intrazonal_demand_exact": str(dropped), "od_entries_dropped": dropped_pairs,
             "retained_interzonal_demand_exact": str(total-dropped), "source_values_modified": False}
    return data, audit

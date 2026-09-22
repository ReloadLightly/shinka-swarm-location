"""Prepare two public development networks, pinned to upstream Git blob hashes.

No validation/test network is invented. Custom manifests can supply whole-network
holdouts later. Downloads are opt-in; no positive demand is silently discarded.
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
from swarm_location.core import Instance

COMMIT = "977ee75c6906337c0c7d229a1336107c7cdb533e"
SOURCES = {
    "SiouxFalls": ("66d0eca4ddcfb82f861bea040060deab7a741b2f", "db70eda57738877811e9ac07c25a567973d3b6a0"),
    "Anaheim": ("1a5600ffb343b9b391dab59a28b39d2a2869b645", "59146d9224872e06c00acee90bf25f7eed9c6fe3"),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_tntp(network, trips, name):
    metadata = dict(re.findall(r"<([^>]+)>\s*([^\n]*)", network))
    edges = []
    for line in network.split("<END OF METADATA>", 1)[1].splitlines():
        line = line.strip()
        if not line or line.startswith("~"):
            continue
        fields = line.rstrip(";").split()
        if len(fields) < 5:
            raise ValueError("incomplete TNTP link")
        edges.append([int(fields[0]), int(fields[1]), str(Fraction(fields[4]))])
    if len(edges) != int(metadata["NUMBER OF LINKS"]):
        raise ValueError("declared TNTP link count mismatch")
    od, source, seen, total = [], None, set(), Fraction(0)
    for line in trips.split("<END OF METADATA>", 1)[1].splitlines():
        origin = re.fullmatch(r"\s*Origin\s+(\d+)\s*", line)
        if origin:
            source = int(origin[1])
            continue
        if not line.strip():
            continue
        entries = re.findall(r"(\d+)\s*:\s*([\d.eE+-]+)\s*;", line)
        residue = re.sub(r"\d+\s*:\s*[\d.eE+-]+\s*;", "", line).strip()
        if not entries or residue:
            raise ValueError("unparsed TNTP demand content")
        for target, value in entries:
            target, q = int(target), Fraction(value)
            if source is None or q < 0 or (source, target) in seen:
                raise ValueError("invalid or duplicate demand entry")
            seen.add((source, target))
            total += q
            if q > 0:
                od.append([source, target, int(q) if q.denominator == 1 else float(q)])
    declared = Fraction(re.search(r"<TOTAL OD FLOW>\s*([\d.eE+-]+)", trips)[1])
    if total != declared:
        raise ValueError(f"demand total mismatch: {total} versus {declared}")
    data = {"schema_version": 1, "name": name + "-free-flow",
            "nodes": list(range(1, int(metadata["NUMBER OF NODES"]) + 1)),
            "edges": edges, "od": od, "first_thru_node": int(metadata["FIRST THRU NODE"])}
    Instance.from_dict(data)  # Reject parallel links, nonpositive times, positive intrazonal demand.
    return data


def prepare(output, source_dir, download=False):
    output, source_dir = Path(output), Path(source_dir)
    output.mkdir(parents=True, exist_ok=True)
    datasets = []
    for name, hashes in SOURCES.items():
        texts, provenance = [], []
        for suffix, expected in zip(("net", "trips"), hashes):
            relative = f"{name}/{name}_{suffix}.tntp"
            local = source_dir / relative
            url = f"https://raw.githubusercontent.com/bstabler/TransportationNetworks/{COMMIT}/{relative}"
            if download:
                with urlopen(url, timeout=60) as response:
                    content = response.read()
                actual = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
                if actual != expected:
                    raise ValueError(f"upstream blob mismatch: {relative}")
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(content)
            content = local.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            if actual != expected:
                raise ValueError(f"modified or wrong-version input: {relative}")
            texts.append(content.decode("utf-8"))
            provenance.append({"url": url, "git_blob_sha1": actual,
                               "sha256": hashlib.sha256(content).hexdigest()})
        data = parse_tntp(*texts, name)
        data["provenance"] = {"upstream_commit": COMMIT, "files": provenance,
            "classification": "historical_public_benchmark_not_chapter_replication",
            "terms": "academic research only; attribute original providers; see data/README.md",
            "scenario": "1992" if name == "Anaheim" else "debugging network, not realistic"}
        path = output / (name + ".json")
        path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
        datasets.append({"id": name, "source_graph": name, "split": "development",
                         "path": path.name, "sha256": sha256(path),
                         "budgets": [1, 3, 4, 6] if name == "SiouxFalls" else [3, 6, 12, 24]})
    suite = {"schema_version": 2, "name": "m2-development-commissioning",
             "checkpoints_seconds": [0.02, 0.1, 0.5, 2.0], "seeds": [0, 1, 2],
             "datasets": datasets,
             "scope": "Two development source networks; no held-out generalization claim."}
    (output / "suite.json").write_text(json.dumps(suite, indent=2) + "\n")
    print(json.dumps(suite, indent=2))
    return suite


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "data/commissioning")
    p.add_argument("--source-dir", type=Path, default=ROOT / "data/raw")
    p.add_argument("--download", action="store_true")
    a = p.parse_args()
    prepare(a.output, a.source_dir, a.download)

"""Import pinned, full-size TNTP networks without dropping zero-time connectors.

New data schema and explicit intrazonal exclusion leave historical M1--M6 files
unchanged. Chicago variants belong to ONE source family, never different splits.
Only the requested split is opened. --ids selects datasets, not subgraphs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_location.tntp_v2 import parse_documented, source_bytes
from swarm_location.core import Instance
from evaluate_anytime import write_json


def prepare(catalog_path, raw_dir, output, split="development", ids=None, download=False, time_profile="standard"):
    catalog_path, raw_dir, output = map(Path, (catalog_path, raw_dir, output))
    catalog = json.loads(catalog_path.read_text())
    profiles = catalog.get('time_profiles', {'standard': catalog['checkpoints_seconds']})
    if time_profile not in profiles:
        raise ValueError('unknown time profile')
    checkpoints = profiles[time_profile]
    from swarm_location.anytime import checkpoints_checked
    checkpoints_checked(checkpoints)
    groups, identifiers = {}, set()
    for item in catalog["datasets"]:
        if item["id"] in identifiers or item["split"] not in ("development", "validation", "test"):
            raise ValueError("duplicate ID or invalid split")
        identifiers.add(item["id"])
        group = item["source_graph"]
        if group in groups and groups[group] != item["split"]:
            raise ValueError("source family crosses split boundaries")
        groups[group] = item["split"]
    eligible = [d for d in catalog["datasets"] if d["split"] == split]
    if ids is not None and (not ids or not set(ids).issubset(d["id"] for d in eligible)):
        raise ValueError("requested dataset not in this split")
    selected = [d for d in eligible if ids is None or d["id"] in ids]
    if not selected:
        raise ValueError("no datasets in requested split")
    output.mkdir(parents=True, exist_ok=True)
    entries, audits = [], []
    for item in selected:
        net = source_bytes(item["files"]["network"], catalog, raw_dir, download).decode("utf-8-sig")
        trips = source_bytes(item["files"]["trips"], catalog, raw_dir, download).decode("utf-8-sig")
        data, audit = parse_documented(net, trips, item["id"], item.get("header_total_tolerance", catalog["header_total_tolerance"]),
                                     schema_version=2, intrazonal="exclude",
                                     shortest_path_ties=catalog["shortest_path_ties"],
                                     centroid_override=item.get("centroid_override"))
        instance = Instance.from_dict(data)
        if len(instance.nodes) != item["expected_nodes"] or len(instance.edges) != item["expected_edges"]:
            raise ValueError("source dimensions differ from catalog")
        data["provenance"] = {"upstream_commit": catalog["upstream_commit"], "files": item["files"],
                              "import_audit": audit, "routing": catalog["routing"]}
        path = output / (item["id"] + ".json")
        encoded = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if path.exists() and path.read_bytes() != encoded:
            raise ValueError("refusing to replace a different dataset")
        path.write_bytes(encoded)
        entries.append({"id": item["id"], "source_graph": item["source_graph"], "split": split,
                        "path": path.name, "sha256": hashlib.sha256(encoded).hexdigest(), "budgets": item["budgets"]})
        audits.append({"dataset": item["id"], "nodes": len(instance.nodes), "edges": len(instance.edges),
                       "positive_od_pairs": len(instance.od), "origins": len({s for s, _, _ in instance.od}),
                       "zero_weight_edges_preserved": sum(w == 0 for _, _, w in instance.edges), **audit})
    suite = {"schema_version": 2, "name": "chapter-search-" + split,
             "research_protocol": "chapter-search-v2", "datasets": entries,
             "checkpoints_seconds": checkpoints, "time_profile": time_profile, "seeds": catalog["seeds"][split],
             "fitness": {"coverage_weight": 0.5, "certificate_weight": 0.5},
             "setup_timeout_seconds": 1800, "relabel_seed": 90231,
             "controls": ["greedy", "early_celf_swap", "program:controls/dag_dfbnb.py", "program:controls/dag_potential.py"],
             "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest()}
    target = output / 'suite.json'
    if target.exists() and json.loads(target.read_text()) != suite:
        raise ValueError('a different suite already exists here; use a new output directory')
    write_json(target, suite)
    write_json(output / "import_audit.json", audits)
    return audits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", type=Path, default=ROOT / "configs/source_catalog_search.json")
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw_search")
    p.add_argument("--output", type=Path, default=ROOT / "data/search")
    p.add_argument("--split", choices=["development", "validation", "test"], default="development")
    p.add_argument("--ids", nargs="+")
    p.add_argument("--download", action="store_true")
    p.add_argument("--time-profile", default="standard", help="standard (60s) or chapter-hour (3600s); no runs are launched")
    a = p.parse_args()
    print(json.dumps(prepare(a.catalog, a.raw_dir, a.output, a.split, a.ids, a.download, a.time_profile), indent=2))

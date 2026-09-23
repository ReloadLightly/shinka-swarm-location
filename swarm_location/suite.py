"""Hash-verified benchmark manifests with whole-source-graph split boundaries."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .anytime import checkpoints_checked
from .core import Instance


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_suite(path, split="development"):
    path = Path(path).resolve()
    data = json.loads(path.read_text())
    if data.get("schema_version") != 2:
        raise ValueError("expected suite schema_version=2")
    if split not in ("development", "validation", "test"):
        raise ValueError("unknown split")
    from .comparisons import comparison_spec
    comparison_spec(data, split)
    checkpoints_checked(data["checkpoints_seconds"])
    seeds = data["seeds"]
    if not seeds or any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be nonempty unique integers")
    identifiers, groups, hashes, instances = set(), {}, {}, []
    for record in data["datasets"]:
        identifier, group, partition = record["id"], record["source_graph"], record["split"]
        if (not isinstance(identifier, str) or not identifier or identifier in identifiers
                or not isinstance(group, str) or not group):
            raise ValueError("dataset IDs must be unique; source_graph must be nonempty")
        identifiers.add(identifier)
        if partition not in ("development", "validation", "test"):
            raise ValueError("invalid dataset split")
        expected = record["sha256"]
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("dataset sha256 must be a lowercase SHA-256 digest")
        for key, mapping in ((group, groups), (expected, hashes)):
            if key in mapping and mapping[key] != partition:
                raise ValueError("source graph or identical file crosses split boundaries")
            mapping[key] = partition
        if partition != split:
            continue  # Do not load held-out bytes during development evaluation.
        source = (path.parent / record["path"]).resolve()
        if file_sha256(source) != expected:
            raise ValueError(f"dataset hash mismatch for {identifier}")
        instance = Instance.load(source)
        budgets = record["budgets"]
        if not budgets or len(set(budgets)) != len(budgets):
            raise ValueError("budgets must be nonempty and unique")
        for k in budgets:
            instance.validate_budget(k)
        instances.append((record, instance))
    if not instances:
        raise ValueError(f"no source networks assigned to {split}")
    return data, instances

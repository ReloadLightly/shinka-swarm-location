"""Reproducible node anonymization with explicit, ID-invariant centroid semantics."""
from dataclasses import replace
import random


def relabel(instance, seed):
    if type(seed) is not int:
        raise ValueError("integer relabel seed required")
    labels = list(range(len(instance.nodes)))
    random.Random(seed).shuffle(labels)
    forward = dict(zip(instance.nodes, labels))
    changed = replace(instance, name="anonymized-network", nodes=tuple(sorted(labels)),
        edges=tuple((forward[u], forward[v], w) for u, v, w in instance.edges),
        od=tuple((forward[s], forward[t], q) for s, t, q in instance.od),
        first_thru_node=None, non_thru_nodes=tuple(sorted(forward[v] for v in instance.non_transit)))
    return changed, forward

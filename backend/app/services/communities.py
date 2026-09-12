"""Phase 5 — community detection (deterministic Louvain).

Louvain modularity optimization implemented directly (no new dependency):
local greedy moves in fixed node order, then aggregation, repeated until
no improvement or the pass cap. Fully deterministic: same graph always
yields the same partition. Output labels are contiguous ints relabeled by
minimum member id, but remain run-scoped identifiers.

Communities describe graph structure — dense connectivity — and must never
be presented as confirmed criminal organizations.
"""

from __future__ import annotations


def louvain(adjacency: dict[str, set[str]], resolution: float = 1.0,
            max_passes: int = 10) -> dict[str, int]:
    """Partition nodes into communities. Returns {node_id: community_idx}."""
    nodes = sorted(adjacency)
    if not nodes:
        return {}
    if len(nodes) == 1:
        return {nodes[0]: 0}
    # Undirected edge weights (each pair counted once).
    weight: dict[tuple[str, str], float] = {}
    total = 0.0
    for node in nodes:
        for neighbor in adjacency[node]:
            if node < neighbor:
                weight[(node, neighbor)] = \
                    weight.get((node, neighbor), 0.0) + 1.0
                total += 1.0
    if total == 0.0:  # edgeless: every isolate is its own community
        return {node: i for i, node in enumerate(nodes)}

    community = {node: i for i, node in enumerate(nodes)}
    strength = {node: sum(weight.get(tuple(sorted((node, nb))), 0.0)
                           for nb in adjacency[node]) for node in nodes}

    def community_strength(cid: int, exclude: str | None = None) -> float:
        return sum(strength[n] for n in nodes
                   if community[n] == cid and n != exclude)

    improved = True
    passes = 0
    while improved and passes < max_passes:
        improved = False
        passes += 1
        for node in nodes:
            current = community[node]
            # Remove node, then evaluate each neighboring community.
            community[node] = -1
            candidates = {community[nb] for nb in adjacency[node]
                          if community[nb] != -1}
            candidates.add(current)
            best_gain, best_cid = 0.0, current
            links_total = sum(weight.get(tuple(sorted((node, nb))), 0.0)
                              for nb in adjacency[node])
            for cid in sorted(candidates):
                if cid == -1:
                    continue
                links_in = sum(weight.get(tuple(sorted((node, nb))), 0.0)
                               for nb in adjacency[node]
                               if community[nb] == cid)
                comm_str = community_strength(cid)
                gain = (links_in - resolution * comm_str * links_total /
                        (2.0 * total)) / (2.0 * total)
                if gain > best_gain + 1e-12:
                    best_gain, best_cid = gain, cid
            community[node] = best_cid
            if best_cid != current:
                improved = True

    # Relabel to contiguous ids ordered by minimum member (deterministic).
    groups: dict[int, list[str]] = {}
    for node, cid in community.items():
        groups.setdefault(cid, []).append(node)
    ordered = sorted(groups.values(), key=min)
    return {node: i for i, members in enumerate(ordered) for node in members}


def community_sizes(partition: dict[str, int]) -> dict[int, int]:
    """Member count per community id."""
    sizes: dict[int, int] = {}
    for cid in partition.values():
        sizes[cid] = sizes.get(cid, 0) + 1
    return sizes

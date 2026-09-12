"""Phase 5 — centrality analytics over the investigation graph.

Scope decision (documented): all measures treat edges as UNDIRECTED. The
graph stores directed evidence (CALLED, TRANSFERRED_TO, ...), but triage
centrality asks "how connected / how bridging is this entity", for which
direction adds noise at demo scale. Direction is preserved in storage and
queries; only the analytics projection is undirected.

Signals, not verdicts: high degree means connectivity, high PageRank means
structural importance, high betweenness means a bridge position. None of
these imply criminality.

Pure stdlib, deterministic (fixed iteration order, no RNG), bounded
runtime suitable for demo-scale graphs. No distributed infrastructure.
"""

from __future__ import annotations

import math

DAMPING = 0.85
MAX_ITER = 100
TOL = 1e-6


def sanitize_score(value: object) -> float:
    """Coerce to a finite float in [0, 1]. No NaN/Infinity ever escapes."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return max(0.0, min(1.0, number))


def build_adjacency(node_ids: list[str],
                    edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Undirected adjacency. Isolates are kept (degree 0, valid members)."""
    adjacency: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for src, dst in edges:
        if src not in adjacency or dst not in adjacency or src == dst:
            continue  # self-loops and unknown ids carry no centrality info
        adjacency[src].add(dst)
        adjacency[dst].add(src)
    return adjacency


def degree_centrality(adjacency: dict[str, set[str]]) -> dict[str, int]:
    """Raw undirected degree per entity: ``{"entity_id": degree}``."""
    return {nid: len(neighbors) for nid, neighbors in adjacency.items()}


def pagerank_raw(adjacency: dict[str, set[str]], damping: float = DAMPING,
                 max_iter: int = MAX_ITER, tol: float = TOL) -> dict[str, float]:
    """Classic power-iteration PageRank on the undirected projection.

    Returns shares summing to ~1 (structural importance distribution).
    Dangling nodes redistribute uniformly. Deterministic.
    """
    nodes = sorted(adjacency)
    count = len(nodes)
    if count == 0:
        return {}
    rank = {nid: 1.0 / count for nid in nodes}
    for _ in range(max_iter):
        dangling = sum(rank[nid] for nid in nodes if not adjacency[nid])
        updated = {}
        for nid in nodes:
            inflow = sum(rank[nb] / len(adjacency[nb])
                         for nb in adjacency[nid] if adjacency[nb])
            updated[nid] = ((1.0 - damping) / count
                            + damping * (inflow + dangling / count))
        shift = sum(abs(updated[nid] - rank[nid]) for nid in nodes)
        rank = updated
        if shift < tol:
            break
    total = sum(rank.values()) or 1.0
    return {nid: value / total for nid, value in rank.items()}


def betweenness_centrality(adjacency: dict[str, set[str]]) -> dict[str, float]:
    """Brandes' exact algorithm (unweighted, undirected), normalized to
    [0, 1] by the undirected maximum ((n-1)(n-2)/2). Graphs with <3 nodes
    score 0.0 everywhere (no bridge position can exist)."""
    nodes = sorted(adjacency)
    count = len(nodes)
    betweenness = {nid: 0.0 for nid in nodes}
    if count < 3:
        return betweenness
    for source in nodes:
        stack: list[str] = []
        pred: dict[str, list[str]] = {nid: [] for nid in nodes}
        sigma = dict.fromkeys(nodes, 0)
        sigma[source] = 1
        dist = dict.fromkeys(nodes, -1)
        dist[source] = 0
        queue = [source]
        while queue:
            current = queue.pop(0)
            stack.append(current)
            for neighbor in sorted(adjacency[current]):
                if dist[neighbor] < 0:
                    queue.append(neighbor)
                    dist[neighbor] = dist[current] + 1
                if dist[neighbor] == dist[current] + 1:
                    sigma[neighbor] += sigma[current]
                    pred[neighbor].append(current)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            current = stack.pop()
            for parent in pred[current]:
                if sigma[current]:
                    delta[parent] += (sigma[parent] / sigma[current]) * \
                        (1.0 + delta[current])
            if current != source:
                betweenness[current] += delta[current]
    for nid in nodes:
        betweenness[nid] /= 2.0  # undirected: each pair counted twice
    scale = ((count - 1) * (count - 2) / 2.0) or 1.0
    return {nid: sanitize_score(value / scale)
            for nid, value in betweenness.items()}


def minmax_norm(scores: dict[str, float]) -> dict[str, float]:
    """Rescale to [0, 1]. Degenerate input (empty / all equal) maps to 0.0 —
    with no differentiation there is no signal to report."""
    if not scores:
        return {}
    values = [sanitize_score(v) for v in scores.values()]
    floor, ceiling = min(values), max(values)
    if ceiling <= floor:
        return {nid: 0.0 for nid in scores}
    return {nid: sanitize_score((sanitize_score(v) - floor) / (ceiling - floor))
            for nid, v in scores.items()}


def ranked(scores: dict[str, float]) -> list[tuple[str, float]]:
    """Entities sorted by score descending (ties broken by id, stable)."""
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def analyze(adjacency: dict[str, set[str]]) -> dict[str, dict]:
    """Full centrality pass. Returns per entity::

        {"degree": int, "pagerank": [0,1] min-max, "betweenness": [0,1]}

    ``pagerank`` here is the min-max normalized share (storage/API form);
    use :func:`pagerank_raw` for the sum-to-1 distribution.
    """
    degrees = degree_centrality(adjacency)
    pagerank = minmax_norm(pagerank_raw(adjacency))
    betweenness = betweenness_centrality(adjacency)
    return {nid: {"degree": degrees.get(nid, 0),
                  "pagerank": pagerank.get(nid, 0.0),
                  "betweenness": betweenness.get(nid, 0.0)}
            for nid in adjacency}

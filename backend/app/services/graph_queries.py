"""Phase 4 — graph read/query service (NEO4J_SCHEMA.md §§19-20, 25).

All reads are parameterized; labels, relationship types, depth and limits
are validated server-side against allowlists/caps. Output is Cytoscape.js
compatible per API_SPEC.md §4. Works against any session with a
``run(cypher, params, timeout=...)`` method (real driver or test fake).
"""

from __future__ import annotations

from ..database.neo4j import QUERY_TIMEOUT_SECONDS
from .graph_builder import LABEL_ENTITY, REL_TYPES
from .validation import ID_RE, IngestionError

MAX_DEPTH = 3
DEFAULT_DEPTH = 1
DEFAULT_NODE_LIMIT, MAX_NODE_LIMIT = 100, 500
DEFAULT_EDGE_LIMIT, MAX_EDGE_LIMIT = 300, 1500

# Reverse map: API entity type -> Neo4j label.
TYPE_LABEL = {entity: label for label, entity in LABEL_ENTITY.items()}


def check_id(entity_id: str) -> str:
    if not isinstance(entity_id, str) or not ID_RE.match(entity_id):
        raise IngestionError("INVALID_ID", "Malformed entity id.",
                             http_status=400)
    return entity_id


def check_depth(depth: int) -> int:
    try:
        depth = int(depth)
    except (TypeError, ValueError) as exc:
        raise IngestionError("INVALID_DEPTH",
                             "depth must be an integer.",
                             http_status=422) from exc
    if not 1 <= depth <= MAX_DEPTH:
        raise IngestionError("INVALID_DEPTH",
                             f"depth must be between 1 and {MAX_DEPTH}.",
                             http_status=422)
    return depth


def check_types(values: list[str] | None, allowed: tuple[str, ...],
                field: str) -> list[str] | None:
    if values is None:
        return None
    cleaned = []
    for value in values:
        if value not in allowed:
            raise IngestionError("INVALID_FILTER",
                                 f"{field} '{value}' is not allowed.",
                                 http_status=422)
        cleaned.append(value)
    return cleaned or None


def clamp(limit: int, default: int, maximum: int, field: str) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise IngestionError("INVALID_LIMIT", f"{field} must be an integer.",
                             http_status=422) from exc
    if not limit:
        return default
    return max(1, min(limit, maximum))


def _node_to_cytoscape(identity: str, labels: list[str],
                       props: dict) -> dict:
    entity_type = LABEL_ENTITY.get(labels[0] if labels else "", "UNKNOWN")
    label = (props.get("name") or props.get("number") or
             props.get("registration_number") or
             props.get("account_number") or props.get("id", identity))
    node = {"id": props.get("id", identity), "label": label,
            "type": entity_type}
    meta = {k: v for k, v in props.items()
            if k not in ("id", "name") and v is not None}
    if meta:
        node["metadata"] = meta
    return node


def _as_node(raw) -> tuple[list[str], dict] | None:
    """Normalize a driver node (or fake dict) to (labels, props)."""
    if isinstance(raw, dict):
        labels = list(raw.get("_labels", []))
        props = {k: v for k, v in raw.items() if k != "_labels"}
        return (labels, props) if props.get("id") else None
    labels = list(raw.labels)
    props = dict(raw)
    return (labels, props) if props.get("id") else None


def _as_edge(raw) -> tuple[str, str, str, dict, str] | None:
    """Normalize a driver relationship (or fake dict)."""
    if isinstance(raw, dict):
        props = dict(raw.get("props", {}))
        return (raw.get("type", ""), raw.get("source", ""),
                raw.get("target", ""), props, raw.get("id", ""))
    props = dict(raw)
    edge_id = props.get("id", "")
    return (raw.type, raw.start_node["id"], raw.end_node["id"], props,
            edge_id)


def get_entity(session, entity_id: str) -> dict | None:
    """Fetch one node by canonical id."""
    check_id(entity_id)
    result = session.run("MATCH (n {id: $id}) RETURN n LIMIT 1",
                         {"id": entity_id},
                         timeout=QUERY_TIMEOUT_SECONDS)
    rows = list(result)
    if not rows:
        return None
    row = rows[0]
    raw = row["n"] if isinstance(row, dict) else row["n"]
    parsed = _as_node(raw)
    if parsed is None:
        return None
    labels, props = parsed
    return _node_to_cytoscape(entity_id, labels, props)


def search_entities(session, query: str, entity_type: str | None = None,
                    page: int = 1, page_size: int = 20) -> dict:
    """Substring search over display/identifier properties."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 128:
        raise IngestionError("INVALID_QUERY",
                             "q must be 1-128 characters.",
                             http_status=400)
    label = None
    if entity_type is not None:
        label = TYPE_LABEL.get(entity_type)
        if label is None:
            raise IngestionError("INVALID_FILTER",
                                 f"type '{entity_type}' is not allowed.",
                                 http_status=422)
    label_filter = "" if label is None else "AND $label IN labels(n)"
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError) as exc:
        raise IngestionError("INVALID_LIMIT", "page must be an integer.",
                             http_status=422) from exc
    page_size = clamp(page_size or 20, 20, 100, "page_size")
    result = session.run(
        "MATCH (n) WHERE (n.name CONTAINS $q OR n.normalized_name "
        "CONTAINS $q OR n.number CONTAINS $q OR n.registration_number "
        "CONTAINS $q OR n.account_number CONTAINS $q) "
        f"{label_filter} RETURN n SKIP $skip LIMIT $limit",
        {"q": query.strip(), "label": label,
         "skip": (page - 1) * page_size, "limit": page_size + 1},
        timeout=QUERY_TIMEOUT_SECONDS)
    items = []
    for row in result:
        raw = row["n"] if isinstance(row, dict) else row["n"]
        parsed = _as_node(raw)
        if parsed is None:
            continue
        labels, props = parsed
        items.append(_node_to_cytoscape(props.get("id", ""), labels, props))
        if len(items) >= page_size:
            break
    return {"items": items, "page": page, "page_size": page_size}


def get_neighborhood(session, entity_id: str, depth: int = DEFAULT_DEPTH,
                     rel_types: list[str] | None = None,
                     node_types: list[str] | None = None,
                     limit_nodes: int = DEFAULT_NODE_LIMIT,
                     limit_edges: int = DEFAULT_EDGE_LIMIT) -> dict:
    """Bounded traversal around one node, Cytoscape-shaped with truncation."""
    check_id(entity_id)
    depth = check_depth(depth)
    rel_types = check_types(rel_types, REL_TYPES, "rel_types")
    node_labels = None
    if node_types is not None:
        mapped = [TYPE_LABEL.get(t) for t in node_types]
        if any(label is None for label in mapped):
            raise IngestionError("INVALID_FILTER",
                                 "node_types contains an unknown type.",
                                 http_status=422)
        node_labels = check_types(mapped, tuple(LABEL_ENTITY), "node_types")
    limit_nodes = clamp(limit_nodes, DEFAULT_NODE_LIMIT, MAX_NODE_LIMIT,
                        "limit_nodes")
    limit_edges = clamp(limit_edges, DEFAULT_EDGE_LIMIT, MAX_EDGE_LIMIT,
                        "limit_edges")

    conditions = ["True"]
    if rel_types:
        conditions.append(
            "ALL(x IN relationships(p) WHERE type(x) IN $rel_types)")
    if node_labels:
        conditions.append(
            "ALL(m IN nodes(p)[1..] WHERE "
            "ANY(l IN labels(m) WHERE l IN $node_labels))")
    result = session.run(
        f"MATCH p = (n {{id: $id}})-[*1..{depth}]-(m) "
        f"WHERE {' AND '.join(conditions)} "
        "RETURN [n IN nodes(p) | n] AS ns, "
        "[r IN relationships(p) | {id: r.id, type: type(r), "
        "source: startNode(r).id, target: endNode(r).id, "
        "props: properties(r)}] AS rs "
        "LIMIT $row_limit",
        {"id": entity_id, "rel_types": rel_types or [],
         "node_labels": node_labels or [], "row_limit": limit_edges + 1},
        timeout=QUERY_TIMEOUT_SECONDS)

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for row in result:
        raw_ns = row["ns"] if isinstance(row, dict) else row["ns"]
        raw_rs = row["rs"] if isinstance(row, dict) else row["rs"]
        for raw in raw_ns:
            parsed = _as_node(raw)
            if parsed is None:
                continue
            labels, props = parsed
            node = _node_to_cytoscape(props.get("id", ""), labels, props)
            nodes[node["id"]] = node
        for raw in raw_rs:
            parsed = _as_edge(raw)
            if parsed is None:
                continue
            rtype, src, dst, props, eid = parsed
            edge = {"id": eid or f"{src}-{rtype}-{dst}", "source": src,
                    "target": dst, "type": rtype}
            meta = {}
            if props.get("confidence") is not None:
                meta["confidence"] = props["confidence"]
            if props.get("timestamp") is not None:
                meta["timestamp"] = props["timestamp"]
            source_record = props.get("source_record_id",
                                      props.get("source_id"))
            if source_record is not None:
                meta["source_record"] = source_record
            if meta:
                edge["metadata"] = meta
            edges[edge["id"]] = edge
        if len(nodes) > limit_nodes or len(edges) > limit_edges:
            break
    truncated = len(nodes) > limit_nodes or len(edges) > limit_edges
    return {"nodes": list(nodes.values())[:limit_nodes],
            "edges": list(edges.values())[:limit_edges],
            "truncated": truncated}


MAX_FETCH_NODES, MAX_FETCH_EDGES = 2000, 5000


def fetch_graph(session, node_limit: int = MAX_FETCH_NODES,
                edge_limit: int = MAX_FETCH_EDGES) -> dict:
    """Bounded full-graph snapshot for batch analytics (demo scale).

    Returns ``{"nodes": [cytoscape...], "edges": [...], "truncated": bool}``.
    Caps are hard: analytics never issues an unbounded query.
    """
    node_limit = clamp(node_limit, MAX_FETCH_NODES, MAX_FETCH_NODES,
                       "node_limit")
    edge_limit = clamp(edge_limit, MAX_FETCH_EDGES, MAX_FETCH_EDGES,
                       "edge_limit")
    node_rows = list(session.run(
        "MATCH (n) RETURN n LIMIT $limit", {"limit": node_limit + 1},
        timeout=QUERY_TIMEOUT_SECONDS))
    truncated = len(node_rows) > node_limit
    nodes = []
    for row in node_rows[:node_limit]:
        raw = row["n"] if isinstance(row, dict) else row["n"]
        parsed = _as_node(raw)
        if parsed is None:
            continue
        labels, props = parsed
        nodes.append(_node_to_cytoscape(props.get("id", ""), labels, props))
    edge_rows = list(session.run(
        "MATCH (a)-[r]->(b) RETURN {id: r.id, type: type(r), source: a.id, "
        "target: b.id, props: properties(r)} AS r LIMIT $limit",
        {"limit": edge_limit + 1},
        timeout=QUERY_TIMEOUT_SECONDS))
    if len(edge_rows) > edge_limit:
        truncated = True
    edges = []
    for row in edge_rows[:edge_limit]:
        raw = row["r"] if isinstance(row, dict) else row["r"]
        parsed = _as_edge(raw)
        if parsed is None:
            continue
        rtype, src, dst, props, eid = parsed
        edge = {"id": eid or f"{src}-{rtype}-{dst}", "source": src,
                "target": dst, "type": rtype}
        if props.get("timestamp") is not None:
            edge["metadata"] = {"timestamp": props["timestamp"]}
        edges.append(edge)
    return {"nodes": nodes, "edges": edges, "truncated": truncated}

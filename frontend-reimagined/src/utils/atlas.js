/** Pure helpers for the Atlas entity directory (unit-tested). */

export function mergeScores(entities, analyticsRows) {
  const byId = new Map((analyticsRows || []).map((row) => [row.entity_id, row]));
  return (entities || []).map((entity) => ({
    ...entity,
    scores: byId.get(entity.id) || null,
  }));
}

export function filterEntities(rows, query, typeFilter) {
  const q = (query || "").trim().toLowerCase();
  return rows.filter((row) => {
    if (typeFilter && row.type !== typeFilter) return false;
    if (!q) return true;
    const hay = `${row.name || ""} ${row.id || ""} ${(row.aliases || []).join(" ")}`.toLowerCase();
    return hay.includes(q);
  });
}

export function sortEntities(rows, sortKey) {
  const scored = (row) => {
    const s = row.scores || {};
    if (sortKey === "pagerank") return Number(s.pagerank ?? -1);
    if (sortKey === "name") return 0;
    return Number(s.priority_score ?? s.pagerank ?? -1);
  };
  const copy = [...rows];
  if (sortKey === "name") {
    copy.sort((a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id)));
  } else {
    copy.sort((a, b) => scored(b) - scored(a) || String(a.id).localeCompare(String(b.id)));
  }
  return copy;
}

export function paginateRows(rows, page, pageSize) {
  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  return { items: rows.slice(start, start + pageSize), total, totalPages, page: safePage };
}

export function countByType(rows) {
  const counts = {};
  for (const row of rows) {
    const t = row.type || "UNKNOWN";
    counts[t] = (counts[t] || 0) + 1;
  }
  return counts;
}

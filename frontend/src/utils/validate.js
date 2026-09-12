/** Pure frontend helpers (no DOM, no network) — unit-tested with vitest. */

export const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

export function isValidId(value) {
  return typeof value === "string" && ID_RE.test(value);
}

export function formatScore(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(2);
}

export function formatInt(value) {
  if (value === null || value === undefined) return "—";
  return String(value);
}

const SEVERITY_TONE = {
  HIGH: "bg-red-100 text-red-800 border-red-300",
  MEDIUM: "bg-amber-100 text-amber-800 border-amber-300",
  LOW: "bg-green-100 text-green-800 border-green-300",
};

export function severityTone(severity) {
  return SEVERITY_TONE[severity] || "bg-gray-100 text-gray-800 border-gray-300";
}

const TYPE_TONE = {
  PERSON: "#2563eb",
  PHONE: "#16a34a",
  LOCATION: "#d97706",
  VEHICLE: "#9333ea",
  ORGANIZATION: "#0d9488",
  ACCOUNT: "#db2777",
  DATE: "#64748b",
  FIR: "#4b5563",
};

export function typeColor(entityType) {
  return TYPE_TONE[entityType] || "#6b7280";
}

/** Convert API graph payload to Cytoscape elements (pure mapping). */
export function toCytoscapeElements(nodes, edges) {
  const elements = [];
  for (const node of nodes || []) {
    elements.push({
      data: {
        id: node.id,
        label: node.label || node.id,
        type: node.type || "UNKNOWN",
        color: typeColor(node.type),
      },
    });
  }
  for (const edge of edges || []) {
    elements.push({
      data: {
        id: edge.id || `${edge.source}-${edge.type}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        label: edge.type,
      },
    });
  }
  return elements;
}

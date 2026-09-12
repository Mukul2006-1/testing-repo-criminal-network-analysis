/** Deterministic plain-language investigation summary.
 *
 * Template-based only (no LLM, no guessing): every sentence is guarded by
 * the data it cites. Anything unknown is omitted, never invented.
 */

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function levelWord(score) {
  if (score >= 0.6) return "the highest review priority";
  if (score >= 0.35) return "an elevated review priority";
  return "a routine review priority";
}

export function buildNarrative(report) {
  if (!report || !report.entity) return "";
  const id = report.entity.id || "this entity";
  const name = report.entity.name && report.entity.name !== id
    ? `${report.entity.name} (${id})`
    : id;
  const priority = report.priority || {};
  const components = priority.components || {};
  const score = num(priority.score);
  const sentences = [
    `${name} has ${levelWord(score)} of ${score.toFixed(2)} out of 1.`,
  ];

  const parts = [
    ["network influence", num(components.pagerank)],
    ["bridge role", num(components.betweenness)],
    ["unusual-pattern flag", num(components.anomaly_score)],
  ].sort((a, b) => b[1] - a[1]);
  if (parts[0][1] > 0) {
    sentences.push(
      `The biggest contributor is ${parts[0][0]} (${parts[0][1].toFixed(2)}).`
    );
  }

  const anomaly = report.anomaly || {};
  const reasons = [...(anomaly.reasons || []), ...(report.explanations || [])]
    .filter((r) => r && r !== "No anomaly signal");
  const unique = [...new Set(reasons)].slice(0, 3);
  if (unique.length > 0) {
    sentences.push(`Notable signals: ${unique.join("; ")}.`);
  }

  const relCount = (report.key_relationships || []).length;
  const srcCount = (report.sources || []).length;
  const metrics = report.graph_metrics || {};
  const bits = [];
  if (relCount > 0) bits.push(`${relCount} key link${relCount === 1 ? "" : "s"}`);
  if (srcCount > 0) bits.push(`${srcCount} source record${srcCount === 1 ? "" : "s"}`);
  if (metrics.community_id !== null && metrics.community_id !== undefined) {
    bits.push(`close-knit group ${metrics.community_id}`);
  }
  if (bits.length > 0) {
    sentences.push(`On file: ${bits.join(", ")}.`);
  }

  sentences.push(
    "These are leads for investigator review, not findings of guilt."
  );
  return sentences.join(" ");
}

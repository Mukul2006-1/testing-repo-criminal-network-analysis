/** Deterministic plain-language investigation summary.
 *
 * Template-based only (no LLM, no guessing): every sentence is guarded by
 * the data it cites. Anything unknown is omitted, never invented.
 */

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function levelWord(score, lang) {
  if (lang === "hi") {
    if (score >= 0.6) return "सर्वोच्च समीक्षा प्राथमिकता";
    if (score >= 0.35) return "बढ़ी हुई समीक्षा प्राथमिकता";
    return "सामान्य समीक्षा प्राथमिकता";
  }
  if (score >= 0.6) return "the highest review priority";
  if (score >= 0.35) return "an elevated review priority";
  return "a routine review priority";
}

export function buildNarrative(report, lang = "en") {
  if (!report || !report.entity) return "";
  const hi = lang === "hi";
  const id = report.entity.id || "this entity";
  const name = report.entity.name && report.entity.name !== id
    ? (hi ? `${report.entity.name} (${id})` : `${report.entity.name} (${id})`)
    : id;
  const priority = report.priority || {};
  const components = priority.components || {};
  const score = num(priority.score);
  const sentences = hi
    ? [`${name} को 1 में से ${score.toFixed(2)} के साथ ${levelWord(score, lang)} मिली है।`]
    : [`${name} has ${levelWord(score, lang)} of ${score.toFixed(2)} out of 1.`];

  const labels = hi
    ? ["नेटवर्क प्रभाव", "सेतु भूमिका", "असामान्य पैटर्न चेतावनी"]
    : ["network influence", "bridge role", "unusual-pattern flag"];
  const parts = [
    [labels[0], num(components.pagerank)],
    [labels[1], num(components.betweenness)],
    [labels[2], num(components.anomaly_score)],
  ].sort((a, b) => b[1] - a[1]);
  if (parts[0][1] > 0) {
    sentences.push(hi
      ? `सबसे बड़ा योगदान ${parts[0][0]} (${parts[0][1].toFixed(2)}) का है।`
      : `The biggest contributor is ${parts[0][0]} (${parts[0][1].toFixed(2)}).`
    );
  }

  const anomaly = report.anomaly || {};
  const reasons = [...(anomaly.reasons || []), ...(report.explanations || [])]
    .filter((r) => r && r !== "No anomaly signal");
  const unique = [...new Set(reasons)].slice(0, 3);
  if (unique.length > 0) {
    sentences.push(hi
      ? `मुख्य संकेत: ${unique.join("; ")}।`
      : `Notable signals: ${unique.join("; ")}.`);
  }

  const relCount = (report.key_relationships || []).length;
  const srcCount = (report.sources || []).length;
  const metrics = report.graph_metrics || {};
  const bits = [];
  if (relCount > 0) bits.push(hi ? `${relCount} मुख्य कड़ी` : `${relCount} key link${relCount === 1 ? "" : "s"}`);
  if (srcCount > 0) bits.push(hi ? `${srcCount} स्रोत रिकॉर्ड` : `${srcCount} source record${srcCount === 1 ? "" : "s"}`);
  if (metrics.community_id !== null && metrics.community_id !== undefined) {
    bits.push(hi ? `घनिष्ठ समूह ${metrics.community_id}` : `close-knit group ${metrics.community_id}`);
  }
  if (bits.length > 0) {
    sentences.push(hi ? `फ़ाइल पर: ${bits.join(", ")}।` : `On file: ${bits.join(", ")}.`);
  }

  sentences.push(hi
    ? "ये जांचकर्ता समीक्षा के लिए संकेत हैं, दोष के निष्कर्ष नहीं।"
    : "These are leads for investigator review, not findings of guilt."
  );
  return sentences.join(" ");
}

import { describe, expect, it } from "vitest";
import { buildNarrative } from "./narrative.js";

const BASE = {
  entity: { id: "person_007", name: "Rohit Sharma", type: "PERSON" },
  priority: {
    score: 0.72,
    components: { pagerank: 0.8, betweenness: 0.7, anomaly_score: 0.65 },
  },
  anomaly: { severity: "HIGH", reasons: ["Night calls 6x baseline"] },
  explanations: ["Acts as a bridge between network groups"],
  graph_metrics: { community_id: 3 },
  key_relationships: [{}, {}],
  sources: [{}, {}, {}],
};

describe("buildNarrative", () => {
  it("names the entity as Name (id) with score and top contributor", () => {
    const text = buildNarrative(BASE);
    expect(text).toContain("Rohit Sharma (person_007)");
    expect(text).toContain("0.72");
    expect(text).toContain("network influence");
    expect(text).toContain("highest review priority");
  });

  it("includes signals, counts and the disclaimer", () => {
    const text = buildNarrative(BASE);
    expect(text).toContain("Night calls 6x baseline");
    expect(text).toContain("2 key links");
    expect(text).toContain("3 source records");
    expect(text).toContain("not findings of guilt");
  });

  it("never invents missing data", () => {
    const text = buildNarrative({ entity: { id: "person_009" }, priority: {} });
    expect(text).toContain("person_009");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("NaN");
  });

  it("returns empty for a missing entity", () => {
    expect(buildNarrative(null)).toBe("");
    expect(buildNarrative({})).toBe("");
  });

  it("renders a Hindi summary with the same guards", () => {
    const text = buildNarrative(BASE, "hi");
    expect(text).toContain("Rohit Sharma (person_007)");
    expect(text).toContain("0.72");
    expect(text).toContain("नेटवर्क प्रभाव");
    expect(text).toContain("दोष के निष्कर्ष नहीं");
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("NaN");
  });
});

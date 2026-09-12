import { describe, expect, it } from "vitest";
import {
  formatInt,
  formatPct,
  formatScore,
  isValidId,
  severityTone,
  toCytoscapeElements,
  typeColor,
} from "./validate.js";

describe("validate helpers (ARGUS frontend)", () => {
  it("validates entity ids", () => {
    expect(isValidId("person_001")).toBe(true);
    expect(isValidId("abc-123_X")).toBe(true);
    expect(isValidId("")).toBe(false);
    expect(isValidId("has space")).toBe(false);
    expect(isValidId(null)).toBe(false);
  });

  it("formats scores and ints", () => {
    expect(formatScore(0.8512)).toBe("0.85");
    expect(formatScore(null)).toBe("—");
    expect(formatScore(undefined)).toBe("—");
    expect(formatInt(42)).toBe("42");
    expect(formatInt(null)).toBe("—");
    expect(formatPct(0.35)).toBe("35%");
    expect(formatPct(null)).toBe("—");
  });

  it("maps severity tones including CRITICAL", () => {
    expect(severityTone("CRITICAL")).toContain("red");
    expect(severityTone("HIGH")).toContain("red");
    expect(severityTone("MEDIUM")).toContain("amber");
    expect(severityTone("LOW")).toContain("green");
    expect(severityTone("UNKNOWN")).toContain("gray");
  });

  it("maps entity type colors with PERSON as indigo", () => {
    expect(typeColor("PERSON")).toBe("#4f46e5");
    expect(typeColor("NOPE")).toBe("#6b7280");
  });

  it("converts graph payloads to cytoscape elements", () => {
    const elements = toCytoscapeElements(
      [{ id: "person_001", label: "P1", type: "PERSON" }],
      [{ source: "person_001", target: "phone_1", type: "USED" }]
    );
    expect(elements).toHaveLength(2);
    expect(elements[0].data.color).toBe("#4f46e5");
    expect(elements[1].data.id).toBe("person_001-USED-phone_1");
  });
});

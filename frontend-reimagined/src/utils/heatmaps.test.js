import { describe, expect, it } from "vitest";
import {
  FEATURE_KEYS,
  normalizeFeatureColumns,
  weeklyActivityGrid,
} from "./heatmaps.js";

describe("heatmap helpers", () => {
  it("max-normalizes feature columns", () => {
    const rows = normalizeFeatureColumns([
      { entity_id: "a", features: { night_calls: 10, transaction_amount: 0 } },
      { entity_id: "b", features: { night_calls: 5, transaction_amount: 100 } },
    ]);
    expect(rows[0].cells.night_calls).toBe(1);
    expect(rows[1].cells.night_calls).toBe(0.5);
    expect(rows[0].cells.transaction_amount).toBe(0);
    expect(rows[1].cells.transaction_amount).toBe(1);
    expect(Object.keys(rows[0].cells)).toEqual(FEATURE_KEYS);
  });

  it("handles missing features without crashing", () => {
    const rows = normalizeFeatureColumns([{}, null]);
    expect(rows).toHaveLength(2);
    expect(rows[0].cells.night_calls).toBe(0);
  });

  it("bins timestamps into a 12x7 grid", () => {
    const today = new Date().toISOString();
    const { days, max } = weeklyActivityGrid([today, today, "not-a-date"]);
    expect(days).toHaveLength(84);
    expect(max).toBe(2);
    expect(days[days.length - 1].count).toBe(2);
  });

  it("handles empty input", () => {
    const { days, max } = weeklyActivityGrid([]);
    expect(days).toHaveLength(84);
    expect(max).toBe(0);
  });
});

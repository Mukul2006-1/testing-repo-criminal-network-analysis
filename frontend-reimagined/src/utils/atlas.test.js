import { describe, expect, it } from "vitest";
import {
  countByType,
  filterEntities,
  mergeScores,
  paginateRows,
  sortEntities,
} from "./atlas.js";

const ROWS = [
  { id: "person_001", name: "Asha", type: "PERSON", aliases: ["A."] },
  { id: "phone_002", name: null, type: "PHONE" },
  { id: "person_003", name: "Bala", type: "PERSON" },
];

describe("atlas helpers", () => {
  it("merges analytics rows by entity id", () => {
    const merged = mergeScores(ROWS, [{ entity_id: "person_001", pagerank: 0.9 }]);
    expect(merged[0].scores.pagerank).toBe(0.9);
    expect(merged[1].scores).toBeNull();
  });

  it("filters by query across name, id and aliases", () => {
    expect(filterEntities(ROWS, "asha", "").map((r) => r.id)).toEqual(["person_001"]);
    expect(filterEntities(ROWS, "A.", "").map((r) => r.id)).toEqual(["person_001"]);
    expect(filterEntities(ROWS, "", "PHONE").map((r) => r.id)).toEqual(["phone_002"]);
    expect(filterEntities(ROWS, "zzz", "")).toEqual([]);
  });

  it("sorts by score desc and name asc", () => {
    const merged = mergeScores(ROWS, [
      { entity_id: "person_003", pagerank: 0.5 },
      { entity_id: "person_001", pagerank: 0.9 },
    ]);
    expect(sortEntities(merged, "pagerank").map((r) => r.id)[0]).toBe("person_001");
    expect(sortEntities(merged, "name").map((r) => r.id)).toEqual([
      "person_001",
      "person_003",
      "phone_002",
    ]);
  });

  it("paginates and counts by type", () => {
    const page = paginateRows(ROWS, 2, 2);
    expect(page.items).toHaveLength(1);
    expect(page.total).toBe(3);
    expect(page.totalPages).toBe(2);
    expect(countByType(ROWS)).toEqual({ PERSON: 2, PHONE: 1 });
  });
});

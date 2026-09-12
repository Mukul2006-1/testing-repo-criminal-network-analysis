import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  ApiError,
  api,
  buildUrl,
  clearToken,
  getToken,
  parseError,
  setToken,
} from "./api.js";
import {
  formatScore,
  isValidId,
  severityTone,
  toCytoscapeElements,
  typeColor,
} from "../utils/validate.js";

function mockFetchOnce(status, body) {
  globalThis.fetch = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
}

beforeEach(() => {
  clearToken();
  vi.unstubAllGlobals();
});

describe("buildUrl", () => {
  it("joins path and filters empty params", () => {
    expect(buildUrl("/api/search", { q: "rahul", page: 1, empty: "" })).toContain("q=rahul");
    expect(buildUrl("/api/search", { q: "rahul", page: 1, empty: "" })).toContain("page=1");
    expect(buildUrl("/api/search", { q: "rahul", page: 1, empty: "" })).not.toContain("empty");
  });

  it("encodes special characters", () => {
    expect(buildUrl("/api/search", { q: "a&b" })).toContain("q=a%26b");
  });
});

describe("token handling", () => {
  it("starts empty and round-trips in memory", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("sends Authorization only when a token exists", async () => {
    mockFetchOnce(200, { success: true, data: { ok: true } });
    await api.me();
    expect(globalThis.fetch.mock.calls[0][1].headers.Authorization).toBeUndefined();
    setToken("tok123");
    await api.me();
    expect(globalThis.fetch.mock.calls[1][1].headers.Authorization).toBe("Bearer tok123");
  });
});

describe("parseError", () => {
  it("maps envelope errors", () => {
    const error = parseError(403, { error: { code: "FORBIDDEN", message: "No." } });
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(403);
    expect(error.code).toBe("FORBIDDEN");
  });

  it("handles missing envelopes", () => {
    const error = parseError(500, null);
    expect(error.code).toBe("REQUEST_FAILED");
  });
});

describe("api calls", () => {
  it("login posts credentials without auth header", async () => {
    mockFetchOnce(200, { success: true, data: { access_token: "t" } });
    const data = await api.login("a@b.c", "secret123");
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toContain("/api/auth/login");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ username: "a@b.c", password: "secret123" });
    expect(options.headers.Authorization).toBeUndefined();
    expect(data.access_token).toBe("t");
  });

  it("throws ApiError on HTTP errors", async () => {
    mockFetchOnce(404, { success: false, error: { code: "NOT_FOUND", message: "Gone." } });
    await expect(api.entity("ghost")).rejects.toMatchObject({ status: 404, code: "NOT_FOUND" });
  });

  it("throws NETWORK_ERROR when fetch rejects", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("down");
    });
    await expect(api.me()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("search builds query params", async () => {
    mockFetchOnce(200, { success: true, data: { items: [] } });
    await api.search("rahul", { page: 2 });
    const [url] = globalThis.fetch.mock.calls[0];
    expect(url).toContain("q=rahul");
    expect(url).toContain("page=2");
  });
});

describe("validate utils", () => {
  it("validates entity IDs like the backend", () => {
    expect(isValidId("person_001")).toBe(true);
    expect(isValidId("../evil")).toBe(false);
    expect(isValidId("")).toBe(false);
    expect(isValidId("x".repeat(65))).toBe(false);
  });

  it("formats scores safely", () => {
    expect(formatScore(0.8295)).toBe("0.83");
    expect(formatScore(null)).toBe("—");
    expect(formatScore(undefined)).toBe("—");
  });

  it("maps severity tones", () => {
    expect(severityTone("HIGH")).toContain("red");
    expect(severityTone("BOGUS")).toContain("gray");
  });

  it("maps graph payloads to cytoscape elements", () => {
    const elements = toCytoscapeElements(
      [{ id: "p1", label: "Rahul", type: "PERSON" }],
      [{ id: "r1", source: "p1", target: "p2", type: "CALLED" }]
    );
    expect(elements).toHaveLength(2);
    expect(elements[0].data.color).toBe(typeColor("PERSON"));
    expect(elements[1].data.label).toBe("CALLED");
    expect(toCytoscapeElements([], [])).toEqual([]);
  });
});

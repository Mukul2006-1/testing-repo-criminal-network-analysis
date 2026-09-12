/** Centralized backend API client (fetch-based, no scattered calls).
 *
 * - Base URL from VITE_API_BASE_URL (default http://localhost:8000).
 * - Auth token lives in memory only (never localStorage), per API_SPEC §18.
 * - All responses use the backend envelope {success, data, error}.
 * - Network/JSON failures become ApiError; 401s trigger onUnauthorized.
 */

const BASE = (
  (import.meta.env && import.meta.env.VITE_API_BASE_URL) ||
  "http://localhost:8000"
).replace(/\/$/, "");

let token = null;
let unauthorizedHandler = null;

export function setToken(value) {
  token = value || null;
}

export function getToken() {
  return token;
}

export function clearToken() {
  token = null;
}

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

export function buildUrl(path, params) {
  const query = params
    ? Object.entries(params)
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join("&")
    : "";
  return `${BASE}${path}${query ? `?${query}` : ""}`;
}

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.code = code || "REQUEST_FAILED";
  }
}

export function parseError(status, body) {
  if (body && body.error) {
    return new ApiError(status, body.error.code, body.error.message);
  }
  return new ApiError(status, null, `Request failed (${status})`);
}

async function request(path, { method = "GET", body, form, params, auth = true } = {}) {
  const headers = {};
  let payload;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (auth && token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  let response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers,
      body: payload,
    });
  } catch (error) {
    throw new ApiError(0, "NETWORK_ERROR", `Network failure: ${error.message}`);
  }
  let parsed = null;
  try {
    parsed = await response.json();
  } catch {
    throw new ApiError(response.status, "BAD_RESPONSE", "Invalid JSON response.");
  }
  if (!response.ok) {
    if (response.status === 401 && unauthorizedHandler) {
      unauthorizedHandler();
    }
    throw parseError(response.status, parsed);
  }
  return parsed && parsed.data !== undefined ? parsed.data : parsed;
}

export const api = {
  // Auth (login is unauthenticated; everything else sends the token).
  login: (username, password) =>
    request("/api/auth/login", { method: "POST", body: { username, password }, auth: false }),
  refresh: (refreshToken) =>
    request("/api/auth/refresh", { method: "POST", body: { refresh_token: refreshToken }, auth: false }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request("/api/auth/me"),
  listUsers: () => request("/api/users"),
  createUser: (user) => request("/api/users", { method: "POST", body: user }),
  setUserRole: (id, role) =>
    request(`/api/users/${encodeURIComponent(id)}/role`, { method: "PATCH", body: { role } }),

  // Pipeline.
  upload: (file, datasetType, sourceName, description) => {
    const form = new FormData();
    form.append("file", file);
    form.append("dataset_type", datasetType);
    if (sourceName) form.append("source_name", sourceName);
    if (description) form.append("description", description);
    return request("/api/upload", { method: "POST", form });
  },
  process: (uploadId) => request("/api/process", { method: "POST", body: { upload_id: uploadId } }),
  job: (jobId) => request(`/api/process/${encodeURIComponent(jobId)}`),
  buildGraph: (uploadId) =>
    request("/api/graph/build", { method: "POST", body: { upload_id: uploadId } }),
  runAnalytics: (uploadId) =>
    request("/api/analytics/run", {
      method: "POST",
      body: uploadId ? { upload_id: uploadId } : {},
    }),

  // Reads.
  entities: (params) => request("/api/entities", { params }),
  entity: (id) => request(`/api/entities/${encodeURIComponent(id)}`),
  graph: (id, params) => request(`/api/graph/${encodeURIComponent(id)}`, { params }),
  neighbors: (id, params) =>
    request(`/api/graph/${encodeURIComponent(id)}/neighbors`, { params }),
  pagerank: (params) => request("/api/analytics/pagerank", { params }),
  betweenness: (params) => request("/api/analytics/betweenness", { params }),
  communities: (params) => request("/api/analytics/communities", { params }),
  degree: (params) => request("/api/analytics/degree", { params }),
  anomalies: (params) => request("/api/anomalies", { params }),
  investigation: (id) => request(`/api/investigation/${encodeURIComponent(id)}`),
  timeline: (id, params) => request(`/api/timeline/${encodeURIComponent(id)}`, { params }),
  search: (query, params) => request("/api/search", { params: { q: query, ...(params || {}) } }),
  extract: (payload) => request("/api/entities/extract", { method: "POST", body: payload }),
  resolve: (payload) => request("/api/entities/resolve", { method: "POST", body: payload }),
};

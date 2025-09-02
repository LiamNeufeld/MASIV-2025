// Centralized API base. Safe use of ?? with || (parenthesized).
const RAW_BASE = (import.meta?.env?.VITE_API_BASE ?? "");
// If you want a hard fallback path during dev, change "" to "/api".
const API_BASE = (RAW_BASE || "").replace(/\/$/, "");

// ---- small helpers ----
async function _json(res) {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { _raw: t }; }
}
async function _get(url) {
  const res = await fetch(url);
  const data = await _json(res);
  if (!res.ok) throw new Error(data?.message || data?.error || `HTTP ${res.status}`);
  return data;
}
async function _post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  const data = await _json(res);
  if (!res.ok) throw new Error(data?.message || data?.error || `HTTP ${res.status}`);
  return data;
}

// ---- public API surface ----
export function ping() {
  return _get(`${API_BASE}/api/health`);
}
export function getBuildings(bbox, limit = 1200) {
  const qs = new URLSearchParams({ bbox: bbox.join(","), limit: String(limit) }).toString();
  return _get(`${API_BASE}/api/buildings?${qs}`);
}
export function parseLLM(query, bbox, limit) {
  return _post(`${API_BASE}/api/llm_filter`, { query, bbox, limit });
}
export function applyFilters(filters, bbox, limit) {
  return _post(`${API_BASE}/api/filter_apply`, { filters, bbox, limit });
}

// Projects
export function listProjects(username) {
  const qs = new URLSearchParams({ username }).toString();
  return _get(`${API_BASE}/api/projects/list?${qs}`);
}
export function saveProjectApi(payload) {
  return _post(`${API_BASE}/api/projects/save`, payload);
}
export function loadProject(username, name) {
  const qs = new URLSearchParams({ username, name }).toString();
  return _get(`${API_BASE}/api/projects/load?${qs}`);
}

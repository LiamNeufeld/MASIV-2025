// frontend/src/api.js

// Prefer env var if set (good for local dev), otherwise fall back to Render
const BASE =
  (import.meta.env.VITE_API_BASE || "https://masiv-2025.onrender.com").replace(/\/$/, "");

function apiUrl(path) {
  return `${BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function handle(res) {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const text = await res.text();
      if (text) msg += ` – ${text}`;
    } catch {}
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

// --- public API used by the app ---

export async function ping() {
  const u = apiUrl("/api/health");
  const res = await fetch(u, { mode: "cors" });
  return handle(res);
}

export async function getBuildings(bbox, limit = 1200) {
  const qs = new URLSearchParams({
    bbox: bbox.join(","),
    limit: String(limit),
  });
  const u = apiUrl(`/api/buildings?${qs}`);
  const res = await fetch(u, { mode: "cors" });
  return handle(res);
}

export async function parseLLM(query, bbox, limit = 1200) {
  const u = apiUrl("/api/llm_filter");
  const res = await fetch(u, {
    method: "POST",
    mode: "cors",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, bbox, limit }),
  });
  return handle(res);
}

export async function applyFilters(filters, bbox, limit = 1200) {
  const u = apiUrl("/api/filter_apply");
  const res = await fetch(u, {
    method: "POST",
    mode: "cors",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filters, bbox, limit }),
  });
  return handle(res);
}

// ------- Projects -------
export async function listProjects(username) {
  const qs = new URLSearchParams({ username });
  const u = apiUrl(`/api/projects/list?${qs}`);
  const res = await fetch(u, { mode: "cors" });
  return handle(res);
}

export async function saveProjectApi({ username, name, query, filters, bbox, limit }) {
  const u = apiUrl("/api/projects/save");
  const res = await fetch(u, {
    method: "POST",
    mode: "cors",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, name, query, filters, bbox, limit }),
  });
  return handle(res);
}

export async function loadProject(username, name) {
  const qs = new URLSearchParams({ username, name });
  const u = apiUrl(`/api/projects/load?${qs}`);
  const res = await fetch(u, { mode: "cors" });
  return handle(res);
}

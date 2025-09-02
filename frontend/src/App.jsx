import React, { useState, Suspense, useEffect } from "react";
import { ping, getBuildings, parseLLM, applyFilters, listProjects, saveProjectApi, loadProject } from "./api.js";
const Scene3D = React.lazy(() => import("./three/Scene.jsx"));

function Banner({ type = "info", children }) {
  const styles = {
    info:  { bg:"#ecfeff", border:"#a5f3fc", color:"#155e75" },
    warn:  { bg:"#fff3cd", border:"#ffe69c", color:"#664d03" },
    error: { bg:"#fee2e2", border:"#fecaca", color:"#991b1b" },
  }[type];
  return (
    <div style={{ background: styles.bg, border: `1px solid ${styles.border}`, color: styles.color, padding: 10, borderRadius: 8, marginBottom: 12 }}>
      {children}
    </div>
  );
}

class Boundary extends React.Component {
  constructor(p) { super(p); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error("UI error:", err, info); }
  render() {
    if (this.state.err) return <Banner type="error"><b>UI error:</b> {String(this.state.err?.message || this.state.err)}</Banner>;
    return this.props.children;
  }
}

export default function App() {
  // core data
  const [bbox, setBbox] = useState("-114.074,51.045,-114.066,51.049");
  const [limit, setLimit] = useState(1200);
  const [features, setFeatures] = useState([]);
  const [highlightIds, setHighlightIds] = useState(new Set());
  const [onlyMatches, setOnlyMatches] = useState(false);
  const [query, setQuery] = useState("");
  const [lastFilters, setLastFilters] = useState([]); // store filters received from backend

  // projects
  const [username, setUsername] = useState("demo");
  const [projectName, setProjectName] = useState("");
  const [projectList, setProjectList] = useState([]);
  const [selectedProject, setSelectedProject] = useState("");

  // messages
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  // refresh project list whenever username changes
  useEffect(() => { refreshProjects(); }, [username]);

  async function refreshProjects() {
    if (!username) { setProjectList([]); return; }
    try {
      const r = await listProjects(username);
      setProjectList(r.projects || []);
    } catch (e) {
      console.warn("listProjects:", e);
    }
  }

  async function doPing() {
    setErr(""); setMsg("");
    try { const h = await ping(); setMsg(`Backend OK @ ${h.time}`); }
    catch (e) { setErr(String(e.message || e)); }
  }

  async function fetchBuildings() {
    setErr(""); setMsg(""); setHighlightIds(new Set());
    try {
      const bb = bbox.split(",").map(s => parseFloat(s.trim()));
      if (bb.length !== 4 || bb.some(Number.isNaN)) throw new Error("Invalid bbox (west,south,east,north)");
      const fc = await getBuildings(bb, limit);
      setFeatures(fc.features || []);
      setMsg(`Loaded ${fc.features?.length || 0} features`);
      if (!fc.features?.length) setErr("No parcels returned. Check backend data sources.");
    } catch (e) { setFeatures([]); setErr(String(e.message || e)); }
  }

  async function runLLM() {
    setErr(""); setMsg("");
    try {
      if (!query.trim()) return;
      const bb = bbox.split(",").map(s => parseFloat(s.trim()));
      if (bb.length !== 4 || bb.some(Number.isNaN)) throw new Error("Invalid bbox");
      const r = await parseLLM(query.trim(), bb, limit);
      setLastFilters(r.filters || []);
      const ids = new Set(r.ids || []);
      setHighlightIds(ids);

      if ((r.note === "NO_FILTERS_PARSED") || ids.size === 0) {
        setOnlyMatches(false);
        setErr("No matches parsed for this viewport. Try a different phrasing or zoom/pan to the area you want.");
      } else {
        setOnlyMatches(true);
        setMsg(`Matched ${ids.size} of ${r.total_considered ?? features.length} features`);
      }
    } catch (e) { setErr(String(e.message || e)); }
  }

  async function saveProject() {
    setErr(""); setMsg("");
    try {
      const bb = bbox.split(",").map(s => parseFloat(s.trim()));
      if (!username || !projectName) throw new Error("Enter username and project name");
      if (bb.length !== 4 || bb.some(Number.isNaN)) throw new Error("Invalid bbox");
      await saveProjectApi({
        username,
        name: projectName,
        query,
        filters: lastFilters, // save the structured filters we already computed
        bbox: bb,
        limit
      });
      setMsg(`Saved "${projectName}"`);
      setProjectName("");
      await refreshProjects();
    } catch (e) { setErr(String(e.message || e)); }
  }

  async function loadProjectByName() {
    setErr(""); setMsg("");
    try {
      if (!username || !selectedProject) throw new Error("Choose a project to load");
      const proj = await loadProject(username, selectedProject);
      if (proj.error) throw new Error("Project not found");
      // set bbox/limit/query in UI
      setBbox(proj.bbox.join(","));
      setLimit(proj.limit);
      setQuery(proj.query || "");
      setLastFilters(proj.filters || []);

      // fetch features for bbox, then apply filters
      const fc = await getBuildings(proj.bbox, proj.limit);
      setFeatures(fc.features || []);

      const r = await applyFilters(proj.filters || [], proj.bbox, proj.limit);
      const ids = new Set(r.ids || []);
      setHighlightIds(ids);
      setOnlyMatches(true);

      // ✅ FIX: parenthesize the nullish part before using ||
      const total = (r.total_considered ?? (fc.features?.length ?? 0));
      setMsg(`Loaded "${selectedProject}" · matched ${ids.size} of ${total}`);
    } catch (e) { setErr(String(e.message || e)); }
  }

  const shown = onlyMatches ? features.filter(f => highlightIds.has(f.properties?.id)) : features;

  return (
    <div style={{ height: "100vh", display: "grid", gridTemplateColumns: "360px 1fr" }}>
      {/* Left panel */}
      <div style={{ padding: "12px", borderRight: "1px solid #eee", overflow: "auto" }}>
        <h2 style={{ marginTop: 0 }}>MASIV City Dashboard</h2>

        {err && <Banner type="warn"><b>Error:</b> {err}</Banner>}
        {msg && <Banner>{msg}</Banner>}

        <button onClick={doPing} style={{ width: "100%", padding: "8px 10px" }}>Ping Backend</button>

        <label>Bounding Box (west,south,east,north)</label>
        <input value={bbox} onChange={e => setBbox(e.target.value)} style={{ width: "100%" }} />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button onClick={() => setBbox("-114.27,50.84,-113.86,51.22")}>Calgary (citywide)</button>
          <button onClick={() => setBbox("-114.074,51.045,-114.066,51.049")}>Downtown</button>
        </div>

        <label>Limit</label>
        <input type="number" value={limit} onChange={e => setLimit(parseInt(e.target.value || "0", 10))} style={{ width: "100%" }} />

        <button onClick={fetchBuildings} style={{ width: "100%", padding: "8px 10px", marginTop: 10 }}>Fetch</button>

        <hr />

        <label>Ask the map</label>
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder='e.g., "buildings in R-CG under $700k"'
          style={{ width: "100%" }} />
        <button onClick={runLLM} style={{ width: "100%", padding: "8px 10px", marginTop: 8 }}>Interpret</button>

        <label style={{ marginTop: 12 }}>
          <input type="checkbox" checked={onlyMatches} onChange={e => setOnlyMatches(e.target.checked)} /> Show only matches
        </label>
        <p style={{ fontSize: 12, color: "#666" }}>Loaded: {features.length} · Highlighted: {highlightIds.size}</p>

        <hr />

        <h3 style={{ marginTop: 10 }}>Projects</h3>

        <label>Username</label>
        <input value={username} onChange={e => setUsername(e.target.value)} style={{ width: "100%" }} />

        <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, marginTop: 8 }}>
          <input placeholder="Project name" value={projectName} onChange={e => setProjectName(e.target.value)} />
          <button onClick={saveProject}>Save</button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, marginTop: 8 }}>
          <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}>
            <option value="">— Select a saved project —</option>
            {projectList.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
          <button onClick={loadProjectByName}>Load</button>
        </div>

        <small style={{ color: "#666" }}>Saved items include: bbox, limit, query, and parsed filters. Loading fetches the bbox and applies the saved filters immediately.</small>
      </div>

      {/* 3D view */}
      <div style={{ position: "relative" }}>
        <Boundary>
          <Suspense fallback={<div style={{ padding: 12 }}>Loading 3D…</div>}>
            <Scene3D features={shown} highlightIds={highlightIds} />
          </Suspense>
        </Boundary>
      </div>
    </div>
  );
}

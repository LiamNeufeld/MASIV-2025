import React, { useState } from "react"

export default function Sidebar(props){
  const {username, setUsername, bbox, setBbox, reload, limit, setLimit, query, setQuery, runLLM, filters, setFilters, projects, onSave, onLoad, loading, error} = props
  const [projectName, setProjectName] = useState("")

  return (
    <div>
      <h2>Urban Design 3D City Dashboard</h2>
      <div><small className="mono">Calgary · parcels extruded as buildings</small></div>
      <hr/>
      <label>Username</label>
      <input value={username} onChange={e=>props.setUsername(e.target.value)} placeholder="your name" style={{width:"100%"}}/>
      <div style={{marginTop:8}}>
        <label>Bounding Box (west,south,east,north)</label>
        <input value={bbox.join(",")} onChange={e=>{
          const parts = e.target.value.split(",").map(s=>Number(s.trim()))
          if(parts.length===4 && parts.every(x=>!Number.isNaN(x))){
            setBbox(parts)
          }
        }} style={{width:"100%"}}/>
        <div className="controls">
          <button onClick={()=>{ setBbox([-114.27,50.84,-113.86,51.22]) }}>City of Calgary</button>
          <button onClick={reload} disabled={loading}>Fetch</button>
          <span>{loading ? "Loading…" : ""}</span>
        </div>
      </div>
      <div style={{marginTop:8}}>
        <label>Limit (features)</label>
        <input type="number" value={limit} onChange={e=>setLimit(Number(e.target.value)||0)} style={{width:"100%"}}/>
      </div>
      {error && <div style={{color:"#b91c1c"}}>{error}</div>}
      <hr/>
      <label>Ask the map (LLM query)</label>
      <input value={query} onChange={e=>setQuery(e.target.value)} placeholder='e.g., "show buildings in RC-G" or "over 100 feet"' style={{width:"100%"}}/>
      <div className="controls">
        <button onClick={runLLM}>Interpret Query</button>
        <span className="badge">{filters.length} filters</span>
      </div>
      <div>
        {filters.map((f,i)=>(<div key={i}><small className="mono">{JSON.stringify(f)}</small></div>))}
      </div>
      <hr/>
      <h3>Projects</h3>
      <div className="controls">
        <input value={projectName} onChange={e=>setProjectName(e.target.value)} placeholder="project name" style={{flex:1}}/>
        <button onClick={()=> onSave(projectName)} disabled={!projectName}>Save</button>
      </div>
      <div>
        {projects.map(p=>(
          <div className="project" key={p.id}>
            <span>{p.name}</span>
            <button onClick={()=>onLoad(p.id)}>Load</button>
          </div>
        ))}
      </div>
      <hr/>
      <div>
        <p><b>Tips</b></p>
        <ul>
          <li>Try queries like “show buildings in RC-G zoning”.</li>
          <li>“less than $500,000” filters by assessed value.</li>
          <li>“over 100 feet” converts to meters and filters by <code>height_m</code>.</li>
        </ul>
      </div>
    </div>
  )
}

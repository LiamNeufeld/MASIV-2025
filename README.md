# MASIV Urban Design 3D City Dashboard

Interactive 3D dashboard for Calgary parcels with zoning & assessment, natural-language querying, and project persistence.

---

## Features

- **3D map** of Calgary parcels (extruded footprints) with pan/orbit controls.
- **Parcel details** on hover/click: address, zoning, assessment, community, year, id.
- **Natural-language queries** (e.g., `buildings in R-CG under $700k`, `over 100 feet`, `built after 2005`).
- **Project persistence**: save/load filters + viewport by username (SQLite).
- **Deterministic parser** (no API key) **or** optional **free LLM** (Hugging Face).

---

## Repository layout
.
├─ backend/
│ ├─ app.py # Flask API (health, buildings, llm_filter, filter_apply, projects)
│ ├─ data_sources.py # ArcGIS/Socrata fetch + normalization
│ ├─ storage.py # SQLite (projects.db) save/list/load
│ └─ projects.db # created at first save
└─ frontend/
├─ src/
│ ├─ App.jsx # UI: bbox/limit, query, Save/Load, status banners
│ ├─ api.js # API helpers (safe base URL handling)
│ └─ three/Scene.jsx # Three.js scene (opaque buildings, anti-flicker)
├─ vite.config.js # dev proxy → backend
└─ index.html

## Setup

### Prereqs
- **Python** 3.10+
- **Node.js** 18+ (npm 9+)
- (Optional) **Hugging Face** account & API key (free)

> **Windows PowerShell tip (npm blocked):**  
> If `npm` errors with execution policy, use `npm.cmd` or run (elevated):  
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### 1) Backend (Flask)

From `backend/`:

```bash
# macOS/Linux
python -m venv .venv && source .venv/bin/activate
pip install flask flask-cors requests shapely

# Windows PowerShell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install flask flask-cors requests shapely
Configure data sources
Recommended (ArcGIS parcels include land-use designation):

# Windows PowerShell
$env:ARCGIS_PARCELS_URL = "https://services1.arcgis.com/AVP60cs0Q9PEA8rH/ArcGIS/rest/services/Parcel_with_Roll_2024/FeatureServer/0"
# Optional, if you have a Land Use layer:
# $env:ARCGIS_LANDUSE_URL = "<ArcGIS Land Use Districts FeatureServer layer URL>"

# macOS/Linux
export ARCGIS_PARCELS_URL="https://services1.arcgis.com/AVP60cs0Q9PEA8rH/ArcGIS/rest/services/Parcel_with_Roll_2024/FeatureServer/0"
# export ARCGIS_LANDUSE_URL="<ArcGIS Land Use Districts FeatureServer layer URL>"
Optional Socrata (helps with rate limits):

export SOCRATA_APP_TOKEN="<your_socrata_token>"
Run the backend:

python app.py
# → Flask on http://localhost:5001
Health & debug:

GET http://localhost:5001/api/health

GET http://localhost:5001/api/_debug/config

GET http://localhost:5001/api/_debug/arcgis?which=parcels&bbox=-114.074,51.045,-114.066,51.049&limit=5

2) Frontend (React + Vite)
From frontend/:

npm i
npm run dev
# → http://localhost:5173
The dev proxy (vite.config.js) forwards /api/* → http://localhost:5001.

🗺️ Using the app
Choose a bounding box (presets: Calgary (citywide), Downtown).

Click Fetch — parcels render as extruded buildings. Hover for details; click to select.

Enter a query and click Interpret — matches highlight in red.

Toggle Show only matches to isolate results.

Save your analysis (username + project name) and Load it later.

Query examples

buildings in R-CG

less than $500,000

between $350k and $1.2m

over 100 feet (also accepts meters or storeys)

built after 2005

in DC zoning under $700k

Zoning behavior: short codes like DC, MU, CR are prefix-matched (e.g., DC 131D2005), while complete codes such as R-CG require exact (normalized) match.

Project persistence
    Stored locally in SQLite at backend/projects.db.

    Each project saves: username, name, query, filters (structured), bbox, limit, updated_at.

    Persists across restarts on your machine.

    On load, the app refetches features for the saved bbox and re-applies saved filters.

    Optional: Free LLM integration (Hugging Face)
    Default is a deterministic parser (no API key). To also use a free LLM:

    Get a key at https://huggingface.co (free tier).

    Set before starting Flask:

        # macOS/Linux
        export HUGGINGFACE_API_KEY="hf_************************"
        powershell
        Copy code
        # Windows
        $env:HUGGINGFACE_API_KEY = "hf_************************"
        The backend will auto-switch to the HF path inside /api/llm_filter when the key is present; otherwise it uses the deterministic parser.

API Commands: 

GET /api/health
Health check.

GET /api/buildings?bbox=W,S,E,N&limit=N
Returns GeoJSON FeatureCollection with properties:
id, address, zoning, assessed_value, community, year, height_m, source.

POST /api/llm_filter
Request:

{ "query": "buildings in R-CG under $700k", "bbox": [-114.074,51.045,-114.066,51.049], "limit": 1200 }
Response:

{ "filters":[...], "ids":["..."], "matched": 93, "total_considered": 167 }
POST /api/filter_apply
Apply already-parsed filters (no text):

{ "filters":[...], "bbox":[...], "limit": 1200 }
Projects
POST /api/projects/save — body: { username, name, query, filters, bbox, limit }

GET /api/projects/list?username=demo

GET /api/projects/load?username=demo&name=MyProject

Deployment (free options)
Frontend — Vercel/Netlify
Build: npm run build
Output: dist
Set VITE_API_BASE if calling a remote backend (or keep relative /api and rely on proxy).
Backend — Render/Railway/Fly
Start: python app.py
Env vars: ARCGIS_PARCELS_URL, optional ARCGIS_LANDUSE_URL, SOCRATA_APP_TOKEN, optional HUGGINGFACE_API_KEY
CORS: tighten in app.py for production, e.g.
CORS(app, resources={r"/api/*": {"origins": "https://your-frontend.app"}})

Persistence: ensure a persistent volume for projects.db (or swap to Postgres).

Architecture

classDiagram
  class App[React App]
  class Scene3D[Three.js scene]
  class API[frontend/src/api.js]
  class Flask[Flask app.py]
  class DataSources[data_sources.py]
  class External[ArcGIS/Socrata APIs]
  class HF[Hugging Face API]
  class DB[(SQLite)]

  App --> API : fetch buildings / interpret / projects
  App --> Scene3D : features, highlightIds
  API --> Flask : /api/buildings, /api/llm_filter, /api/filter_apply
  Flask --> DataSources : fetch_parcels_with_attrs()
  DataSources --> External : HTTP (ArcGIS/Socrata)
  Flask --> HF : (optional) LLM parse
  Flask --> DB : save/list/load projects
LLM sequence (when HF enabled)

sequenceDiagram
  participant UI as Frontend UI
  participant BE as Flask (/api/llm_filter)
  participant HF as Hugging Face Inference API

  UI->>BE: POST {query, bbox, limit}
  BE->>HF: Prompt(query) → extract filters
  HF-->>BE: {"filters":[...]}
  BE->>BE: Fetch features for bbox; apply filters; collect ids
  BE-->>UI: {filters, ids, matched, total_considered}
  UI->>UI: highlight matches (optional: show only matches)
🧪 Quick local tests
PowerShell:

# Health
Invoke-WebRequest "http://localhost:5001/api/health" | Select-Object -ExpandProperty Content

# Buildings (downtown slice)
$bbox = "-114.074,51.045,-114.066,51.049"
Invoke-WebRequest "http://localhost:5001/api/buildings?bbox=$bbox&limit=200" | Select-Object -ExpandProperty Content

# Interpret
$body = @{ query = 'buildings in DC under $700k'; bbox = @(-114.074,51.045,-114.066,51.049); limit = 1200 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:5001/api/llm_filter" -Method Post -ContentType 'application/json' -Body $body
🧯 Troubleshooting
Frontend “Failed to fetch”
Backend not running or CORS/proxy misconfigured. In dev, Vite proxies /api/* → http://localhost:5001. Ensure both are running locally.

0 features returned
Check your bbox is inside Calgary. Verify ArcGIS URL via
/api/_debug/arcgis?which=parcels&bbox=...&limit=5 (count should be > 0).

Zoning shows “UNKNOWN”
Use the ArcGIS parcel layer including land-use fields (see ARCGIS_PARCELS_URL). Add ARCGIS_LANDUSE_URL if using a separate zoning layer.

LLM shows “NO_FILTERS_PARSED”
Rephrase the query (e.g., include zoning or in R-CG). Short codes like DC are allowed.

3D flicker
We use opaque meshes, polygon offset on ground, narrowed camera frustum, and a single RAF loop. If you still see shimmer, lower pixel ratio inside Scene.jsx (e.g., setPixelRatio(..., 1.25)).

Windows npm policy
Use npm.cmd or set execution policy (see tip above).

Spec compliance (high level)
Backend API (Flask) with health, data fetch, NL query, and persistence.

Frontend (React + Three.js) with 3D extrusions, pan/orbit, hover & click.

Public data (ArcGIS; Socrata optional).

NL querying via deterministic parser; optional free LLM (Hugging Face).

Project persistence via SQLite (save/load).

Documentation (this README), UML diagrams, and run/deploy instructions.
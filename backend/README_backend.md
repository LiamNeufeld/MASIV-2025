# Backend (Flask)

## What it does
- Fetches Calgary **parcels with assessed values** and joins **Land Use (zoning)** polygons inside a bounding box via the Open Calgary API.
- Derives a `height_m` for each polygon so **every feature is extrudable** in 3D (visual proxy).
- Parses natural-language filters using **Hugging Face Inference API** (or a rule-based fallback).
- Persists **Projects** (username, name, filters) in **SQLite**.

> Datasets used (Socrata IDs):  
> - **Current Year Property Assessments (Parcel)**: `4bsw-nn7w`  
> - **Land Use Districts**: `mw9j-jik5`

These are available from Open Calgary's portal (Socrata).

## Quickstart
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# (optional) cp .env.example .env and set HUGGINGFACE_API_KEY
export FLASK_APP=app.py
python app.py  # runs on http://localhost:5001
```

## API
- `GET /api/health`
- `GET /api/buildings?bbox=west,south,east,north&limit=800`
- `POST /api/llm_filter` body: `{"query":"show RC-G under $500k"}`
- `POST /api/projects` body: `{"username":"liam","name":"rcg under 500k","filters":[...]}`
- `GET /api/projects?username=liam`
- `GET /api/projects/<id>`

## Notes
- If Socrata field names change, `data_sources.py` tries several geometry field candidates.
- The 3D **height** is a computed visualization proxy (`height_m`) so every polygon has a consistent extrude height.
- If you have a true height dataset, you can map it to `height_m` instead.
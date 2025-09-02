# backend/app.py
import os
import re
import json
import traceback
from typing import List, Dict, Any, Tuple, Set

from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin

# Local modules
import data_sources as ds
import storage as st


# -----------------------------------------------------------------------------
# App & CORS (origin(s) configurable via env; support comma-separated list)
# -----------------------------------------------------------------------------
app = Flask(__name__)

_origins_env = os.environ.get("CORS_ORIGIN", "*")
if _origins_env == "*":
    _origins: Any = "*"
else:
    _origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

CORS(app, resources={r"/api/*": {"origins": "*"}})



# -----------------------------------------------------------------------------
# Small root route so Render's probe gets HTTP 200 on "/"
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return "OK", 200


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _parse_bbox(arg: str) -> Tuple[float, float, float, float]:
    try:
        west, south, east, north = [float(x.strip()) for x in arg.split(",")]
        return (west, south, east, north)
    except Exception:
        raise ValueError("bbox must be 'west,south,east,north' (comma-separated)")


def _norm_zone(z: str) -> str:
    if not z:
        return ""
    z = z.upper().replace(" ", "")
    z = z.replace("—", "-").replace("–", "-").replace("_", "-").replace("/", "-")
    return z


def _parse_money(txt: str):
    m = re.match(r"\$?\s*([0-9]+(?:[.,][0-9]{3})*(?:\.[0-9]+)?|[0-9]*\.?[0-9]+)\s*([kKmM]?)", txt.strip())
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    s = m.group(2).lower()
    if s == "k":
        n *= 1_000
    elif s == "m":
        n *= 1_000_000
    return n


def _parse_height_to_m(txt: str):
    m = re.match(r"([0-9]*\.?[0-9]+)\s*(m|meter|meters|metre|metres|ft|foot|feet)?", txt.strip(), re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "m").lower()
    return val * 0.3048 if unit in ("ft", "foot", "feet") else val


def _parse_int(txt: str):
    try:
        return int(re.sub(r"[^\d]", "", txt))
    except Exception:
        return None


def _feature_matches_filters(props: Dict[str, Any], filters: List[Dict[str, Any]]) -> bool:
    """Apply parsed filters to one feature's properties."""
    zoning = _norm_zone(props.get("zoning") or "")

    assessed_value = None
    try:
        assessed_value = float(props.get("assessed_value")) if props.get("assessed_value") is not None else None
    except Exception:
        pass

    height_m = None
    try:
        height_m = float(props.get("height_m")) if props.get("height_m") is not None else None
    except Exception:
        pass

    year = None
    try:
        year = int(props.get("year")) if props.get("year") is not None else None
    except Exception:
        pass

    community = (props.get("community") or "").strip().lower()

    for f in filters or []:
        attr = f.get("attribute")
        op = f.get("operator")
        val = f.get("value")

        if attr == "zoning":
            wanted = [str(v).strip().upper() for v in (val if isinstance(val, list) else [val])]
            ok = False
            for code in wanted:
                code_norm = _norm_zone(code)
                if not code_norm:
                    continue
                # Short tokens (<=3 letters) allow prefix match; else exact
                if len(code_norm) <= 3 and zoning.startswith(code_norm):
                    ok = True
                    break
                if zoning == code_norm:
                    ok = True
                    break
            if not ok:
                return False

        elif attr == "assessed_value":
            if assessed_value is None:
                return False
            try:
                v = float(val)
            except Exception:
                return False
            if op == "<" and not (assessed_value < v):
                return False
            if op == ">" and not (assessed_value > v):
                return False
            if op == "=" and not (assessed_value == v):
                return False

        elif attr == "height_m":
            if height_m is None:
                return False
            try:
                v = float(val)
            except Exception:
                return False
            if op == "<" and not (height_m < v):
                return False
            if op == ">" and not (height_m > v):
                return False
            if op == "=" and not (abs(height_m - v) < 1e-6):
                return False

        elif attr == "year":
            if year is None:
                return False
            try:
                v = int(val)
            except Exception:
                return False
            if op == "<" and not (year < v):
                return False
            if op == ">" and not (year > v):
                return False
            if op == "=" and not (year == v):
                return False

        elif attr == "community":
            target = (str(val) or "").strip().lower()
            if not target or community != target:
                return False

        # Unknown attributes: ignore gracefully
    return True


def _apply_filters(filters: List[Dict[str, Any]], features: List[Dict[str, Any]]) -> Tuple[Set[str], int]:
    ids: Set[str] = set()
    total = 0
    for f in features or []:
        props = (f or {}).get("properties") or {}
        fid = props.get("id")
        if fid is None:
            continue
        total += 1
        if _feature_matches_filters(props, filters):
            ids.add(fid)
    return ids, total


def _parse_text_to_filters(q: str) -> List[Dict[str, Any]]:
    """Deterministic parser (no external calls)."""
    filters: List[Dict[str, Any]] = []
    qq = (q or "").strip().lower()
    if not qq:
        return filters

    # Zoning
    zblock = None
    m = re.search(r"(?:zoning|zone|district)s?\s+([a-z0-9/\-, ]+)", qq)
    if m:
        zblock = m.group(1)
    if not zblock:
        m = re.search(r"\bin\s+([a-z0-9\-/ ,]+)", qq)
        if m and not re.search(r"\bcommunity|neighbou?rhood\b", qq):
            zblock = m.group(1)
    if zblock:
        codes = []
        for tok in re.split(r"[,\s/]+|(?:\bor\b)|(?:\band\b)", zblock):
            t = tok.strip().upper()
            if not t:
                continue
            if re.match(r"^[A-Z]{1,3}(?:-[A-Z0-9]{1,4})+$", t) or re.match(r"^[A-Z]{1,3}\d?$", t) or re.match(r"^[A-Z]{1,3}$", t):
                codes.append(t)
        if codes:
            filters.append({"attribute": "zoning", "operator": "in", "value": codes})

    # Assessed value
    m = re.search(r"(?:less than|under|below)\s+\$?\s*([0-9][\d,\.]*\s*[kKmM]?)", qq)
    if m:
        n = _parse_money(m.group(1))
        if n is not None:
            filters.append({"attribute": "assessed_value", "operator": "<", "value": n})

    m = re.search(r"(?:greater than|over|above)\s+\$?\s*([0-9][\d,\.]*\s*[kKmM]?)", qq)
    if m:
        n = _parse_money(m.group(1))
        if n is not None:
            filters.append({"attribute": "assessed_value", "operator": ">", "value": n})

    m = re.search(r"between\s+\$?\s*([0-9][\d,\.]*\s*[kKmM]?)\s+and\s+\$?\s*([0-9][\d,\.]*\s*[kKmM]?)", qq)
    if m:
        n1 = _parse_money(m.group(1))
        n2 = _parse_money(m.group(2))
        if n1 is not None and n2 is not None:
            lo, hi = sorted([n1, n2])
            filters.append({"attribute": "assessed_value", "operator": ">", "value": lo})
            filters.append({"attribute": "assessed_value", "operator": "<", "value": hi})

    # Height
    m = re.search(r"(?:over|greater than|above)\s+([0-9\.]+)\s*(ft|feet|foot|m|meter|metre|meters|metres)\b", qq)
    if m:
        h = _parse_height_to_m(m.group(1) + " " + m.group(2))
        if h is not None:
            filters.append({"attribute": "height_m", "operator": ">", "value": h})
    m = re.search(r"(?:under|less than|below)\s+([0-9\.]+)\s*(ft|feet|foot|m|meter|metre|meters|metres)\b", qq)
    if m:
        h = _parse_height_to_m(m.group(1) + " " + m.group(2))
        if h is not None:
            filters.append({"attribute": "height_m", "operator": "<", "value": h})
    m = re.search(r"(?:over|greater than|above)\s+([0-9]+)\s*(?:floors?|storeys?|stories?)", qq)
    if m:
        fl = _parse_int(m.group(1))
        if fl is not None:
            filters.append({"attribute": "height_m", "operator": ">", "value": fl * 3.0})
    m = re.search(r"(?:under|less than|below)\s+([0-9]+)\s*(?:floors?|storeys?|stories?)", qq)
    if m:
        fl = _parse_int(m.group(1))
        if fl is not None:
            filters.append({"attribute": "height_m", "operator": "<", "value": fl * 3.0})

    # Year
    m = re.search(r"(?:built|year)\s+(?:after|since)\s+([12][0-9]{3})", qq)
    if m:
        filters.append({"attribute": "year", "operator": ">", "value": int(m.group(1))})
    m = re.search(r"(?:built|year)\s+(?:before|until|prior to)\s+([12][0-9]{3})", qq)
    if m:
        filters.append({"attribute": "year", "operator": "<", "value": int(m.group(1))})

    # Community
    m = re.search(r"in\s+([a-z][a-z \-']+?)\s+(?:community|neighbou?rhood)\b", qq)
    if m:
        name = m.group(1).strip()
        if name:
            filters.append({"attribute": "community", "operator": "=", "value": name.title()})

    return filters


def _maybe_huggingface_parse(q: str) -> List[Dict[str, Any]]:
    """Optional: use a HF model to extract filters. Falls back to deterministic on failure."""
    key = os.environ.get("HUGGINGFACE_API_KEY")
    model = os.environ.get("HUGGINGFACE_MODEL")  # e.g. meta-llama/Llama-3.1-8B-Instruct
    if not key or not model:
        return _parse_text_to_filters(q)

    try:
        import requests
        prompt = (
            "Extract structured filters from the user query for parcel filtering. "
            "Return ONLY compact JSON: {\"filters\":[{\"attribute\":\"zoning|assessed_value|height_m|year|community\","
            "\"operator\":\"<|>|=|in\",\"value\":<number|string|array>}]}\n\n"
            f"Query: {q}\nJSON:"
        )
        resp = requests.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers={"Authorization": f"Bearer {key}"},
            json={"inputs": prompt, "options": {"wait_for_model": True}},
            timeout=22,
        )
        resp.raise_for_status()
        text = resp.json()
        if isinstance(text, list) and text and "generated_text" in text[0]:
            out = text[0]["generated_text"]
        else:
            out = json.dumps(text)
        jmatch = re.search(r"\{[\s\S]*\}", out)
        if not jmatch:
            return _parse_text_to_filters(q)
        data = json.loads(jmatch.group(0))
        flt = data.get("filters") if isinstance(data, dict) else None
        if isinstance(flt, list):
            return flt
        return _parse_text_to_filters(q)
    except Exception:
        return _parse_text_to_filters(q)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/api/health")
def health():
    from datetime import datetime, timezone
    return jsonify({"ok": True, "time": datetime.now(tz=timezone.utc).isoformat(), "db": st.get_db_path()})


@app.route("/api/buildings")
def buildings():
    """
    Returns a GeoJSON FeatureCollection of REAL parcels (with assessed_value)
    + zoning joined from Land Use (or parcel field). No synthetic fallbacks.
    """
    try:
        bbox = _parse_bbox(request.args.get("bbox", ""))
        limit = int(request.args.get("limit", "1200"))
        feats = ds.fetch_parcels_with_attrs(bbox, limit=limit)
        return jsonify({"type": "FeatureCollection", "features": feats})
    except Exception as e:
        app.logger.exception("buildings error")
        return jsonify({
            "error": "BUILDINGS_FETCH_FAILED",
            "message": str(e),
            "hint": "Check ARCGIS_PARCELS_URL/ARCGIS_LANDUSE_URL or Socrata env vars; use /api/_debug/* to verify."
        }), 500


@app.route("/api/llm_filter", methods=["POST", "OPTIONS"])
@cross_origin()  # answers CORS preflight in dev; global CORS handles in prod
def llm_filter():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("query") or "").strip()
    bbox = data.get("bbox")
    limit = int(data.get("limit") or 1200)

    if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return jsonify({"error": "BAD_REQUEST", "message": "bbox must be an array [w,s,e,n]"}), 400

    # 1) Parse filters (HF optional)
    filters = _maybe_huggingface_parse(q)

    # 2) Fetch features & apply filters to compute ids
    try:
        feats = ds.fetch_parcels_with_attrs(tuple(float(x) for x in bbox), limit=limit)
    except Exception as e:
        app.logger.exception("llm_filter fetch error")
        return jsonify({"error": "FETCH_FAILED", "message": str(e)}), 500

    ids, total = _apply_filters(filters, feats)
    return jsonify({
        "filters": filters,
        "ids": list(ids),
        "matched": len(ids),
        "total_considered": total,
        "note": "NO_FILTERS_PARSED" if not filters else None
    })


@app.route("/api/filter_apply", methods=["POST"])
def filter_apply():
    """Apply already-parsed filters (no text parsing)."""
    data = request.get_json(force=True, silent=True) or {}
    filters = data.get("filters") or []
    bbox = data.get("bbox")
    limit = int(data.get("limit") or 1200)

    if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return jsonify({"error": "BAD_REQUEST", "message": "bbox must be an array [w,s,e,n]"}), 400

    try:
        feats = ds.fetch_parcels_with_attrs(tuple(float(x) for x in bbox), limit=limit)
        ids, total = _apply_filters(filters, feats)
        return jsonify({"ids": list(ids), "matched": len(ids), "total_considered": total})
    except Exception as e:
        app.logger.exception("filter_apply error")
        return jsonify({"error": "FILTER_APPLY_FAILED", "message": str(e)}), 500


# ---------------- Projects (SQLite or Postgres via storage.py) ----------------
@app.route("/api/projects/save", methods=["POST"])
def projects_save():
    data = request.get_json(force=True, silent=True) or {}
    try:
        username = (data.get("username") or "").strip()
        name = (data.get("name") or "").strip()
        query = (data.get("query") or "").strip()
        filters = data.get("filters") or []
        bbox = data.get("bbox") or []
        limit = int(data.get("limit") or 1200)

        if not (username and name):
            return jsonify({"error": "BAD_REQUEST", "message": "username and name are required"}), 400
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            return jsonify({"error": "BAD_REQUEST", "message": "bbox must be [w,s,e,n]"}), 400

        st.save_project(username, name, query, filters, [float(x) for x in bbox], limit)
        return jsonify({"ok": True})
    except Exception as e:
        app.logger.exception("projects_save error")
        return jsonify({"error": "PROJECT_SAVE_FAILED", "message": str(e)}), 500


@app.route("/api/projects/list")
def projects_list():
    username = (request.args.get("username") or "").strip()
    try:
        projects = st.list_projects(username)
        return jsonify({"projects": projects})
    except Exception as e:
        app.logger.exception("projects_list error")
        return jsonify({"error": "PROJECT_LIST_FAILED", "message": str(e)}), 500


@app.route("/api/projects/load")
def projects_load():
    username = (request.args.get("username") or "").strip()
    name = (request.args.get("name") or "").strip()
    try:
        proj = st.load_project(username, name)
        if not proj:
            return jsonify({"error": "NOT_FOUND"}), 404
        return jsonify(proj)
    except Exception as e:
        app.logger.exception("projects_load error")
        return jsonify({"error": "PROJECT_LOAD_FAILED", "message": str(e)}), 500


# ---------------- Debug helpers ----------------
@app.route("/api/_debug/config")
def debug_config():
    return jsonify({
        "ARCGIS_PARCELS_URL": os.environ.get("ARCGIS_PARCELS_URL", ""),
        "ARCGIS_LANDUSE_URL": os.environ.get("ARCGIS_LANDUSE_URL", ""),
        "YYC_PARCELS_DATASET": os.environ.get("YYC_PARCELS_DATASET", "4bsw-nn7w"),
        "YYC_LANDUSE_DATASET": os.environ.get("YYC_LANDUSE_DATASET", "mw9j-jik5"),
        "SOCRATA_APP_TOKEN_set": bool(os.environ.get("SOCRATA_APP_TOKEN")),
        "HUGGINGFACE_MODEL": os.environ.get("HUGGINGFACE_MODEL", ""),
        "HUGGINGFACE_API_KEY_set": bool(os.environ.get("HUGGINGFACE_API_KEY")),
        "PROJECTS_DB_PATH": st.get_db_path(),
        "CORS_ORIGIN": os.environ.get("CORS_ORIGIN", "*"),
    })


@app.route("/api/_debug/arcgis")
def debug_arcgis():
    """which: parcels|landuse, bbox: west,south,east,north, limit: int"""
    which = (request.args.get("which") or "parcels").lower()
    bbox = request.args.get("bbox")
    limit = int(request.args.get("limit", "5"))
    if not bbox:
        return jsonify({"error": "bbox required"}), 400

    west, south, east, north = [float(x) for x in bbox.split(",")]
    url = os.environ.get("ARCGIS_PARCELS_URL") if which == "parcels" else os.environ.get("ARCGIS_LANDUSE_URL")
    if not url:
        return jsonify({"error": "URL not set", "which": which}), 400

    feats = ds._arcgis_query_public(url, (west, south, east, north), limit=limit)
    sample = feats[0] if feats else None
    keys = list((sample or {}).get("properties", {}).keys()) if sample else []
    return jsonify({"which": which, "count": len(feats), "sample_property_keys": keys[:30], "has_geometry": bool(sample and sample.get("geometry"))})


@app.route("/api/_debug/ping")
def debug_ping():
    return jsonify({"ok": True})


# -----------------------------------------------------------------------------
# Entrypoint (bind to Render's $PORT)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))  # Render assigns PORT; default 10000
    print(f"[boot] Starting Flask on 0.0.0.0:{port} (CORS_ORIGIN={_origins_env})")
    app.run(host="0.0.0.0", port=port, debug=True)

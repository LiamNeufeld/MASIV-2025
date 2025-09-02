import os, json, requests
from shapely.geometry import shape

# ---------------- Config ----------------
YYC_BASE = "https://data.calgary.ca/resource"
PARCELS_DATASET = os.environ.get("YYC_PARCELS_DATASET", "4bsw-nn7w")
LANDUSE_DATASET = os.environ.get("YYC_LANDUSE_DATASET", "mw9j-jik5")
SOCRATA_APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")

# Prefer ArcGIS feature layers if provided (recommended)
ARCGIS_PARCELS_URL = os.environ.get("ARCGIS_PARCELS_URL", "").strip()
ARCGIS_LANDUSE_URL = os.environ.get("ARCGIS_LANDUSE_URL", "").strip()

# Common geometry field guesses (Socrata)
GEOM_FIELDS = ["the_geom", "geom", "geometry", "shape"]

# ---------------- Socrata helpers ----------------
def _json_endpoint(d): return f"{YYC_BASE}/{d}.json"
def _geojson_endpoint(d): return f"{YYC_BASE}/{d}.geojson"

def _try_get(url, params, timeout=35):
    headers = {"X-App-Token": SOCRATA_APP_TOKEN} if SOCRATA_APP_TOKEN else {}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r

def _bbox_wkt_polygon(bbox):
    w,s,e,n = bbox
    return f"POLYGON (({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"

def _records_to_features(records):
    feats = []
    for rec in records or []:
        geom = None; gk = None
        for k, v in rec.items():
            if isinstance(v, dict) and "type" in v and "coordinates" in v:
                geom = v; gk = k; break
        if not geom: continue
        props = {k:v for k,v in rec.items() if k != gk}
        feats.append({"type":"Feature","geometry":geom,"properties":props})
    return feats

def _fetch_geo_features_socrata(dataset_id, bbox, limit=5000):
    poly = _bbox_wkt_polygon(bbox)

    # JSON + intersects (works for polygons)
    for gf in GEOM_FIELDS:
        try:
            p = {"$limit":limit, "$select":f"{gf}, *", "$where":f"intersects({gf}, to_polygon('{poly}'))"}
            rec = _try_get(_json_endpoint(dataset_id), p).json()
            feats = _records_to_features(rec)
            if feats: return feats
        except: pass

    # GeoJSON + intersects
    for gf in GEOM_FIELDS:
        try:
            p = {"$limit":limit, "$where":f"intersects({gf}, to_polygon('{poly}'))"}
            gj = _try_get(_geojson_endpoint(dataset_id), p).json()
            feats = gj.get("features", [])
            if feats: return feats
        except: pass

    return []

# ---------------- ArcGIS FeatureServer ----------------
def _arcgis_query(url, bbox, limit=2000):
    if not url: return []
    w,s,e,n = bbox
    base = url.rstrip("/") + "/query"
    env = {
        "geometry": json.dumps({"xmin":w,"ymin":s,"xmax":e,"ymax":n,"spatialReference":{"wkid":4326}}),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": 4326,
        "resultRecordCount": limit,
    }
    # Try GeoJSON first
    try:
        r = requests.get(base, params={**env, "f":"geojson"}, timeout=40); r.raise_for_status()
        feats = r.json().get("features", [])
        if feats: return feats
    except: pass
    # ESRIJSON → GeoJSON
    r = requests.get(base, params={**env, "f":"json"}, timeout=40); r.raise_for_status()
    data = r.json()
    feats = []
    for f in (data.get("features") or []):
        attrs = f.get("attributes") or {}
        geom = f.get("geometry") or {}
        rings = geom.get("rings")
        if not rings: continue
        rings2 = []
        for ring in rings:
            if ring and ring[0] != ring[-1]:
                ring = ring + [ring[0]]
            rings2.append(ring)
        feats.append({"type":"Feature","geometry":{"type":"Polygon","coordinates":rings2},"properties":attrs})
    return feats

# Expose for app debug route
# (app imports this symbol)
# noinspection PyUnusedLocal
def _arcgis_query_public(url, bbox, limit=2000):
    return _arcgis_query(url, bbox, limit)

# ---------------- Field helpers ----------------
def _pick_str(props, needles):
    low = {k.lower(): k for k in props.keys()}
    for n in needles:
        for kl, k in low.items():
            if n in kl and props.get(k) not in (None, ""):
                return k
    return None

def _pick_num(props, needles):
    k = _pick_str(props, needles)
    if not k: return None
    try:
        float(str(props.get(k)).replace(",","")); return k
    except: return None

# Common zoning keys (include Calgary's LAND_USE_DESIGNATION)
ZONING_KEYS_PARCEL = [
    "land_use_designation",  # Calgary parcel field
    "zoning","zone","zone_code","zoning_code",
    "land_use_district","land_use","landuse",
    "district","lu_district","lu_code","ludistrict","ludist"
]
ZONING_KEYS_LU = [
    "land_use_district","zoning","zone","zone_code","district","lu_district","lu_code","ludistrict","ludist","land_use","landuse"
]

# ---------------- Public main fetch ----------------
def fetch_parcels_with_attrs(bbox, limit=1200):
    """
    Returns features with properties:
      id, address, assessed_value, community, zoning, height_m, year, source
    """
    # Prefer ArcGIS
    parcels = _arcgis_query(ARCGIS_PARCELS_URL, bbox, limit) if ARCGIS_PARCELS_URL else \
              _fetch_geo_features_socrata(PARCELS_DATASET, bbox, limit)
    landuse = _arcgis_query(ARCGIS_LANDUSE_URL, bbox, 5000) if ARCGIS_LANDUSE_URL else \
              _fetch_geo_features_socrata(LANDUSE_DATASET, bbox, 5000)

    if not parcels:
        raise RuntimeError("No parcels returned. Confirm ARCGIS_PARCELS_URL or Socrata parcel view.")

    # Detect if parcel layer already carries zoning (e.g., LAND_USE_DESIGNATION)
    parcel_zoning_key = None
    for f in parcels:
        p = f.get("properties") or {}
        parcel_zoning_key = _pick_str(p, ZONING_KEYS_PARCEL)
        if parcel_zoning_key: break

    # Prepare land-use polygons (optional if parcel_zoning_key exists)
    lus = []
    for f in landuse or []:
        try:
            g = shape(f["geometry"])
            p = f.get("properties", {}) or {}
            k = _pick_str(p, ZONING_KEYS_LU)
            lu = str(p.get(k)).strip().upper() if k else "UNKNOWN"
            lus.append((g, lu))
        except: pass

    if (not parcel_zoning_key) and (not lus):
        # Neither parcel zoning nor land-use polygons → we can’t compute zoning
        # (still return parcels but zoning may be UNKNOWN)
        pass

    out = []
    for f in parcels:
        geom = f.get("geometry"); 
        if not geom: continue
        p = f.get("properties", {}) or {}

        # core attributes
        id_key   = _pick_str(p, ["roll_number","roll","account","parcel_id","property_id","objectid","id","unique_key","cpid"])
        addr_key = _pick_str(p, ["address_full","site_address","street_address","full_address","address","addr"])
        comm_key = _pick_str(p, ["community_name","comm_name","community","neighbourhood","neighborhood"])
        val_key  = _pick_num(p, ["total_assessed_value","assessed_value","assessed","assesed","assesed_value","total_value","re_assessed_value","nr_assessed_value","fl_assessed_value"])
        year_key = _pick_str(p, ["year_of_construction","year_built","build_year","constructed","construction_year","yr_built","year"])

        fid = p.get(id_key) if id_key else (p.get("objectid") or p.get("id") or "parcel")
        address = p.get(addr_key) if addr_key else "Unknown address"
        community = p.get(comm_key) if comm_key else "Unknown"
        try: assessed = float(str(p.get(val_key, 0)).replace(",","")) if val_key else 0.0
        except: assessed = 0.0
        try: year = int(str(p.get(year_key))) if year_key and str(p.get(year_key)).isdigit() else None
        except: year = None

        # zoning
        zoning = "UNKNOWN"
        if parcel_zoning_key:
            zoning = (str(p.get(parcel_zoning_key)) or "").strip().upper() or "UNKNOWN"
        if (zoning in (None,"","UNKNOWN")) and lus:
            try:
                c = shape(geom).centroid
                for g, lu in lus:
                    if g.covers(c):  # robust on edges
                        zoning = lu
                        break
            except: pass

        # Extrusion height heuristic
        try:
            minx,miny,maxx,maxy = shape(geom).bounds
            area = ((maxx-minx) or 1e-6)*((maxy-miny) or 1e-6)*(111320*111320)
        except: area = 1.0
        density = assessed/area if assessed else 0.0
        height = 6 + min(120, (density**0.25)*8)

        out.append({
            "type":"Feature",
            "geometry": geom,
            "properties":{
                "id": fid,
                "address": address,
                "assessed_value": round(assessed,2),
                "community": community,
                "zoning": zoning,
                "height_m": round(height,2),
                "year": year,
                "source": "arcgis" if ARCGIS_PARCELS_URL else "socrata"
            }
        })

    print(f"[buildings] bbox={bbox} -> parcels:{len(parcels)} landuse:{len(landuse or [])} out:{len(out)} zoning_key={parcel_zoning_key}")
    return out

import os
import sqlite3
import json
import time
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

# Configure where the SQLite DB lives.
# For hosting, set: PROJECTS_DB_PATH=/data/projects.db (and mount a disk at /data)
DB_PATH = os.environ.get("PROJECTS_DB_PATH") or os.path.join(os.path.dirname(__file__), "projects.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_schema():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                query TEXT,
                filters_json TEXT,
                bbox TEXT,
                limit INTEGER,
                updated_at REAL,
                UNIQUE(username, name)
            )
            """
        )
_ensure_schema()


def save_project(
    username: str,
    name: str,
    query: Optional[str],
    filters: Optional[List[Dict[str, Any]]],
    bbox: List[float],
    limit: int,
) -> None:
    """Create or update a saved project (UPSERT on username+name)."""
    if not username or not name:
        raise ValueError("username and name are required")

    filters_json = json.dumps(filters or [], ensure_ascii=False)
    bbox_str = ",".join(str(float(x)) for x in bbox)
    ts = time.time()

    with _conn() as c:
        c.execute(
            """
            INSERT INTO projects (username, name, query, filters_json, bbox, limit, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, name) DO UPDATE SET
              query=excluded.query,
              filters_json=excluded.filters_json,
              bbox=excluded.bbox,
              limit=excluded.limit,
              updated_at=excluded.updated_at
            """,
            (username, name, query or "", filters_json, bbox_str, int(limit), ts),
        )


def list_projects(username: str) -> List[Dict[str, Any]]:
    """Return [{name, updated_at}] for a user."""
    if not username:
        return []
    with _conn() as c:
        rows = c.execute(
            "SELECT name, updated_at FROM projects WHERE username=? ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
        return [{"name": r["name"], "updated_at": r["updated_at"]} for r in rows]


def load_project(username: str, name: str) -> Optional[Dict[str, Any]]:
    """Return the saved project payload or None."""
    if not username or not name:
        return None
    with _conn() as c:
        r = c.execute(
            "SELECT query, filters_json, bbox, limit FROM projects WHERE username=? AND name=?",
            (username, name),
        ).fetchone()
        if not r:
            return None
        try:
            filters = json.loads(r["filters_json"] or "[]")
        except Exception:
            filters = []
        try:
            bbox = [float(x.strip()) for x in (r["bbox"] or "").split(",")] if r["bbox"] else []
        except Exception:
            bbox = []
        return {
            "username": username,
            "name": name,
            "query": r["query"] or "",
            "filters": filters,
            "bbox": bbox,
            "limit": int(r["limit"] or 0),
        }


def get_db_path() -> str:
    return DB_PATH

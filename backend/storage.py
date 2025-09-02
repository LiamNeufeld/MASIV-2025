from contextlib import contextmanager
import os
import sqlite3
import json
import time
from typing import List, Dict, Any, Optional

# Prefer env var; on Render without disks, set PROJECTS_DB_PATH=/tmp/projects.db
_env_path = os.environ.get("PROJECTS_DB_PATH")
if _env_path:
    DB_PATH = _env_path
elif os.environ.get("RENDER"):
    DB_PATH = "/tmp/projects.db"
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "projects.db")

DB_DIR = os.path.dirname(DB_PATH) or "."
os.makedirs(DB_DIR, exist_ok=True)


@contextmanager
def _conn():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    except sqlite3.OperationalError as e:
        if "unable to open database file" in str(e):
            raise RuntimeError(
                f"SQLite could not open DB at '{DB_PATH}'. On Render use "
                f"PROJECTS_DB_PATH=/tmp/projects.db (ephemeral) or a mounted disk."
            ) from e
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
                limit_n INTEGER,
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
    if not username or not name:
        raise ValueError("username and name are required")

    filters_json = json.dumps(filters or [], ensure_ascii=False)
    bbox_str = ",".join(str(float(x)) for x in bbox)
    ts = time.time()

    with _conn() as c:
        c.execute(
            """
            INSERT INTO projects (username, name, query, filters_json, bbox, limit_n, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, name) DO UPDATE SET
              query=excluded.query,
              filters_json=excluded.filters_json,
              bbox=excluded.bbox,
              limit_n=excluded.limit_n,
              updated_at=excluded.updated_at
            """,
            (username, name, query or "", filters_json, bbox_str, int(limit), ts),
        )


def list_projects(username: str) -> List[Dict[str, Any]]:
    if not username:
        return []
    with _conn() as c:
        rows = c.execute(
            "SELECT name, updated_at FROM projects WHERE username=? ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
        return [{"name": r["name"], "updated_at": float(r["updated_at"] or 0)} for r in rows]


def load_project(username: str, name: str) -> Optional[Dict[str, Any]]:
    if not username or not name:
        return None
    with _conn() as c:
        r = c.execute(
            "SELECT query, filters_json, bbox, limit_n AS limit FROM projects WHERE username=? AND name=?",
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
            "limit": int(r["limit"] or 0),  # API still returns 'limit'
        }


def get_db_path() -> str:
    return DB_PATH

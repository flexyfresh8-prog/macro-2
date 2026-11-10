"""SQLite persistence for NTH: build history, move library, activity log."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS builds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    fruit       TEXT, fruit_conf   REAL,
    sword       TEXT, sword_conf   REAL,
    style       TEXT, style_conf   REAL,
    screenshot  TEXT,
    raw         TEXT
);
CREATE TABLE IF NOT EXISTS moves (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT,
    item        TEXT,
    ability     TEXT,
    key         TEXT,
    delay       REAL DEFAULT 0.3,
    mouse_path  TEXT,
    description TEXT,
    favorite    INTEGER DEFAULT 0,
    created     REAL
);
CREATE TABLE IF NOT EXISTS activity (
    id  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts  REAL NOT NULL,
    tag TEXT,
    msg TEXT
);
CREATE INDEX IF NOT EXISTS idx_builds_ts ON builds(ts DESC);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts DESC);
"""


class Database:
    """Thread-safe SQLite wrapper (single connection + lock)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(str(self.path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        with self._lock:
            self._con.executescript(SCHEMA)
            self._con.commit()

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._con.execute(sql, params)
            self._con.commit()
            return cur

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._con.execute(sql, params).fetchall()

    # -- build history -------------------------------------------------------
    def save_build(self, fruit: str, fruit_conf: float, sword: str, sword_conf: float,
                   style: str, style_conf: float, screenshot: str = "",
                   raw: Optional[Dict[str, Any]] = None) -> int:
        cur = self._exec(
            "INSERT INTO builds (ts, fruit, fruit_conf, sword, sword_conf, style, style_conf,"
            " screenshot, raw) VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), fruit, fruit_conf, sword, sword_conf, style, style_conf,
             screenshot, json.dumps(raw or {}, ensure_ascii=False)),
        )
        self.trim_builds(int(500))
        return int(cur.lastrowid or 0)

    def trim_builds(self, keep: int) -> None:
        self._exec(
            "DELETE FROM builds WHERE id NOT IN"
            " (SELECT id FROM builds ORDER BY ts DESC LIMIT ?)", (keep,)
        )

    def recent_builds(self, limit: int = 30) -> List[Dict[str, Any]]:
        rows = self._query("SELECT * FROM builds ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def clear_builds(self) -> None:
        self._exec("DELETE FROM builds")

    # -- move library ---------------------------------------------------------
    def add_move(self, name: str, category: str, item: str, ability: str, key: str,
                 delay: float, mouse_path: str = "", description: str = "") -> int:
        cur = self._exec(
            "INSERT INTO moves (name, category, item, ability, key, delay, mouse_path,"
            " description, favorite, created) VALUES (?,?,?,?,?,?,?,?,0,?)",
            (name, category, item, ability, key, delay, mouse_path, description, time.time()),
        )
        return int(cur.lastrowid or 0)

    def update_move(self, move_id: int, **fields: Any) -> None:
        allowed = {"name", "category", "item", "ability", "key", "delay", "mouse_path",
                   "description", "favorite"}
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return
        vals.append(move_id)
        self._exec(f"UPDATE moves SET {', '.join(sets)} WHERE id=?", tuple(vals))

    def delete_move(self, move_id: int) -> None:
        self._exec("DELETE FROM moves WHERE id=?", (move_id,))

    def list_moves(self, query: str = "", category: str = "", favorites_only: bool = False
                   ) -> List[Dict[str, Any]]:
        sql, vals = "SELECT * FROM moves WHERE 1=1", []
        if query:
            sql += " AND (name LIKE ? OR item LIKE ? OR description LIKE ?)"
            q = f"%{query}%"
            vals += [q, q, q]
        if category:
            sql += " AND category=?"
            vals.append(category)
        if favorites_only:
            sql += " AND favorite=1"
        sql += " ORDER BY favorite DESC, created DESC"
        return [dict(r) for r in self._query(sql, tuple(vals))]

    def get_move(self, move_id: int) -> Optional[Dict[str, Any]]:
        rows = self._query("SELECT * FROM moves WHERE id=?", (move_id,))
        return dict(rows[0]) if rows else None

    # -- activity log ----------------------------------------------------------
    def log(self, tag: str, msg: str) -> None:
        self._exec("INSERT INTO activity (ts, tag, msg) VALUES (?,?,?)", (time.time(), tag, msg))

    def recent_activity(self, limit: int = 60) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._query(
            "SELECT * FROM activity ORDER BY ts DESC LIMIT ?", (limit,))]

    def clear_activity(self) -> None:
        self._exec("DELETE FROM activity")

    # -- maintenance -----------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        builds = self._query("SELECT COUNT(*) AS c FROM builds")[0]["c"]
        moves = self._query("SELECT COUNT(*) AS c FROM moves")[0]["c"]
        size = self.path.stat().st_size if self.path.exists() else 0
        return {"builds": builds, "moves": moves, "size": size, "path": str(self.path)}

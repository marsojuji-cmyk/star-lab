"""SQLite authoritative sliding window for breaker events."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def db_path() -> Path:
    return _lab_data() / "resilience_events.db"


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            key TEXT NOT NULL,
            success INTEGER NOT NULL,
            weight REAL NOT NULL,
            class TEXT,
            reason TEXT
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_key_ts ON events(key, ts)")
    c.commit()
    return c


def append_event(
    key: str,
    *,
    success: bool,
    weight: float = 1.0,
    class_: str = "behavioral",
    reason: str = "",
) -> None:
    c = _conn()
    try:
        c.execute(
            "INSERT INTO events (ts, key, success, weight, class, reason) VALUES (?,?,?,?,?,?)",
            (time.time(), key, 1 if success else 0, float(weight), class_, reason or ""),
        )
        c.commit()
    finally:
        c.close()


def recent(key: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    c = _conn()
    try:
        rows = c.execute(
            "SELECT ts, key, success, weight, class, reason FROM events WHERE key=? ORDER BY id DESC LIMIT ?",
            (key, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def fail_ratio(key: str, *, window: int = 20) -> Optional[float]:
    rows = recent(key, limit=window)
    if not rows:
        return None
    fail = sum(float(r["weight"]) for r in rows if not r["success"])
    succ = sum(float(r["weight"]) for r in rows if r["success"])
    total = fail + succ
    if total <= 0:
        return None
    return fail / total

"""Persistent galaxy ledger: snapshots + event log (SQLite WAL)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import SCHEMA_VERSION


def lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


class GalaxyStore:
    """
    galaxy.db holds:
      snapshots  — full constellation harvests (JSON payload)
      events     — discrete key/value or typed log lines
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = lab_data()
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(root), 0o700)
        except OSError:
            pass
        gdir = root / "galaxy"
        gdir.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            os.chmod(str(gdir), 0o700)
        except OSError:
            pass
        self.db_path = db_path or (root / "galaxy.db")
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                  id TEXT PRIMARY KEY,
                  schema_version INTEGER NOT NULL,
                  ts REAL NOT NULL,
                  day TEXT NOT NULL,
                  source TEXT NOT NULL,
                  health_score REAL,
                  n_stars INTEGER,
                  payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snap_day ON snapshots(day)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY,
                  schema_version INTEGER NOT NULL,
                  ts REAL NOT NULL,
                  day TEXT NOT NULL,
                  star TEXT NOT NULL,
                  key TEXT NOT NULL,
                  value_json TEXT,
                  note TEXT,
                  source TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evt_ts ON events(ts DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evt_star ON events(star)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_evt_key ON events(key)"
            )

    @staticmethod
    def _day(ts: Optional[float] = None) -> str:
        t = ts if ts is not None else time.time()
        return time.strftime("%Y-%m-%d", time.gmtime(t))

    def log_event(
        self,
        star: str,
        key: str,
        value: Any = None,
        *,
        note: str = "",
        source: str = "manual",
        ts: Optional[float] = None,
    ) -> str:
        eid = uuid.uuid4().hex[:12]
        now = ts if ts is not None else time.time()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO events (
                  id, schema_version, ts, day, star, key, value_json, note, source
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    eid,
                    SCHEMA_VERSION,
                    now,
                    self._day(now),
                    star or "core",
                    key,
                    json.dumps(value, default=str) if value is not None else None,
                    note or "",
                    source,
                ),
            )
        return eid

    def save_snapshot(
        self,
        payload: Dict[str, Any],
        *,
        source: str = "collect",
        ts: Optional[float] = None,
    ) -> str:
        sid = uuid.uuid4().hex[:12]
        now = ts if ts is not None else time.time()
        stars = payload.get("stars") or {}
        health = payload.get("health_score")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                  id, schema_version, ts, day, source, health_score, n_stars, payload_json
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    SCHEMA_VERSION,
                    now,
                    self._day(now),
                    source,
                    float(health) if health is not None else None,
                    len(stars),
                    json.dumps(payload, default=str),
                ),
            )
        return sid

    def latest_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        return d

    def recent_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, schema_version, ts, day, source, health_score, n_stars "
                "FROM snapshots ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit: int = 50, star: str = "") -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if star:
                rows = conn.execute(
                    "SELECT * FROM events WHERE star=? ORDER BY ts DESC LIMIT ?",
                    (star, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            raw = d.pop("value_json", None)
            if raw:
                try:
                    d["value"] = json.loads(raw)
                except json.JSONDecodeError:
                    d["value"] = raw
            else:
                d["value"] = None
            out.append(d)
        return out

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            n_snap = conn.execute("SELECT COUNT(*) AS c FROM snapshots").fetchone()["c"]
            n_evt = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
            last = conn.execute(
                "SELECT ts, health_score FROM snapshots ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return {
            "n_snapshots": n_snap,
            "n_events": n_evt,
            "last_ts": last["ts"] if last else None,
            "last_health": last["health_score"] if last else None,
            "db_path": str(self.db_path),
        }

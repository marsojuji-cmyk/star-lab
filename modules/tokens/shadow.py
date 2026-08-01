"""Shadow dual-log for L1 mode routing (log-only; does not change served decision)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


class ShadowStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = _lab_data()
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(root), 0o700)
        except OSError:
            pass
        self.db_path = db_path or (root / "token_shadow.db")
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
                CREATE TABLE IF NOT EXISTS shadows (
                  id TEXT PRIMARY KEY,
                  ts REAL NOT NULL,
                  audit_id TEXT,
                  task TEXT,
                  served_mode TEXT,
                  served_horizon INTEGER,
                  served_budget INTEGER,
                  served_ev REAL,
                  shadow_policy_id TEXT,
                  shadow_mode TEXT,
                  shadow_horizon INTEGER,
                  shadow_budget INTEGER,
                  shadow_ev REAL,
                  session_id TEXT,
                  tenant TEXT,
                  payload_json TEXT
                )
                """
            )

    def log(
        self,
        *,
        audit_id: str,
        task: str,
        served: Dict[str, Any],
        shadow: Dict[str, Any],
        shadow_policy_id: str = "heuristic_v1_mirror",
        session_id: str = "",
        tenant: str = "",
    ) -> str:
        sid = uuid.uuid4().hex[:12]
        tenant = tenant or os.environ.get("GROK_TENANT", "local")
        session_id = session_id or os.environ.get("GROK_SESSION_ID", "")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO shadows (
                  id, ts, audit_id, task, served_mode, served_horizon, served_budget,
                  served_ev, shadow_policy_id, shadow_mode, shadow_horizon,
                  shadow_budget, shadow_ev, session_id, tenant, payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    time.time(),
                    audit_id,
                    (task or "")[:500],
                    served.get("mode"),
                    served.get("predicted_horizon") or served.get("horizon"),
                    served.get("budget_tokens") or served.get("budget"),
                    served.get("expected_value") or served.get("ev"),
                    shadow_policy_id,
                    shadow.get("mode"),
                    shadow.get("predicted_horizon") or shadow.get("horizon"),
                    shadow.get("budget_tokens") or shadow.get("budget"),
                    shadow.get("expected_value") or shadow.get("ev"),
                    session_id,
                    tenant,
                    json.dumps({"served": served, "shadow": shadow}),
                ),
            )
        return sid

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            n = conn.execute("SELECT COUNT(*) AS c FROM shadows").fetchone()["c"]
            if not n:
                return {"n": 0, "mode_agree_frac": None, "by_served_mode": {}}
            agree = conn.execute(
                """
                SELECT SUM(CASE WHEN served_mode = shadow_mode THEN 1 ELSE 0 END) AS a
                FROM shadows
                """
            ).fetchone()["a"]
            by = conn.execute(
                """
                SELECT served_mode, COUNT(*) AS c FROM shadows GROUP BY served_mode
                """
            ).fetchall()
        return {
            "n": n,
            "mode_agree_frac": (agree / n) if n else None,
            "by_served_mode": {r["served_mode"]: r["c"] for r in by},
            "note": "shadow is log-only; serve baseline until golden gate",
        }

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM shadows ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

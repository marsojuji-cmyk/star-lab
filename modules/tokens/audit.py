"""Audit loop: predicted horizon vs actual tokens vs outcome quality."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


def _lab_data_root() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    grok = os.environ.get("GROK_HOME", os.path.join(os.path.expanduser("~"), ".grok"))
    return Path(grok) / "lab"


@dataclass
class AuditRecord:
    id: str
    ts: float
    task: str
    mode: str
    predicted_horizon: int
    budget_tokens: int
    actual_tokens: Optional[int]
    outcome_quality: Optional[float]  # 0..1 user/system score
    expected_value: float
    success: Optional[bool]
    drivers_json: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = _lab_data_root()
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(root), 0o700)
        except OSError:
            pass
        self.db_path = db_path or (root / "token_policy.db")
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audits (
                  id TEXT PRIMARY KEY,
                  ts REAL NOT NULL,
                  task TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  predicted_horizon INTEGER NOT NULL,
                  budget_tokens INTEGER NOT NULL,
                  actual_tokens INTEGER,
                  outcome_quality REAL,
                  expected_value REAL,
                  success INTEGER,
                  drivers_json TEXT,
                  notes TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rules (
                  id TEXT PRIMARY KEY,
                  ts REAL NOT NULL,
                  rule_json TEXT NOT NULL,
                  support INTEGER NOT NULL,
                  notes TEXT
                )
                """
            )

    def log_route(
        self,
        task: str,
        mode: str,
        predicted_horizon: int,
        budget_tokens: int,
        expected_value: float,
        drivers: List[Dict[str, Any]],
        notes: str = "",
    ) -> str:
        rid = uuid.uuid4().hex[:12]
        rec = AuditRecord(
            id=rid,
            ts=time.time(),
            task=task[:2000],
            mode=mode,
            predicted_horizon=predicted_horizon,
            budget_tokens=budget_tokens,
            actual_tokens=None,
            outcome_quality=None,
            expected_value=expected_value,
            success=None,
            drivers_json=json.dumps(drivers),
            notes=notes,
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO audits
                (id, ts, task, mode, predicted_horizon, budget_tokens, actual_tokens,
                 outcome_quality, expected_value, success, drivers_json, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rec.id,
                    rec.ts,
                    rec.task,
                    rec.mode,
                    rec.predicted_horizon,
                    rec.budget_tokens,
                    rec.actual_tokens,
                    rec.outcome_quality,
                    rec.expected_value,
                    None,
                    rec.drivers_json,
                    rec.notes,
                ),
            )
        return rid

    def complete(
        self,
        audit_id: str,
        actual_tokens: Optional[int],
        outcome_quality: Optional[float],
        success: Optional[bool],
        notes: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE audits SET actual_tokens=?, outcome_quality=?, success=?,
                  notes=CASE WHEN ?='' THEN notes ELSE notes || ' | ' || ? END
                WHERE id=?
                """,
                (
                    actual_tokens,
                    outcome_quality,
                    None if success is None else (1 if success else 0),
                    notes,
                    notes,
                    audit_id,
                ),
            )

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM audits ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def error_stats(self) -> Dict[str, Any]:
        """Compare predicted horizon vs actual when both present."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT predicted_horizon, actual_tokens, mode, outcome_quality
                FROM audits
                WHERE actual_tokens IS NOT NULL
                """
            ).fetchall()
        if not rows:
            return {"n": 0, "mae": None, "overrun_rate": None}
        errs = [abs(r["predicted_horizon"] - r["actual_tokens"]) for r in rows]
        over = sum(1 for r in rows if r["actual_tokens"] > r["predicted_horizon"] * 1.25)
        return {
            "n": len(rows),
            "mae": sum(errs) / len(errs),
            "overrun_rate": over / len(rows),
            "by_mode": _by_mode(rows),
        }

    def save_rule(self, rule: Dict[str, Any], support: int, notes: str = "") -> str:
        rid = uuid.uuid4().hex[:10]
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO rules (id, ts, rule_json, support, notes) VALUES (?,?,?,?,?)",
                (rid, time.time(), json.dumps(rule), support, notes),
            )
        return rid

    def list_rules(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM rules ORDER BY ts DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["rule"] = json.loads(d.pop("rule_json"))
            out.append(d)
        return out


def _by_mode(rows: List[sqlite3.Row]) -> Dict[str, Any]:
    from collections import defaultdict

    buckets: Dict[str, List[int]] = defaultdict(list)
    for r in rows:
        buckets[r["mode"]].append(abs(r["predicted_horizon"] - r["actual_tokens"]))
    return {m: {"n": len(v), "mae": sum(v) / len(v)} for m, v in buckets.items()}

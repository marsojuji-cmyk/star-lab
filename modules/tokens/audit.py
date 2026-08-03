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

    def error_stats(self, *, for_gate: bool = False) -> Dict[str, Any]:
        """Compare predicted horizon vs actual when both present.

        for_gate=True excludes retro:/seed-cycle: notes (backfill volume) and
        returns winsorized MAE so historical under-routes don't permanently
        block online graduation after horizon retune.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT predicted_horizon, actual_tokens, mode, outcome_quality, notes
                FROM audits
                WHERE actual_tokens IS NOT NULL
                """
            ).fetchall()
        if not rows:
            return {"n": 0, "mae": None, "overrun_rate": None, "mae_winsor": None, "mae_median": None}
        rows_list = [dict(r) for r in rows]
        if for_gate:
            cleaned = []
            for r in rows_list:
                notes = (r.get("notes") or "").lower()
                if notes.startswith("retro:") or "seed-cycle:" in notes:
                    continue
                cleaned.append(r)
            # Prefer live/joined; fall back to all if too few
            if len(cleaned) >= 12:
                rows_list = cleaned
        errs = [abs(int(r["predicted_horizon"] or 0) - int(r["actual_tokens"] or 0)) for r in rows_list]
        if not errs:
            return {"n": 0, "mae": None, "overrun_rate": None, "mae_winsor": None, "mae_median": None}
        errs_sorted = sorted(errs)
        mid = errs_sorted[len(errs_sorted) // 2]
        # Winsorize at 5k tokens for gate-friendly calibration signal
        winsor_cap = 5000
        winsor = [min(e, winsor_cap) for e in errs]
        over = sum(
            1
            for r in rows_list
            if int(r["actual_tokens"] or 0) > int(r["predicted_horizon"] or 0) * 1.25
        )
        return {
            "n": len(rows_list),
            "mae": sum(errs) / len(errs),
            "mae_winsor": sum(winsor) / len(winsor),
            "mae_median": float(mid),
            "overrun_rate": over / len(rows_list),
            "by_mode": _by_mode_dicts(rows_list),
            "for_gate": for_gate,
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
    return _by_mode_dicts([dict(r) for r in rows])


def _by_mode_dicts(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    from collections import defaultdict

    buckets: Dict[str, List[int]] = defaultdict(list)
    for r in rows:
        buckets[str(r.get("mode") or "?")].append(
            abs(int(r.get("predicted_horizon") or 0) - int(r.get("actual_tokens") or 0))
        )
    return {m: {"n": len(v), "mae": sum(v) / len(v)} for m, v in buckets.items()}

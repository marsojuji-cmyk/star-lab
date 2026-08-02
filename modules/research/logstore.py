"""Persistent golden-workflow research log."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import SCHEMA_VERSION


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


class ResearchLog:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = _lab_data()
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(root), 0o700)
        except OSError:
            pass
        self.db_path = db_path or (root / "research_log.db")
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
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY,
                  schema_version INTEGER NOT NULL,
                  ts_start REAL NOT NULL,
                  ts_end REAL,
                  status TEXT NOT NULL,
                  task_goal TEXT NOT NULL,
                  repo TEXT,
                  mode TEXT,
                  token_audit_id TEXT,
                  predicted_horizon INTEGER,
                  actual_tokens INTEGER,
                  route_ev REAL,
                  risk_score REAL,
                  success INTEGER,
                  human_interruptions INTEGER DEFAULT 0,
                  tests_passed INTEGER,
                  sqc_quality_ok INTEGER,
                  recovery_triggered INTEGER DEFAULT 0,
                  payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_ts ON tasks(ts_start)"
            )

    def start(
        self,
        task_goal: str,
        *,
        repo: str = "",
        mode: str = "",
        token_audit_id: str = "",
        predicted_horizon: Optional[int] = None,
        route_ev: Optional[float] = None,
        risk_score: Optional[float] = None,
        context_pack: Optional[Dict[str, Any]] = None,
    ) -> str:
        tid = uuid.uuid4().hex[:12]
        now = time.time()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "id": tid,
            "ts_start": now,
            "ts_end": None,
            "status": "open",
            "task_goal": task_goal,
            "repo": repo,
            "mode": mode,
            "token_audit_id": token_audit_id or None,
            "predicted_horizon": predicted_horizon,
            "actual_tokens": None,
            "route_ev": route_ev,
            "risk_score": risk_score,
            "context_pack": context_pack or {},
            "actions": [],
            "validation": {
                "tests_ran": False,
                "tests_passed": None,
                "ship_check": None,
                "sqc_loop_id": None,
                "sqc_quality_ok": None,
            },
            "recovery": {"triggered": False, "notes": ""},
            "outcome": {
                "success": None,
                "human_interruptions": 0,
                "notes": "",
            },
            "metrics": {"tokens_per_success": None, "latency_s": None},
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                  id, schema_version, ts_start, ts_end, status, task_goal, repo, mode,
                  token_audit_id, predicted_horizon, actual_tokens, route_ev, risk_score,
                  success, human_interruptions, tests_passed, sqc_quality_ok,
                  recovery_triggered, payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    tid,
                    SCHEMA_VERSION,
                    now,
                    None,
                    "open",
                    task_goal,
                    repo,
                    mode,
                    token_audit_id or None,
                    predicted_horizon,
                    None,
                    route_ev,
                    risk_score,
                    None,
                    0,
                    None,
                    None,
                    0,
                    json.dumps(payload),
                ),
            )
        return tid

    def _load(self, task_id: str) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload_json FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"unknown task id: {task_id}")
        return json.loads(row["payload_json"])

    def _save(self, payload: Dict[str, Any]) -> None:
        tid = payload["id"]
        outcome = payload.get("outcome") or {}
        validation = payload.get("validation") or {}
        recovery = payload.get("recovery") or {}
        metrics = payload.get("metrics") or {}
        success = outcome.get("success")
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE tasks SET
                  ts_end=?, status=?, mode=?, token_audit_id=?, predicted_horizon=?,
                  actual_tokens=?, route_ev=?, risk_score=?, success=?,
                  human_interruptions=?, tests_passed=?, sqc_quality_ok=?,
                  recovery_triggered=?, payload_json=?
                WHERE id=?
                """,
                (
                    payload.get("ts_end"),
                    payload.get("status"),
                    payload.get("mode"),
                    payload.get("token_audit_id"),
                    payload.get("predicted_horizon"),
                    payload.get("actual_tokens"),
                    payload.get("route_ev"),
                    payload.get("risk_score"),
                    None if success is None else (1 if success else 0),
                    int(outcome.get("human_interruptions") or 0),
                    validation.get("tests_passed")
                    if validation.get("tests_passed") is None
                    else (1 if validation.get("tests_passed") else 0),
                    None
                    if validation.get("sqc_quality_ok") is None
                    else (1 if validation.get("sqc_quality_ok") else 0),
                    1 if recovery.get("triggered") else 0,
                    json.dumps(payload),
                    tid,
                ),
            )

    def action(
        self,
        task_id: str,
        *,
        type: str,
        name: str,
        ok: bool = True,
        notes: str = "",
    ) -> None:
        p = self._load(task_id)
        p.setdefault("actions", []).append(
            {"ts": time.time(), "type": type, "name": name, "ok": ok, "notes": notes}
        )
        self._save(p)

    def attach_context_pack(self, task_id: str, pack: Dict[str, Any]) -> None:
        """Merge/replace context_pack on an open task (e.g. from a packet)."""
        p = self._load(task_id)
        existing = p.get("context_pack") or {}
        if not isinstance(existing, dict):
            existing = {}
        merged = dict(existing)
        merged.update(pack or {})
        p["context_pack"] = merged
        # surface packet id if present
        if pack.get("id"):
            p["packet_id"] = pack.get("id")
        self._save(p)

    def complete(
        self,
        task_id: str,
        *,
        success: bool,
        actual_tokens: Optional[int] = None,
        tests_passed: Optional[bool] = None,
        sqc_loop_id: Optional[str] = None,
        sqc_quality_ok: Optional[bool] = None,
        recovery_triggered: bool = False,
        recovery_notes: str = "",
        human_interruptions: int = 0,
        notes: str = "",
    ) -> Dict[str, Any]:
        p = self._load(task_id)
        now = time.time()
        p["ts_end"] = now
        p["status"] = "completed" if success else "aborted"
        if actual_tokens is not None:
            p["actual_tokens"] = actual_tokens
        p["outcome"]["success"] = success
        p["outcome"]["human_interruptions"] = human_interruptions
        p["outcome"]["notes"] = notes
        if tests_passed is not None:
            p["validation"]["tests_ran"] = True
            p["validation"]["tests_passed"] = tests_passed
        if sqc_loop_id is not None:
            p["validation"]["sqc_loop_id"] = sqc_loop_id
        if sqc_quality_ok is not None:
            p["validation"]["sqc_quality_ok"] = sqc_quality_ok
        # Preserve LEAD recover() flag: complete --recovery may be omitted by operators.
        prev_trig = bool((p.get("recovery") or {}).get("triggered"))
        p.setdefault("recovery", {})
        p["recovery"]["triggered"] = bool(recovery_triggered) or prev_trig
        if recovery_notes:
            prev_notes = p["recovery"].get("notes") or ""
            p["recovery"]["notes"] = (prev_notes + "\n" + recovery_notes).strip()
        latency = now - float(p.get("ts_start") or now)
        p["metrics"]["latency_s"] = round(latency, 3)
        tok = p.get("actual_tokens")
        if success and tok is not None and tok >= 0:
            p["metrics"]["tokens_per_success"] = tok
        elif success:
            p["metrics"]["tokens_per_success"] = 0
        else:
            p["metrics"]["tokens_per_success"] = None
        self._save(p)
        return p

    def list(self, limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT payload_json FROM tasks WHERE status=? ORDER BY ts_start DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload_json FROM tasks ORDER BY ts_start DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def kpi(self) -> Dict[str, Any]:
        """Loop 4 product metrics from completed golden logs + token/sqc side channels."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status IN ('completed','aborted')"
            ).fetchall()
        n = len(rows)
        if n == 0:
            base = {
                "n_completed_logs": 0,
                "test_pass_rate": None,
                "accepted_patch_rate": None,
                "average_tokens_per_success": None,
                "recovery_rate_after_failure": None,
                "latency_per_completed_task_s": None,
                "human_interruptions_avg": None,
                "sqc_pass_rate": None,
            }
        else:
            successes = [r for r in rows if r["success"] == 1]
            tested = [r for r in rows if r["tests_passed"] is not None]
            tests_ok = [r for r in tested if r["tests_passed"] == 1]
            tok_succ = [
                r["actual_tokens"]
                for r in successes
                if r["actual_tokens"] is not None
            ]
            recovered = [r for r in rows if r["recovery_triggered"] == 1]
            # recovery_rate among non-success that recovered is hard; report among all with recovery flag
            latencies = []
            interrupts = []
            sqc_rows = [r for r in rows if r["sqc_quality_ok"] is not None]
            sqc_ok = [r for r in sqc_rows if r["sqc_quality_ok"] == 1]
            for r in rows:
                payload = json.loads(r["payload_json"])
                lat = (payload.get("metrics") or {}).get("latency_s")
                if lat is not None:
                    latencies.append(lat)
                interrupts.append(int(r["human_interruptions"] or 0))

            base = {
                "n_completed_logs": n,
                "n_success": len(successes),
                "test_pass_rate": (len(tests_ok) / len(tested)) if tested else None,
                "accepted_patch_rate": len(successes) / n,
                "average_tokens_per_success": (
                    sum(tok_succ) / len(tok_succ) if tok_succ else None
                ),
                "recovery_rate_after_failure": (
                    len(recovered) / n if n else None
                ),
                "latency_per_completed_task_s": (
                    sum(latencies) / len(latencies) if latencies else None
                ),
                "human_interruptions_avg": (
                    sum(interrupts) / len(interrupts) if interrupts else None
                ),
                "sqc_pass_rate": (len(sqc_ok) / len(sqc_rows)) if sqc_rows else None,
            }

        # Side channel: token audits
        token_stats = {}
        token_db = _lab_data() / "token_policy.db"
        if token_db.exists():
            try:
                from tokens.audit import AuditStore

                token_stats = AuditStore(db_path=token_db).error_stats()
            except Exception as e:
                token_stats = {"error": str(e)}

        # Side channel: last SQC loop
        sqc_log = _lab_data() / "sqc" / "loop_log.jsonl"
        last_sqc = None
        sqc_accepts = sqc_total = 0
        if sqc_log.exists():
            for line in sqc_log.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sqc_total += 1
                if row.get("quality_sufficient"):
                    sqc_accepts += 1
                last_sqc = row
        base["token_audit_stats"] = token_stats
        base["sqc_loop_accept_rate"] = (
            sqc_accepts / sqc_total if sqc_total else None
        )
        base["sqc_loops_total"] = sqc_total
        base["last_sqc_decision"] = (
            None if not last_sqc else last_sqc.get("decision")
        )
        base["schema_version"] = SCHEMA_VERSION
        base["generated_at"] = time.time()
        return base

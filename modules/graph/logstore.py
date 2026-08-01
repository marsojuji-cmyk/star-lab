"""Persistent graph node / context-route logs."""

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


class GraphLog:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        root = _lab_data()
        root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(root), 0o700)
        except OSError:
            pass
        self.db_path = db_path or (root / "graph_routes.db")
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
                CREATE TABLE IF NOT EXISTS nodes (
                  id TEXT PRIMARY KEY,
                  ts REAL NOT NULL,
                  role TEXT,
                  stage TEXT,
                  input_tokens INTEGER,
                  output_tokens INTEGER,
                  budget_tokens INTEGER,
                  context_tokens_used INTEGER,
                  policy TEXT,
                  n_passed INTEGER,
                  n_summarized INTEGER,
                  n_dropped INTEGER,
                  tokens_passed INTEGER,
                  tokens_summarized INTEGER,
                  tokens_dropped INTEGER,
                  session_id TEXT,
                  tenant TEXT,
                  parent_task_id TEXT,
                  downstream TEXT,
                  payload_json TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_ts ON nodes(ts)"
            )

    def log_node(
        self,
        *,
        role: str,
        stage: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        budget_tokens: Optional[int] = None,
        context_tokens_used: Optional[int] = None,
        policy: str = "",
        n_passed: int = 0,
        n_summarized: int = 0,
        n_dropped: int = 0,
        tokens_passed: int = 0,
        tokens_summarized: int = 0,
        tokens_dropped: int = 0,
        session_id: str = "",
        tenant: str = "",
        parent_task_id: str = "",
        downstream: Optional[List[str]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        nid = uuid.uuid4().hex[:12]
        tenant = tenant or os.environ.get("GROK_TENANT", "local")
        session_id = session_id or os.environ.get("GROK_SESSION_ID", "")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO nodes (
                  id, ts, role, stage, input_tokens, output_tokens, budget_tokens,
                  context_tokens_used, policy, n_passed, n_summarized, n_dropped,
                  tokens_passed, tokens_summarized, tokens_dropped,
                  session_id, tenant, parent_task_id, downstream, payload_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    nid,
                    time.time(),
                    role,
                    stage,
                    input_tokens,
                    output_tokens,
                    budget_tokens,
                    context_tokens_used,
                    policy,
                    n_passed,
                    n_summarized,
                    n_dropped,
                    tokens_passed,
                    tokens_summarized,
                    tokens_dropped,
                    session_id,
                    tenant,
                    parent_task_id,
                    json.dumps(downstream or []),
                    json.dumps(payload or {}),
                ),
            )
        return nid

    def log_route_result(
        self,
        result: Dict[str, Any],
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        session_id: str = "",
        parent_task_id: str = "",
        downstream: Optional[List[str]] = None,
    ) -> str:
        carried = int(result.get("tokens_passed") or 0) + int(
            result.get("tokens_summarized") or 0
        )
        return self.log_node(
            role=str(result.get("role") or ""),
            stage=str(result.get("stage") or ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            budget_tokens=result.get("budget"),
            context_tokens_used=carried,
            policy=str(result.get("policy") or ""),
            n_passed=int(result.get("n_passed") or 0),
            n_summarized=int(result.get("n_summarized") or 0),
            n_dropped=int(result.get("n_dropped") or 0),
            tokens_passed=int(result.get("tokens_passed") or 0),
            tokens_summarized=int(result.get("tokens_summarized") or 0),
            tokens_dropped=int(result.get("tokens_dropped") or 0),
            session_id=session_id,
            parent_task_id=parent_task_id,
            downstream=downstream,
            payload=result,
        )

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM nodes ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._conn() as conn:
            n = conn.execute("SELECT COUNT(*) AS c FROM nodes").fetchone()["c"]
            if not n:
                return {
                    "n_nodes": 0,
                    "tokens_per_agent_round": None,
                    "context_dropped_frac": None,
                    "by_policy": {},
                }
            row = conn.execute(
                """
                SELECT
                  AVG(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)) AS avg_io,
                  AVG(COALESCE(context_tokens_used,0)) AS avg_ctx,
                  SUM(COALESCE(tokens_passed,0)) AS sum_pass,
                  SUM(COALESCE(tokens_summarized,0)) AS sum_sum,
                  SUM(COALESCE(tokens_dropped,0)) AS sum_drop
                FROM nodes
                """
            ).fetchone()
            by_pol = conn.execute(
                """
                SELECT policy, COUNT(*) AS c,
                       AVG(COALESCE(context_tokens_used,0)) AS avg_ctx
                FROM nodes GROUP BY policy
                """
            ).fetchall()
        carried = (row["sum_pass"] or 0) + (row["sum_sum"] or 0)
        dropped = row["sum_drop"] or 0
        denom = carried + dropped
        return {
            "n_nodes": n,
            "tokens_per_agent_round": row["avg_io"],
            "avg_context_tokens": row["avg_ctx"],
            "context_dropped_frac": (dropped / denom) if denom else None,
            "tokens_passed": row["sum_pass"],
            "tokens_summarized": row["sum_sum"],
            "tokens_dropped": row["sum_drop"],
            "by_policy": {
                (r["policy"] or "unknown"): {
                    "n": r["c"],
                    "avg_ctx": r["avg_ctx"],
                }
                for r in by_pol
            },
            "north_star": "cost_per_successful_end_to_end_task",
        }

"""Golden workflow log schema (paper Phase 1 + Loop 4 metrics)."""

from __future__ import annotations

SCHEMA_VERSION = 1

# Required fields when completing a task log
REQUIRED_COMPLETE = (
    "task_goal",
    "success",
)

# Full instrumented record
EXAMPLE_RECORD = {
    "schema_version": SCHEMA_VERSION,
    "id": "abc123",
    "ts_start": 0.0,
    "ts_end": None,
    "status": "open",  # open | completed | aborted
    "task_goal": "Fix failing unit tests in starlab-demo",
    "repo": "starlab-demo",
    "mode": "short",  # from lab tokens route
    "token_audit_id": None,
    "predicted_horizon": None,
    "actual_tokens": None,
    "route_ev": None,
    "risk_score": None,
    "context_pack": {
        "files": [],
        "summaries": [],
        "retrieval_k": 0,
        "max_context_tokens": 0,
    },
    "actions": [
        # {"type": "tool|local|grok", "name": "...", "ok": true, "notes": "..."}
    ],
    "validation": {
        "tests_ran": False,
        "tests_passed": None,
        "ship_check": None,
        "sqc_loop_id": None,
        "sqc_quality_ok": None,
    },
    "recovery": {
        "triggered": False,
        "notes": "",
    },
    "outcome": {
        "success": None,
        "human_interruptions": 0,
        "notes": "",
    },
    "metrics": {
        "tokens_per_success": None,
        "latency_s": None,
    },
}

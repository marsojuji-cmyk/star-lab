"""Distill audit traces into routing rules for continuous redeploy."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .audit import AuditStore


class SQCGateError(RuntimeError):
    """Raised when distill is blocked by the annotation quality (Loop 3) gate."""


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def last_sqc_loop() -> Optional[Dict[str, Any]]:
    path = _lab_data() / "sqc" / "loop_log.jsonl"
    if not path.exists():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def assert_sqc_gate(allow_ungated: bool = False) -> Dict[str, Any]:
    """
    Hard gate for Loop 3: refuse distill unless the latest SQC loop accepted.

    Set allow_ungated=True or env GROK_SQC_DISTILL_UNGated=1 only for bootstrap/debug.
    """
    if allow_ungated or os.environ.get("GROK_SQC_DISTILL_UNGATED", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return {"gated": False, "reason": "ungated_override"}

    last = last_sqc_loop()
    if last is None:
        raise SQCGateError(
            "distill blocked: no lab sqc loop log yet. "
            "Run `lab sqc loop --file items.json` and get quality_sufficient=true first "
            "(or GROK_SQC_DISTILL_UNGATED=1 for bootstrap only)."
        )
    if not last.get("quality_sufficient"):
        raise SQCGateError(
            "distill blocked: last SQC loop did not pass quality gate "
            f"(decision={last.get('decision')}, loop_id={last.get('loop_id')}). "
            "Correct annotations / re-run lab sqc loop before distill."
        )
    return {
        "gated": True,
        "loop_id": last.get("loop_id"),
        "decision": last.get("decision"),
    }


def distill_rules(
    store: AuditStore,
    min_support: int = 3,
    *,
    require_sqc: bool = True,
    allow_ungated: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    From completed audits, emit simple if-then routing rules.

    Returns (rules, gate_info). Raises SQCGateError if require_sqc and gate fails.
    """
    gate_info: Dict[str, Any] = {"gated": False}
    if require_sqc:
        gate_info = assert_sqc_gate(allow_ungated=allow_ungated)

    rows = store.recent(limit=500)
    # Only rows with outcome
    done = [r for r in rows if r.get("outcome_quality") is not None or r.get("success") is not None]
    if not done:
        return [], gate_info

    by_mode: Dict[str, List[dict]] = defaultdict(list)
    for r in done:
        by_mode[r["mode"]].append(r)

    rules: List[Dict[str, Any]] = []

    # Rule: high quality on short with low horizon → lock short band
    short_hi = [
        r
        for r in by_mode.get("short", [])
        if (r.get("outcome_quality") or 0) >= 0.8 and r["predicted_horizon"] < 800
    ]
    if len(short_hi) >= min_support:
        rule = {
            "if": {"horizon_lt": 800, "tags_any": ["cheap", "ops_local", "general"]},
            "then": {"mode": "short", "max_budget": 512},
            "because": "short mode high quality on low-horizon tasks",
        }
        rules.append(rule)
        store.save_rule(rule, support=len(short_hi), notes="distill:short_hi")

    # Rule: deep with low quality → don't escalate
    deep_lo = [
        r
        for r in by_mode.get("deep", [])
        if (r.get("outcome_quality") is not None and r["outcome_quality"] < 0.5)
        or r.get("success") == 0
    ]
    if len(deep_lo) >= min_support:
        rule = {
            "if": {"mode_was": "deep", "quality_lt": 0.5},
            "then": {"prefer_mode": "medium", "block_deep_unless_horizon_gt": 4000},
            "because": "deep spent tokens without quality payoff",
        }
        rules.append(rule)
        store.save_rule(rule, support=len(deep_lo), notes="distill:deep_lo")

    # Rule: local success on ops
    local_ok = [
        r
        for r in by_mode.get("local", [])
        if r.get("success") == 1 or (r.get("outcome_quality") or 0) >= 0.9
    ]
    if len(local_ok) >= min_support:
        rule = {
            "if": {"task_regex": r"\b(status|doctor|list|help)\b"},
            "then": {"mode": "local"},
            "because": "ops queries resolved locally with high quality",
        }
        rules.append(rule)
        store.save_rule(rule, support=len(local_ok), notes="distill:local_ops")

    return rules, gate_info

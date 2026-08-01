"""Distill audit traces into routing rules for continuous redeploy."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from .audit import AuditStore


def distill_rules(store: AuditStore, min_support: int = 3) -> List[Dict[str, Any]]:
    """
    From completed audits, emit simple if-then routing rules:
      if tags-like task patterns underperform in deep with low quality → prefer medium
      if short succeeds with high quality → prefer short for similar horizon band
    """
    rows = store.recent(limit=500)
    # Only rows with outcome
    done = [r for r in rows if r.get("outcome_quality") is not None or r.get("success") is not None]
    if not done:
        return []

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

    return rules

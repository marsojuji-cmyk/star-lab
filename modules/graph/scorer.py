"""
Three-gate importance scorer α(m; role, stage):

1. role relevance
2. task-stage priority
3. recency / importance
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

# Keywords associated with roles (lightweight heuristic).
ROLE_KEYWORDS: Dict[str, List[str]] = {
    "planner": ["plan", "design", "architecture", "goal", "scope", "roadmap"],
    "searcher": ["search", "find", "docs", "knowledge", "reference", "file"],
    "implementer": ["code", "implement", "patch", "function", "class", "edit"],
    "executor": ["run", "command", "script", "tool", "forge"],
    "validator": ["test", "assert", "fail", "error", "unittest", "pass"],
    "reviewer": ["review", "diff", "risk", "quality", "style"],
    "recoverer": ["recover", "retry", "failing", "lead", "scope cut"],
    "summarizer": ["summary", "notes", "outcome", "result"],
    "main": ["goal", "task", "user", "priority"],
    "default": [],
}

STAGE_KEYWORDS: Dict[str, List[str]] = {
    "plan": ["plan", "design", "scope", "goal"],
    "implement": ["code", "patch", "implement", "change"],
    "execute": ["run", "command", "tool"],
    "validate": ["test", "fail", "error", "assert", "pass"],
    "recover": ["recover", "retry", "failing", "minimal"],
    "ship": ["ship", "commit", "release"],
    "default": [],
}


def _text_of(item: Dict[str, Any]) -> str:
    parts = [
        str(item.get("id") or ""),
        str(item.get("kind") or ""),
        str(item.get("role") or ""),
        str(item.get("stage") or ""),
        str(item.get("text") or item.get("content") or ""),
        " ".join(str(t) for t in (item.get("tags") or [])),
    ]
    return " ".join(parts).lower()


def _token_len(item: Dict[str, Any]) -> int:
    if item.get("tokens") is not None:
        try:
            return max(1, int(item["tokens"]))
        except (TypeError, ValueError):
            pass
    text = str(item.get("text") or item.get("content") or "")
    # ~4 chars/token heuristic
    return max(1, len(text) // 4)


def score_item(
    item: Dict[str, Any],
    role: str,
    stage: str,
    *,
    now: Optional[float] = None,
    w_role: float = 0.45,
    w_stage: float = 0.30,
    w_recency: float = 0.25,
) -> float:
    """Return α in ~[0,1] combining three gates."""
    now = now if now is not None else time.time()
    text = _text_of(item)
    role_key = (role or "default").lower()
    stage_key = (stage or "default").lower()

    # Gate 1: role relevance
    rkw = ROLE_KEYWORDS.get(role_key, []) + ROLE_KEYWORDS.get("default", [])
    role_hits = sum(1 for k in rkw if k and k in text)
    # also boost if item.role matches
    if str(item.get("role") or "").lower() == role_key:
        role_hits += 2
    role_score = min(1.0, role_hits / max(3.0, len(rkw) * 0.5 or 1.0))

    # Gate 2: stage priority
    skw = STAGE_KEYWORDS.get(stage_key, STAGE_KEYWORDS["default"])
    stage_hits = sum(1 for k in skw if k and k in text)
    if str(item.get("stage") or "").lower() == stage_key:
        stage_hits += 2
    # explicit priority field 0..1
    if item.get("priority") is not None:
        try:
            stage_score = max(stage_hits / 4.0, float(item["priority"]))
        except (TypeError, ValueError):
            stage_score = min(1.0, stage_hits / 4.0)
    else:
        stage_score = min(1.0, stage_hits / 4.0)

    # Gate 3: recency / importance
    ts = item.get("ts") or item.get("timestamp")
    recency = 0.5
    if ts is not None:
        try:
            age = max(0.0, now - float(ts))
            # half-life ~1 hour
            recency = max(0.05, min(1.0, 2.0 ** (-age / 3600.0)))
        except (TypeError, ValueError):
            pass
    imp = item.get("importance")
    if imp is not None:
        try:
            recency = max(recency, min(1.0, float(imp)))
        except (TypeError, ValueError):
            pass
    # failures / guardrails are high importance for validators/recoverers
    kind = str(item.get("kind") or "").lower()
    if kind in ("failure", "error", "guardrail", "packet"):
        recency = min(1.0, recency + 0.25)

    alpha = w_role * role_score + w_stage * stage_score + w_recency * recency
    # floor so empty memory still ranks something
    return float(max(0.0, min(1.0, alpha)))


def estimate_tokens(item: Dict[str, Any]) -> int:
    return _token_len(item)

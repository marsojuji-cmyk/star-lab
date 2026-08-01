"""
Lightweight annotation / output risk scorer.

Inspired by the paper's annotation quality skill + Apple-style error modeling:
score likely bad labels from behavioral and task features (no trained net required
for V1 — heuristic features that prioritize audits).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RiskScore:
    score: float  # 0..1 higher = more likely bad / needs audit
    drivers: List[Dict[str, Any]]
    recommend_audit: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_RISK_PATTERNS = [
    ("empty", re.compile(r"^\s*$"), 0.95),
    ("todo", re.compile(r"\b(TODO|FIXME|XXX|HACK)\b"), 0.35),
    ("uncertain", re.compile(r"\b(maybe|not sure|guess|approx|idk|unknown)\b", re.I), 0.40),
    ("contradict", re.compile(r"\b(however|but actually|wait|correction:)\b", re.I), 0.25),
    ("very_short", None, 0.30),  # handled specially
    ("very_long", None, 0.15),
    ("low_confidence_tag", re.compile(r"\b(conf(idence)?\s*[:=]\s*low|low[_-]?conf)\b", re.I), 0.55),
]


def score_item_risk(
    text: str,
    *,
    label: Optional[str] = None,
    latency_ms: Optional[float] = None,
    edit_count: int = 0,
    prior_reject: bool = False,
    audit_threshold: float = 0.45,
) -> RiskScore:
    """
    Score a single annotation or model output for audit priority.

    Features (behavioral + task):
      - empty / tiny / huge text
      - uncertainty language
      - many edits (unstable labeling)
      - slow response (optional)
      - prior reject flag
    """
    drivers: List[Dict[str, Any]] = []
    score = 0.0
    t = text or ""
    n = len(t.strip())

    if n == 0:
        drivers.append({"feature": "empty", "delta": 0.95})
        score += 0.95
    elif n < 8:
        drivers.append({"feature": "very_short", "delta": 0.30, "n": n})
        score += 0.30
    elif n > 4000:
        drivers.append({"feature": "very_long", "delta": 0.15, "n": n})
        score += 0.15

    for name, pat, delta in _RISK_PATTERNS:
        if pat is None:
            continue
        if pat.search(t):
            drivers.append({"feature": name, "delta": delta})
            score += delta

    if label is not None and str(label).strip() == "":
        drivers.append({"feature": "empty_label", "delta": 0.9})
        score += 0.9

    if edit_count >= 3:
        d = min(0.4, 0.1 * edit_count)
        drivers.append({"feature": "many_edits", "delta": d, "edit_count": edit_count})
        score += d

    if latency_ms is not None and latency_ms > 120_000:
        drivers.append({"feature": "slow_latency", "delta": 0.2, "latency_ms": latency_ms})
        score += 0.2

    if prior_reject:
        drivers.append({"feature": "prior_reject", "delta": 0.35})
        score += 0.35

    score = max(0.0, min(1.0, score))
    return RiskScore(
        score=round(score, 4),
        drivers=drivers,
        recommend_audit=score >= audit_threshold,
    )


def prioritize_for_audit(
    items: List[Dict[str, Any]],
    text_key: str = "text",
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return items sorted by risk descending, with risk fields attached."""
    scored = []
    for it in items:
        text = str(it.get(text_key, it.get("body", it.get("output", ""))))
        rs = score_item_risk(
            text,
            label=it.get("label"),
            latency_ms=it.get("latency_ms"),
            edit_count=int(it.get("edit_count") or 0),
            prior_reject=bool(it.get("prior_reject")),
        )
        row = dict(it)
        row["risk"] = rs.to_dict()
        scored.append(row)
    scored.sort(key=lambda r: r["risk"]["score"], reverse=True)
    if top_k is not None:
        return scored[:top_k]
    return scored

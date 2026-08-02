"""Failure taxonomy weights for agentic breakers."""

from __future__ import annotations

from typing import Any, Dict

# class → default weight
WEIGHTS: Dict[str, float] = {
    "hard": 3.0,  # crash, timeout hard, exit≠0 after recover
    "structural": 2.0,  # schema/tool missing
    "semantic": 1.5,  # wrong answer (deferred judges)
    "behavioral": 1.0,  # flaky / thrash
    "cost": 1.2,  # budget overrun signal
    "success": 1.0,
}


def classify(
    *,
    exit_code: int = 0,
    retry_ok: Any = None,
    timeout: bool = False,
    cost_overrun: bool = False,
    hint: str = "",
) -> str:
    if timeout or exit_code == 124:
        return "hard"
    if retry_ok is False:
        return "hard"
    if exit_code not in (0, None):
        return "structural" if exit_code in (127, 126) else "behavioral"
    if cost_overrun:
        return "cost"
    if hint in WEIGHTS:
        return hint
    return "behavioral"


def weight_for(class_: str) -> float:
    return float(WEIGHTS.get(class_ or "behavioral", 1.0))

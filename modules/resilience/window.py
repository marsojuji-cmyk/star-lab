"""Window helpers for breaker ratios."""

from __future__ import annotations

from typing import Iterable, Optional, Tuple


def weighted_fail_ratio(
    samples: Iterable[Tuple[bool, float]],
) -> Optional[float]:
    fail = 0.0
    succ = 0.0
    for success, weight in samples:
        w = abs(float(weight))
        if success:
            succ += w
        else:
            fail += w
    total = fail + succ
    if total <= 0:
        return None
    return fail / total


def hard_count(classes: Iterable[str]) -> int:
    return sum(1 for c in classes if c == "hard")

"""
Token-level length / reasoning-horizon estimation (LenVM-inspired).

Full LenVM (arxiv:2604.27039) is a trained value head that predicts remaining
generation horizon at every decode step as discounted return under constant
per-token cost. We cannot ship Apple's weights here for free-offline operation.

This module provides a *policy-compatible* free estimator:
  - prompt-boundary horizon H0 (predicted total tokens if we call Grok)
  - per-feature drivers that push toward short vs long regimes
  - a value-style score V = -discounted_token_cost (monotone with length)

When a real LenVM probe becomes available (env GROK_LENVM_CMD), we delegate.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# Rough chars-per-token for English-ish technical text (conservative).
_CHARS_PER_TOKEN = 4.0

# Heuristic feature weights for remaining-horizon boost (tokens).
_FEATURE_BOOSTS: List[Tuple[str, re.Pattern, float]] = [
    ("multi_step", re.compile(r"\b(step[- ]by[- ]step|plan|design|architect|migrate|refactor)\b", re.I), 800),
    ("debug", re.compile(r"\b(debug|root[- ]cause|investigate|why (is|does)|fails?|error)\b", re.I), 600),
    ("implement", re.compile(r"\b(implement|build|write|create|scaffold|code)\b", re.I), 500),
    ("review", re.compile(r"\b(review|audit|security|threat)\b", re.I), 400),
    ("compare", re.compile(r"\b(compare|trade[- ]?off|alternatives|vs\.?)\b", re.I), 350),
    ("explain", re.compile(r"\b(explain|how does|what is|summar(y|ize))\b", re.I), 150),
    ("local_only", re.compile(r"\b(status|doctor|list|help|version|open dashboard)\b", re.I), -400),
    ("one_shot", re.compile(r"\b(rename|typo|one[- ]line|quick|trivial)\b", re.I), -300),
    ("multi_file", re.compile(r"\b(codebase|entire repo|all files|monorepo)\b", re.I), 700),
    ("agentic", re.compile(r"\b(subagent|workflow|parallel|multi[- ]agent)\b", re.I), 900),
]


@dataclass
class HorizonEstimate:
    """Predicted reasoning / generation horizon for a task."""

    predicted_tokens: int
    confidence: float  # 0..1
    method: str  # heuristic | lenvm | hybrid
    drivers: List[Dict[str, Any]] = field(default_factory=list)
    prompt_tokens_est: int = 0
    remaining_value: float = 0.0  # LenVM-style V ≈ -γ-discounted length
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, int(math.ceil(len(text) / _CHARS_PER_TOKEN)))


def _heuristic_horizon(task: str, context_chars: int = 0) -> HorizonEstimate:
    prompt_tok = estimate_tokens_from_text(task) + int(context_chars / _CHARS_PER_TOKEN)
    base = 200  # short reply floor
    drivers: List[Dict[str, Any]] = []
    boost = 0.0
    for name, pat, delta in _FEATURE_BOOSTS:
        if pat.search(task):
            boost += delta
            drivers.append(
                {
                    "token_or_pattern": name,
                    "delta_tokens": delta,
                    "regime": "long" if delta > 0 else "short",
                    "matched": True,
                }
            )

    # Length of the ask itself correlates with answer length.
    ask_boost = min(1500, prompt_tok * 2)
    predicted = int(max(64, base + boost + ask_boost))
    # Soft cap: free offline policy shouldn't assume infinite budgets.
    predicted = min(predicted, 12000)

    # Confidence: more matched drivers → higher; extremes lower.
    conf = 0.45 + 0.08 * min(6, len(drivers))
    conf = min(0.92, conf)

    # Value signal: constant negative reward per token (LenVM setup), γ=0.999
    # V ≈ -sum γ^t ≈ -predicted for γ≈1 over practical horizons.
    gamma = 0.999
    if predicted <= 0:
        remaining_value = 0.0
    else:
        remaining_value = -(1.0 - gamma ** predicted) / (1.0 - gamma)

    return HorizonEstimate(
        predicted_tokens=predicted,
        confidence=round(conf, 3),
        method="heuristic",
        drivers=drivers,
        prompt_tokens_est=prompt_tok,
        remaining_value=round(remaining_value, 2),
        notes="Free offline estimator; plug GROK_LENVM_CMD for trained LenVM.",
    )


def _try_lenvm_probe(task: str) -> Optional[HorizonEstimate]:
    """Optional external LenVM binary/script: prints JSON {predicted_tokens, confidence}."""
    cmd = os.environ.get("GROK_LENVM_CMD", "").strip()
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            input=task.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(os.environ.get("GROK_LENVM_TIMEOUT", "5")),
            check=False,
        )
        if proc.returncode != 0:
            return None
        import json

        data = json.loads(proc.stdout.decode("utf-8"))
        pt = int(data.get("predicted_tokens") or data.get("horizon") or 0)
        if pt <= 0:
            return None
        conf = float(data.get("confidence", 0.8))
        return HorizonEstimate(
            predicted_tokens=pt,
            confidence=max(0.0, min(1.0, conf)),
            method="lenvm",
            drivers=list(data.get("drivers") or []),
            prompt_tokens_est=int(data.get("prompt_tokens_est") or estimate_tokens_from_text(task)),
            remaining_value=float(data.get("remaining_value") or -float(pt)),
            notes="From GROK_LENVM_CMD",
        )
    except (OSError, ValueError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def estimate_horizon(task: str, context_chars: int = 0) -> HorizonEstimate:
    """Estimate remaining reasoning horizon for *task* (prompt-boundary prediction)."""
    task = (task or "").strip()
    if not task:
        return HorizonEstimate(
            predicted_tokens=0,
            confidence=1.0,
            method="heuristic",
            notes="empty task",
        )

    external = _try_lenvm_probe(task)
    heuristic = _heuristic_horizon(task, context_chars=context_chars)
    if external is None:
        return heuristic

    # Hybrid: blend external LenVM with heuristic floor/ceiling.
    blended = int(0.7 * external.predicted_tokens + 0.3 * heuristic.predicted_tokens)
    drivers = list(external.drivers) + [
        {"token_or_pattern": "heuristic_blend", "delta_tokens": blended - external.predicted_tokens, "regime": "hybrid"}
    ]
    return HorizonEstimate(
        predicted_tokens=max(64, blended),
        confidence=round(min(0.95, 0.5 * external.confidence + 0.5 * heuristic.confidence), 3),
        method="hybrid",
        drivers=drivers,
        prompt_tokens_est=max(external.prompt_tokens_est, heuristic.prompt_tokens_est),
        remaining_value=external.remaining_value,
        notes="LenVM probe + heuristic blend",
    )

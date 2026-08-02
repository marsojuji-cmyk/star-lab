"""
Token-aware invocation policy.

Operational rule (default for Grok Build / Star Lab):
  For every task, compute
      EV_grok = expected_reward(mode) - λ * predicted_token_cost
      EV_local = expected_reward_local - local_cost
  Choose the cheapest path that still meets confidence requirements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .horizon import HorizonEstimate, estimate_horizon, estimate_tokens_from_text


MODE_LOCAL = "local"
MODE_SHORT = "short"
MODE_MEDIUM = "medium"
MODE_DEEP = "deep"

# Default budgets (completion tokens) per mode.
DEFAULT_BUDGETS = {
    MODE_LOCAL: 0,
    MODE_SHORT: 512,
    MODE_MEDIUM: 2048,
    MODE_DEEP: 8192,
}

# Default λ: cost weight in reward-units per *kilotoken* of predicted spend.
# Rewards live on ~[0,1]; raw per-token λ=1e-3 made every Grok call EV-negative.
# Override with GROK_TOKEN_LAMBDA (still interpreted per kilotoken).
DEFAULT_LAMBDA = float(os.environ.get("GROK_TOKEN_LAMBDA", "0.12"))

# Confidence: require at least this conf that the mode can solve the task.
DEFAULT_MIN_CONFIDENCE = float(os.environ.get("GROK_TOKEN_MIN_CONF", "0.55"))


@dataclass
class TaskAnnotation:
    task: str
    horizon: HorizonEstimate
    predicted_prompt_tokens: int
    tags: List[str] = field(default_factory=list)
    context_chars: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["horizon"] = self.horizon.to_dict()
        return d


@dataclass
class RouteDecision:
    mode: str
    budget_tokens: int
    predicted_horizon: int
    expected_reward: float
    predicted_cost: float
    expected_value: float
    local_expected_value: float
    escalate: bool
    confidence: float
    reasons: List[str]
    packing: Dict[str, Any]
    annotation: TaskAnnotation

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["annotation"] = self.annotation.to_dict()
        return d


def _tag_task(task: str) -> List[str]:
    t = task.lower()
    tags: List[str] = []
    if any(
        k in t
        for k in (
            "status",
            "doctor",
            "list",
            "help",
            "version",
            "policy",
            "kpi",
            "stats",
            "layout",
            "audit --stats",
            "savings",
        )
    ):
        tags.append("ops_local")
    if any(k in t for k in ("implement", "build", "fix", "refactor", "design")):
        tags.append("build")
    if any(k in t for k in ("debug", "investigate", "root cause")):
        tags.append("debug")
    if any(k in t for k in ("review", "audit")):
        tags.append("review")
    if any(k in t for k in ("quick", "trivial", "typo", "rename")):
        tags.append("cheap")
    if any(k in t for k in ("workflow", "subagent", "multi-agent", "parallel")):
        tags.append("agentic")
    return tags or ["general"]


def annotate_task(task: str, context_chars: int = 0) -> TaskAnnotation:
    horizon = estimate_horizon(task, context_chars=context_chars)
    return TaskAnnotation(
        task=task.strip(),
        horizon=horizon,
        predicted_prompt_tokens=horizon.prompt_tokens_est,
        tags=_tag_task(task),
        context_chars=context_chars,
    )


def _reward_for_mode(mode: str, tags: List[str], horizon: int) -> float:
    """
    Expected task success reward in arbitrary units [0, 1+].
    Deep reasoning pays off more on hard tags; local is enough for ops.
    """
    base = {
        MODE_LOCAL: 0.35,
        MODE_SHORT: 0.55,
        MODE_MEDIUM: 0.78,
        MODE_DEEP: 0.92,
    }[mode]

    if "ops_local" in tags or "cheap" in tags:
        # Local/short almost always enough.
        if mode == MODE_LOCAL:
            return 0.95
        if mode == MODE_SHORT:
            return 0.97
        return 0.98  # diminishing returns for overkill

    if "agentic" in tags or "debug" in tags or horizon >= 2500:
        if mode == MODE_DEEP:
            return 0.95
        if mode == MODE_MEDIUM:
            return 0.80
        if mode == MODE_SHORT:
            return 0.50
        return 0.20

    if "build" in tags or "review" in tags:
        if mode == MODE_DEEP:
            return 0.90
        if mode == MODE_MEDIUM:
            return 0.85
        if mode == MODE_SHORT:
            return 0.60
        return 0.25

    return base


def expected_value(
    mode: str,
    tags: List[str],
    horizon: int,
    lam: float = DEFAULT_LAMBDA,
) -> Dict[str, float]:
    reward = _reward_for_mode(mode, tags, horizon)
    budget = DEFAULT_BUDGETS[mode]
    # Cost uses min(budget, horizon) as predicted spend, priced per kilotoken.
    spend = 0 if mode == MODE_LOCAL else min(budget, max(horizon, 64))
    cost = lam * (float(spend) / 1000.0)
    return {
        "reward": reward,
        "cost": cost,
        "ev": reward - cost,
        "spend_tokens": float(spend),
    }


def _role_budgets(max_context: int, n_subagents: int) -> Dict[str, int]:
    """L2 per-role budget shares under L1 max_context envelope (RCR-style)."""
    if max_context <= 0 or n_subagents <= 0:
        return {"main": max(0, max_context)}
    # Rough shares: planner/implementer heavier than validator
    shares = {
        "planner": 0.28,
        "implementer": 0.30,
        "searcher": 0.18,
        "validator": 0.14,
        "main": 0.10,
    }
    return {k: max(64, int(max_context * v)) for k, v in shares.items()}


def _pack_mode() -> str:
    """balanced (default) | aggressive (100× program) | legacy (alias balanced)."""
    m = os.environ.get("GROK_TOKEN_PACK", "balanced").lower()
    if m in ("legacy", "default"):
        return "balanced"
    if m in ("aggressive", "100x", "tight"):
        return "aggressive"
    return "balanced"


def _packing_plan(mode: str, horizon: int, context_chars: int) -> Dict[str, Any]:
    """Govern prompt packing / retrieval sizing relative to budget."""
    budget = DEFAULT_BUDGETS[mode]
    aggressive = _pack_mode() == "aggressive"
    if mode == MODE_LOCAL:
        return {
            "max_context_tokens": 0,
            "retrieval_k": 0,
            "subagents": 0,
            "continuation": False,
            "strategy": "no_model_call",
            "role_budgets": {},
            "context_routing": "none",
            "pack_profile": _pack_mode(),
        }
    # Reserve ~40% of total budget for completion; rest for packed context.
    ctx_budget = int(budget * 1.5)  # allow larger context than completion
    if mode == MODE_SHORT:
        max_ctx = min(512 if aggressive else 1500, ctx_budget)
        n_sub = 0
        return {
            "max_context_tokens": max_ctx,
            "retrieval_k": 1 if aggressive else 2,
            "subagents": n_sub,
            "continuation": False,
            "strategy": "aggressive_tight" if aggressive else "tight_pack",
            "role_budgets": _role_budgets(max_ctx, 0),
            "context_routing": "single_node",
            "pack_profile": _pack_mode(),
        }
    if mode == MODE_MEDIUM:
        max_ctx = min(2048 if aggressive else 6000, max(ctx_budget, 2000 if not aggressive else 512))
        if aggressive:
            max_ctx = min(2048, max(ctx_budget, 512))
        n_sub = 0 if aggressive else (1 if horizon > 1500 else 0)
        if not aggressive and horizon > 1500:
            n_sub = 1
        return {
            "max_context_tokens": max_ctx,
            "retrieval_k": 3 if aggressive else 6,
            "subagents": n_sub,
            "continuation": (not aggressive) and horizon > budget * 0.8,
            "strategy": "aggressive_balanced" if aggressive else "balanced_pack",
            "role_budgets": _role_budgets(max_ctx, max(1, n_sub) if n_sub else 0),
            "context_routing": "role_aware" if n_sub else "single_node",
            "pack_profile": _pack_mode(),
        }
    max_ctx = min(8192 if aggressive else 24000, max(ctx_budget, 8000 if not aggressive else 2048))
    if aggressive:
        # 100× program: hard cap context + no auto subagent fan-out on deep
        max_ctx = min(2048, max(ctx_budget, 512))
    n_sub = 0 if aggressive else (2 if horizon > 3000 else 1)
    return {
        "max_context_tokens": max_ctx,
        "retrieval_k": 6 if aggressive else 12,
        "subagents": n_sub,
        "continuation": True,
        "strategy": "aggressive_deep" if aggressive else "deep_selective_evidence",
        "role_budgets": _role_budgets(max_ctx, n_sub),
        "context_routing": "role_aware",
        "pack_profile": _pack_mode(),
    }


def route_task(
    task: str,
    context_chars: int = 0,
    lam: Optional[float] = None,
    min_confidence: Optional[float] = None,
    force_mode: Optional[str] = None,
) -> RouteDecision:
    """
    Choose local | short | medium | deep by EV = reward - λ·tokens.
    Escalation only when it beats local baseline and meets confidence.
    """
    lam = DEFAULT_LAMBDA if lam is None else float(lam)
    min_confidence = DEFAULT_MIN_CONFIDENCE if min_confidence is None else float(min_confidence)
    ann = annotate_task(task, context_chars=context_chars)
    h = ann.horizon.predicted_tokens
    tags = ann.tags
    conf = ann.horizon.confidence

    if force_mode:
        mode = force_mode
        ev = expected_value(mode, tags, h, lam=lam)
        local = expected_value(MODE_LOCAL, tags, h, lam=lam)
        return RouteDecision(
            mode=mode,
            budget_tokens=DEFAULT_BUDGETS[mode],
            predicted_horizon=h,
            expected_reward=ev["reward"],
            predicted_cost=ev["cost"],
            expected_value=ev["ev"],
            local_expected_value=local["ev"],
            escalate=mode != MODE_LOCAL,
            confidence=conf,
            reasons=[f"forced mode={mode}"],
            packing=_packing_plan(mode, h, context_chars),
            annotation=ann,
        )

    candidates = [MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP]
    scored: List[tuple] = []
    for mode in candidates:
        ev = expected_value(mode, tags, h, lam=lam)
        scored.append((mode, ev))

    local_ev = next(ev for m, ev in scored if m == MODE_LOCAL)
    reasons: List[str] = [
        f"horizon={h} method={ann.horizon.method} conf={conf}",
        f"tags={tags}",
        f"lambda={lam}",
        f"local_ev={local_ev['ev']:.4f}",
    ]

    # Filter modes that meet confidence (local always allowed).
    viable = []
    for mode, ev in scored:
        if mode == MODE_LOCAL:
            viable.append((mode, ev))
            continue
        # Soft: low conf still allows short; medium/deep need conf gate.
        if mode == MODE_SHORT and conf >= min_confidence * 0.7:
            viable.append((mode, ev))
        elif mode in (MODE_MEDIUM, MODE_DEEP) and conf >= min_confidence:
            viable.append((mode, ev))
        elif conf < min_confidence and mode == MODE_SHORT:
            viable.append((mode, ev))
            reasons.append(f"low conf {conf}: cap at short/local")

    if not viable:
        viable = [(MODE_LOCAL, local_ev)]

    # Max EV; ties prefer cheaper (lower spend).
    viable.sort(key=lambda x: (-x[1]["ev"], x[1]["spend_tokens"]))
    best_mode, best_ev = viable[0]

    # Escalation must beat local by a margin.
    margin = float(os.environ.get("GROK_TOKEN_ESCALATE_MARGIN", "0.02"))
    if best_mode != MODE_LOCAL and best_ev["ev"] < local_ev["ev"] + margin:
        reasons.append(
            f"escalation {best_mode} EV {best_ev['ev']:.4f} "
            f"< local+margin {local_ev['ev']+margin:.4f}; stay local"
        )
        best_mode, best_ev = MODE_LOCAL, local_ev

    # Hard rule: never deep for cheap/ops_local.
    if best_mode == MODE_DEEP and ("cheap" in tags or "ops_local" in tags):
        reasons.append("hard block: deep forbidden for cheap/ops_local")
        best_mode = MODE_SHORT if "ops_local" not in tags else MODE_LOCAL
        best_ev = expected_value(best_mode, tags, h, lam=lam)

    # 100× program: ops_local + small horizon → force local (no model tokens).
    if "ops_local" in tags and h < 400 and best_mode != MODE_LOCAL:
        reasons.append(
            f"hard block: ops_local horizon={h}<400 → local (token savings)"
        )
        best_mode = MODE_LOCAL
        best_ev = expected_value(best_mode, tags, h, lam=lam)

    reasons.append(f"selected={best_mode} ev={best_ev['ev']:.4f} reward={best_ev['reward']:.3f} cost={best_ev['cost']:.4f}")

    return RouteDecision(
        mode=best_mode,
        budget_tokens=DEFAULT_BUDGETS[best_mode],
        predicted_horizon=h,
        expected_reward=best_ev["reward"],
        predicted_cost=best_ev["cost"],
        expected_value=best_ev["ev"],
        local_expected_value=local_ev["ev"],
        escalate=best_mode != MODE_LOCAL,
        confidence=conf,
        reasons=reasons,
        packing=_packing_plan(best_mode, h, context_chars),
        annotation=ann,
    )

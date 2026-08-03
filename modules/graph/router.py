"""
RCR-style context router: score → greedy fill under B_i → pass|summarize|drop.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from .allocator import allocate_budget
from .scorer import score_item, estimate_tokens
from .breaker import apply_to_policy, apply_bundle, tick as breaker_tick


@dataclass
class SliceDecision:
    id: str
    action: str  # pass | summarize | drop
    alpha: float
    tokens: int
    tokens_after: int
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RouteResult:
    role: str
    stage: str
    budget: int
    policy: str  # full | budgeted | role_aware
    selected: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[SliceDecision] = field(default_factory=list)
    tokens_passed: int = 0
    tokens_summarized: int = 0
    tokens_dropped: int = 0
    n_passed: int = 0
    n_summarized: int = 0
    n_dropped: int = 0
    breaker_state: str = "closed"
    fail_fast: bool = False
    mode_cap: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["decisions"] = [x.to_dict() if hasattr(x, "to_dict") else x for x in self.decisions]
        return d


def _summarize_text(text: str, max_tokens: int) -> str:
    """Cheap summarize: keep first ~max_tokens*4 chars + ellipsis."""
    max_chars = max(32, max_tokens * 4)
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 20].rstrip() + "\n…[summarized]"


def route_context(
    memory: List[Dict[str, Any]],
    role: str,
    stage: str = "default",
    *,
    budget: Optional[int] = None,
    parent_context_budget: Optional[int] = None,
    policy: str = "role_aware",
    summarize_ratio: float = 0.35,
) -> RouteResult:
    """
    Select context under budget.

    policies:
      full       — all items, ignore budget (baseline A)
      budgeted   — greedy by recency/ts only (baseline B)
      role_aware — three-gate α sort + budget (baseline C)
    """
    policy = (policy or "role_aware").lower()
    # Advance Open→Half-Open timers; apply bundle (DEGRADED/Open) — PR3
    try:
        breaker_tick(None)
    except Exception:
        pass
    if budget is None:
        budget = allocate_budget(
            role, parent_context_budget=parent_context_budget, stage=stage
        )
    bundle = apply_bundle(role, policy=policy, budget=float(budget))
    policy = apply_to_policy(role, policy)
    # prefer bundle policy when constrained
    if bundle.get("state") and bundle["state"] != "closed":
        policy = str(bundle.get("policy") or policy)
    if bundle.get("budget") is not None:
        budget = int(bundle["budget"])
    else:
        budget = int(budget)
    breaker_state = str(bundle.get("state") or "closed")
    fail_fast = bool(bundle.get("fail_fast"))
    mode_cap = bundle.get("mode_cap")

    if fail_fast:
        return RouteResult(
            role=role,
            stage=stage,
            budget=0,
            policy=policy,
            selected=[],
            decisions=[],
            tokens_passed=0,
            n_passed=0,
            breaker_state=breaker_state,
            fail_fast=True,
            mode_cap=mode_cap,
        )

    items = list(memory or [])
    # normalize ids / tokens
    for i, m in enumerate(items):
        if not m.get("id"):
            m["id"] = f"m{i}"
        m["_tokens"] = estimate_tokens(m)

    if policy == "full":
        decisions = []
        total = 0
        selected = []
        for m in items:
            tok = m["_tokens"]
            decisions.append(
                SliceDecision(
                    id=str(m["id"]),
                    action="pass",
                    alpha=1.0,
                    tokens=tok,
                    tokens_after=tok,
                    reason="full_context",
                )
            )
            selected.append({**m, "action": "pass"})
            total += tok
        return RouteResult(
            role=role,
            stage=stage,
            budget=budget,
            policy="full",
            selected=selected,
            decisions=decisions,
            tokens_passed=total,
            n_passed=len(selected),
            breaker_state=breaker_state,
            fail_fast=False,
            mode_cap=mode_cap,
        )

    # score
    scored = []
    for m in items:
        if policy == "budgeted":
            # recency-only: use ts or importance
            alpha = score_item(m, role="default", stage="default", w_role=0.0, w_stage=0.0, w_recency=1.0)
        else:
            alpha = score_item(m, role, stage)
        scored.append((alpha, m))
    scored.sort(key=lambda x: (-x[0], -(float(x[1].get("ts") or 0))))

    used = 0
    decisions: List[SliceDecision] = []
    selected: List[Dict[str, Any]] = []
    tokens_passed = tokens_sum = tokens_drop = 0
    n_pass = n_sum = n_drop = 0

    for alpha, m in scored:
        tok = m["_tokens"]
        mid = str(m["id"])
        if used + tok <= budget:
            decisions.append(
                SliceDecision(
                    id=mid,
                    action="pass",
                    alpha=alpha,
                    tokens=tok,
                    tokens_after=tok,
                    reason="within_budget",
                )
            )
            out = {k: v for k, v in m.items() if not k.startswith("_")}
            out["action"] = "pass"
            out["alpha"] = alpha
            selected.append(out)
            used += tok
            tokens_passed += tok
            n_pass += 1
            continue
        # try summarize into remaining
        remain = budget - used
        sum_cap = max(16, int(tok * summarize_ratio))
        if remain >= 16 and sum_cap <= remain and tok > remain:
            take = min(remain, sum_cap)
            text = str(m.get("text") or m.get("content") or "")
            summarized = _summarize_text(text, take)
            decisions.append(
                SliceDecision(
                    id=mid,
                    action="summarize",
                    alpha=alpha,
                    tokens=tok,
                    tokens_after=take,
                    reason="budget_pressure",
                )
            )
            out = {k: v for k, v in m.items() if not k.startswith("_")}
            out["action"] = "summarize"
            out["alpha"] = alpha
            out["text"] = summarized
            out["tokens"] = take
            selected.append(out)
            used += take
            tokens_sum += take
            n_sum += 1
        else:
            decisions.append(
                SliceDecision(
                    id=mid,
                    action="drop",
                    alpha=alpha,
                    tokens=tok,
                    tokens_after=0,
                    reason="over_budget",
                )
            )
            tokens_drop += tok
            n_drop += 1

    return RouteResult(
        role=role,
        stage=stage,
        budget=budget,
        policy=policy if policy in ("budgeted", "role_aware") else "role_aware",
        selected=selected,
        decisions=decisions,
        tokens_passed=tokens_passed,
        tokens_summarized=tokens_sum,
        tokens_dropped=tokens_drop,
        n_passed=n_pass,
        n_summarized=n_sum,
        n_dropped=n_drop,
        breaker_state=breaker_state,
        fail_fast=False,
        mode_cap=mode_cap,
    )


def ablate(
    memory: List[Dict[str, Any]],
    role: str,
    stage: str = "default",
    *,
    budget: Optional[int] = None,
    parent_context_budget: Optional[int] = None,
) -> Dict[str, Any]:
    """Run full vs budgeted vs role_aware; return comparison table."""
    if budget is None:
        budget = allocate_budget(
            role, parent_context_budget=parent_context_budget, stage=stage
        )
    arms = {}
    for pol in ("full", "budgeted", "role_aware"):
        r = route_context(
            memory,
            role,
            stage,
            budget=budget,
            parent_context_budget=parent_context_budget,
            policy=pol,
        )
        carried = r.tokens_passed + r.tokens_summarized
        arms[pol] = {
            "budget": r.budget,
            "tokens_carried": carried,
            "tokens_dropped": r.tokens_dropped,
            "n_passed": r.n_passed,
            "n_summarized": r.n_summarized,
            "n_dropped": r.n_dropped,
            "vs_full_save_frac": None,
        }
    full_t = arms["full"]["tokens_carried"] or 1
    for pol in ("budgeted", "role_aware"):
        arms[pol]["vs_full_save_frac"] = max(
            0.0, 1.0 - (arms[pol]["tokens_carried"] / full_t)
        )
    return {
        "role": role,
        "stage": stage,
        "budget": budget,
        "arms": arms,
        "north_star_note": "pair with task success → cost_per_success",
    }

"""Per-node token budget: B_i = β_base + β_role(R_i)."""

from __future__ import annotations

import os
from typing import Dict, Optional

# Role offsets (tokens) — planners need more structure; validators less.
ROLE_BETA: Dict[str, int] = {
    "planner": 800,
    "searcher": 600,
    "implementer": 700,
    "executor": 400,
    "validator": 350,
    "reviewer": 500,
    "recoverer": 400,
    "summarizer": 300,
    "main": 500,
    "default": 400,
}


def allocate_budget(
    role: str,
    *,
    parent_context_budget: Optional[int] = None,
    base: Optional[int] = None,
    stage: str = "",
) -> int:
    """
    Allocate per-agent token budget for context carriage.

    parent_context_budget: max_context_tokens from L1 packing plan (envelope).
    """
    beta_base = base if base is not None else int(
        os.environ.get("GROK_GRAPH_BETA_BASE", "512")
    )
    role_key = (role or "default").lower().strip()
    beta_role = ROLE_BETA.get(role_key, ROLE_BETA["default"])
    b = beta_base + beta_role
    # Stage nudge: plan/recover often need more; execute/validate less
    st = (stage or "").lower()
    if st in ("plan", "design", "architecture"):
        b = int(b * 1.15)
    elif st in ("validate", "test", "ship"):
        b = int(b * 0.9)
    if parent_context_budget is not None and parent_context_budget > 0:
        # Never exceed parent envelope share (cap at 80% of parent for one node)
        b = min(b, max(128, int(parent_context_budget * 0.8)))
    return max(64, int(b))

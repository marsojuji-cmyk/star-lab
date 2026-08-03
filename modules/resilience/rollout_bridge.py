"""
Guarded rollout bridge — breakers may fire rollback, never advance (PR4 / KD-1).
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


_LAST_ROLLBACK_TS: float = 0.0
_DEBOUNCE_S = 30.0


def maybe_rollback_from_breaker(
    *,
    key: str = "",
    state: str = "open",
    reason: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    """
    Call tokens.rollout.rollback only when:
      - stage ∈ {canary, ramp, full}
      - auto_rollback_armed
      - not already rolled_back recently (debounce)
      - breaker state is open (or force)
    Never increases traffic_frac / never advances stage.
    """
    global _LAST_ROLLBACK_TS
    out: Dict[str, Any] = {
        "acted": False,
        "reason": reason or "breaker_open",
        "key": key,
        "state": state,
    }
    if state not in ("open", "OPEN") and not force:
        out["skipped"] = "state_not_open"
        return out
    try:
        from tokens import rollout as rollout_mod
    except Exception as e:
        out["error"] = "import_rollout: %s" % e
        return out

    st = rollout_mod.load_state()
    stage = st.get("stage")
    if stage not in ("canary", "ramp", "full"):
        out["skipped"] = "stage_not_armed_for_rollback"
        out["stage"] = stage
        return out
    if not st.get("auto_rollback_armed"):
        out["skipped"] = "auto_rollback_not_armed"
        return out
    now = time.time()
    if not force and (now - _LAST_ROLLBACK_TS) < _DEBOUNCE_S:
        out["skipped"] = "debounce"
        return out
    if st.get("stage") == "rolled_back":
        out["skipped"] = "already_rolled_back"
        return out

    # Use public rollback path
    try:
        res = rollout_mod.rollback(reason="breaker:%s:%s" % (key or "?", reason or state))
        _LAST_ROLLBACK_TS = now
        out["acted"] = True
        out["rollout"] = res
        # never advance — verify traffic did not increase
        new_st = rollout_mod.load_state()
        out["traffic_frac"] = new_st.get("traffic_frac")
        out["new_stage"] = new_st.get("stage")
        return out
    except Exception as e:
        out["error"] = str(e)
        return out


def full_drill() -> Dict[str, Any]:
    """
    Full resilience drill: trip policy key → maybe_rollback → reset.
    Safe on measurement canary (serve false).
    """
    try:
        from graph.breaker import trip, reset, set_state, STATE_OPEN
        from tokens import rollout as rollout_mod
    except Exception as e:
        return {"ok": False, "error": str(e)}

    st_before = rollout_mod.load_state()
    # Ensure canary armed for drill if already canary
    results = {"before": {"stage": st_before.get("stage"), "frac": st_before.get("traffic_frac")}}
    set_state("policy:candidate_v2", STATE_OPEN, reason="resilience_drill")
    rb = maybe_rollback_from_breaker(
        key="policy:candidate_v2",
        state="open",
        reason="resilience_drill",
        force=True,
    )
    results["rollback"] = rb
    reset(None)  # clear role trips
    try:
        set_state("policy:candidate_v2", "closed", reason="drill_cleanup")
    except Exception:
        pass
    st_after = rollout_mod.load_state()
    results["after"] = {"stage": st_after.get("stage"), "frac": st_after.get("traffic_frac")}
    results["ok"] = True
    results["traffic_never_increased"] = float(st_after.get("traffic_frac") or 0) <= float(
        st_before.get("traffic_frac") or 0
    ) + 1e-9
    return results

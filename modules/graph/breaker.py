"""
Agentic circuit breakers for multi-agent graph roles.

FSM: Closed → DEGRADED → Open → Half-Open (classic + DEGRADED).
Compat: is_tripped / trip / reset / apply_to_policy remain; Open ≡ tripped.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# States
STATE_CLOSED = "closed"
STATE_DEGRADED = "degraded"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"

VALID_STATES = {STATE_CLOSED, STATE_DEGRADED, STATE_OPEN, STATE_HALF_OPEN}

DEFAULT_CONFIG: Dict[str, Any] = {
    "window_size": 20,
    "failure_threshold": 0.5,
    "hard_open_count": 3,
    "success_weight": 1.0,
    "reset_timeout_s": 60.0,
    "half_open_max_probes": 3,
    "half_open_success_needed": 2,
    "degraded_budget_frac": 0.5,
    "degraded_mode_cap": "short",
    "degraded_fail_threshold": 0.35,
    "cool_down_s": 5.0,
}


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def breaker_path() -> Path:
    return _lab_data() / "graph_breakers.json"


def _default_v2() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "keys": {},
        "roles": {},  # v1 mirror for dual-write
        "config": dict(DEFAULT_CONFIG),
        "updated_ts": None,
        "kill": False,
    }


def _migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    if int(data.get("schema_version") or 1) >= 2 and "keys" in data:
        # ensure defaults
        data.setdefault("config", dict(DEFAULT_CONFIG))
        data.setdefault("keys", {})
        data.setdefault("roles", {})
        data.setdefault("kill", False)
        return data
    out = _default_v2()
    out["config"] = {**DEFAULT_CONFIG, **(data.get("config") or {})}
    roles = data.get("roles") or {}
    for role, entry in roles.items():
        key = "role:%s" % (role or "default").lower()
        tripped = bool(entry.get("tripped"))
        out["keys"][key] = {
            "state": STATE_OPEN if tripped else STATE_CLOSED,
            "scope": "role",
            "name": (role or "default").lower(),
            "reason": entry.get("reason") or "",
            "fallback_policy": entry.get("fallback_policy") or "budgeted",
            "opened_ts": entry.get("tripped_ts"),
            "changed_ts": entry.get("tripped_ts") or entry.get("reset_ts") or time.time(),
            "success_streak": 0,
            "probe_count": 0,
            "parent_key": None,
            "failure_weight_sum": 0.0,
            "success_weight_sum": 0.0,
            "sample_count": 0,
        }
        out["roles"][role.lower() if role else "default"] = {
            "tripped": tripped,
            "reason": entry.get("reason") or "",
            "fallback_policy": entry.get("fallback_policy") or "budgeted",
            "tripped_ts": entry.get("tripped_ts"),
            "reset_ts": entry.get("reset_ts"),
        }
    return out


def load_breakers() -> Dict[str, Any]:
    p = breaker_path()
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return _migrate_v1_to_v2(raw)
        except (json.JSONDecodeError, OSError):
            pass
    return _default_v2()


def save_breakers(data: Dict[str, Any]) -> Path:
    root = _lab_data()
    root.mkdir(parents=True, exist_ok=True)
    data = _migrate_v1_to_v2(data)
    data["updated_ts"] = time.time()
    data["schema_version"] = 2
    # dual-write roles mirror from keys
    roles: Dict[str, Any] = {}
    for key, entry in (data.get("keys") or {}).items():
        if not key.startswith("role:"):
            continue
        name = key.split(":", 1)[1]
        state = entry.get("state") or STATE_CLOSED
        roles[name] = {
            "tripped": state == STATE_OPEN,
            "reason": entry.get("reason") or "",
            "fallback_policy": entry.get("fallback_policy") or "budgeted",
            "tripped_ts": entry.get("opened_ts"),
            "reset_ts": entry.get("changed_ts") if state == STATE_CLOSED else None,
            "state": state,
        }
    data["roles"] = roles
    path = breaker_path()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _key(scope: str, name: str) -> str:
    return "%s:%s" % (scope, (name or "default").lower())


def _ensure_key(data: Dict[str, Any], key: str, *, scope: str = "role", name: str = "") -> Dict[str, Any]:
    keys = data.setdefault("keys", {})
    if key not in keys:
        if ":" in key:
            sc, nm = key.split(":", 1)
        else:
            sc, nm = scope, key
        keys[key] = {
            "state": STATE_CLOSED,
            "scope": sc,
            "name": nm,
            "reason": "",
            "fallback_policy": "budgeted",
            "opened_ts": None,
            "changed_ts": time.time(),
            "success_streak": 0,
            "probe_count": 0,
            "parent_key": None,
            "failure_weight_sum": 0.0,
            "success_weight_sum": 0.0,
            "sample_count": 0,
        }
    return keys[key]


def is_tripped(role: str) -> bool:
    """Compat: True iff role key is Open (not DEGRADED)."""
    data = load_breakers()
    if data.get("kill"):
        return True
    key = _key("role", role)
    entry = (data.get("keys") or {}).get(key)
    if entry and entry.get("state") == STATE_OPEN:
        return True
    # supervisor propagate
    for k, e in (data.get("keys") or {}).items():
        if e.get("scope") == "supervisor" and e.get("state") == STATE_OPEN:
            if e.get("propagate_fail_fast_to_children"):
                return True
    return False


def is_constrained(role: str) -> bool:
    """Open or DEGRADED or propagated supervisor fail_fast/degraded caps."""
    data = load_breakers()
    key = _key("role", role)
    entry = (data.get("keys") or {}).get(key) or {}
    st = entry.get("state")
    if st in (STATE_OPEN, STATE_DEGRADED):
        return True
    for k, e in (data.get("keys") or {}).items():
        if e.get("scope") == "supervisor" and e.get("state") in (STATE_OPEN, STATE_DEGRADED):
            return True
    return bool(data.get("kill"))


def trip(role: str, *, reason: str = "", fallback_policy: str = "budgeted") -> Dict[str, Any]:
    """Manual trip → Open (compat)."""
    data = load_breakers()
    key = _key("role", role)
    entry = _ensure_key(data, key, scope="role", name=role)
    entry["state"] = STATE_OPEN
    entry["reason"] = reason
    entry["fallback_policy"] = fallback_policy or "budgeted"
    entry["opened_ts"] = time.time()
    entry["changed_ts"] = time.time()
    entry["probe_count"] = 0
    entry["success_streak"] = 0
    save_breakers(data)
    return entry


def reset(role: Optional[str] = None) -> Dict[str, Any]:
    data = load_breakers()
    keys = data.setdefault("keys", {})
    if role:
        key = _key("role", role)
        if key in keys:
            keys[key]["state"] = STATE_CLOSED
            keys[key]["changed_ts"] = time.time()
            keys[key]["probe_count"] = 0
            keys[key]["success_streak"] = 0
            keys[key]["reason"] = ""
    else:
        for k, v in keys.items():
            v["state"] = STATE_CLOSED
            v["changed_ts"] = time.time()
            v["probe_count"] = 0
            v["success_streak"] = 0
    save_breakers(data)
    return data


def status() -> Dict[str, Any]:
    return load_breakers()


def apply_to_policy(role: str, policy: str) -> str:
    """If role Open or DEGRADED, force fallback policy (default budgeted)."""
    data = load_breakers()
    key = _key("role", role)
    entry = (data.get("keys") or {}).get(key)
    if entry and entry.get("state") in (STATE_OPEN, STATE_DEGRADED, STATE_HALF_OPEN):
        return entry.get("fallback_policy") or "budgeted"
    if data.get("kill"):
        return "budgeted"
    return policy


def apply_bundle(role: str, *, policy: str = "full", budget: Optional[float] = None) -> Dict[str, Any]:
    """
    Effective constraints for a role.
    Returns: policy, budget, mode_cap, fail_fast, state, deny_tools (advisory).
    """
    data = load_breakers()
    cfg = {**DEFAULT_CONFIG, **(data.get("config") or {})}
    key = _key("role", role)
    entry = (data.get("keys") or {}).get(key) or {"state": STATE_CLOSED}
    state = entry.get("state") or STATE_CLOSED
    if data.get("kill"):
        state = STATE_OPEN

    out: Dict[str, Any] = {
        "state": state,
        "policy": policy,
        "budget": budget,
        "mode_cap": None,
        "fail_fast": False,
        "deny_tools": [],
        "key": key,
    }
    if state == STATE_CLOSED:
        return out
    if state == STATE_DEGRADED:
        out["policy"] = entry.get("fallback_policy") or "budgeted"
        frac = float(cfg.get("degraded_budget_frac") or 0.5)
        if budget is not None:
            out["budget"] = float(budget) * frac
        out["mode_cap"] = cfg.get("degraded_mode_cap") or "short"
        return out
    if state == STATE_OPEN:
        out["policy"] = entry.get("fallback_policy") or "budgeted"
        out["fail_fast"] = True
        out["mode_cap"] = "local"
        out["budget"] = 0 if budget is not None else budget
        return out
    if state == STATE_HALF_OPEN:
        out["policy"] = entry.get("fallback_policy") or "budgeted"
        out["mode_cap"] = cfg.get("degraded_mode_cap") or "short"
        frac = float(cfg.get("degraded_budget_frac") or 0.5)
        if budget is not None:
            out["budget"] = float(budget) * frac
        return out
    return out


def record(
    key: str,
    *,
    success: bool,
    weight: float = 1.0,
    class_: str = "behavioral",
    reason: str = "",
) -> Dict[str, Any]:
    """
    Record outcome for sliding-window FSM.
    Hard class can force Open after hard_open_count.
    """
    data = load_breakers()
    cfg = {**DEFAULT_CONFIG, **(data.get("config") or {})}
    if ":" not in key:
        key = _key("role", key)
    entry = _ensure_key(data, key)
    w = abs(float(weight))
    entry["sample_count"] = int(entry.get("sample_count") or 0) + 1
    if success:
        entry["success_weight_sum"] = float(entry.get("success_weight_sum") or 0) + w * float(
            cfg.get("success_weight") or 1.0
        )
        entry["success_streak"] = int(entry.get("success_streak") or 0) + 1
    else:
        entry["failure_weight_sum"] = float(entry.get("failure_weight_sum") or 0) + w
        entry["success_streak"] = 0
        if class_ == "hard":
            entry["hard_count"] = int(entry.get("hard_count") or 0) + 1

    # optional events DB
    try:
        from resilience.events import append_event

        append_event(key, success=success, weight=w, class_=class_, reason=reason)
    except Exception:
        pass

    state = entry.get("state") or STATE_CLOSED
    now = time.time()

    # Half-open probe accounting
    if state == STATE_HALF_OPEN:
        entry["probe_count"] = int(entry.get("probe_count") or 0) + 1
        if success:
            if int(entry.get("success_streak") or 0) >= int(cfg.get("half_open_success_needed") or 2):
                entry["state"] = STATE_CLOSED
                entry["changed_ts"] = now
                entry["probe_count"] = 0
                entry["reason"] = "half_open healed"
        else:
            entry["state"] = STATE_OPEN
            entry["opened_ts"] = now
            entry["changed_ts"] = now
            entry["reason"] = reason or "half_open probe failed"
        save_breakers(data)
        return entry

    # Hard burst → Open
    if int(entry.get("hard_count") or 0) >= int(cfg.get("hard_open_count") or 3):
        entry["state"] = STATE_OPEN
        entry["opened_ts"] = now
        entry["changed_ts"] = now
        entry["reason"] = reason or "hard_open_count"
        save_breakers(data)
        _maybe_bridge_rollback(key, entry)
        return entry

    # Window ratio
    fail = float(entry.get("failure_weight_sum") or 0)
    succ = float(entry.get("success_weight_sum") or 0)
    total = fail + succ
    window = int(cfg.get("window_size") or 20)
    if total >= max(3, window * 0.25):
        # decay-ish: keep last window magnitude by soft clamp
        if total > window:
            scale = window / total
            entry["failure_weight_sum"] = fail * scale
            entry["success_weight_sum"] = succ * scale
            fail = float(entry["failure_weight_sum"])
            succ = float(entry["success_weight_sum"])
            total = fail + succ
        ratio = fail / total if total else 0.0
        thr_open = float(cfg.get("failure_threshold") or 0.5)
        thr_deg = float(cfg.get("degraded_fail_threshold") or 0.35)
        if ratio >= thr_open and state != STATE_OPEN:
            entry["state"] = STATE_OPEN
            entry["opened_ts"] = now
            entry["changed_ts"] = now
            entry["reason"] = reason or ("fail_ratio=%.2f" % ratio)
            save_breakers(data)
            _maybe_bridge_rollback(key, entry)
            return entry
        elif ratio >= thr_deg and state == STATE_CLOSED:
            entry["state"] = STATE_DEGRADED
            entry["changed_ts"] = now
            entry["reason"] = reason or ("degraded_ratio=%.2f" % ratio)
        elif ratio < thr_deg * 0.5 and state == STATE_DEGRADED and success:
            if int(entry.get("success_streak") or 0) >= 3:
                entry["state"] = STATE_CLOSED
                entry["changed_ts"] = now
                entry["reason"] = "degraded healed"

    save_breakers(data)
    return entry


def tick(key: Optional[str] = None) -> Dict[str, Any]:
    """Advance Open → Half-Open after reset_timeout; return status snapshot."""
    data = load_breakers()
    cfg = {**DEFAULT_CONFIG, **(data.get("config") or {})}
    timeout = float(cfg.get("reset_timeout_s") or 60.0)
    now = time.time()
    keys = data.get("keys") or {}
    targets = [key] if key else list(keys.keys())
    for k in targets:
        if not k:
            continue
        if ":" not in k:
            k = _key("role", k)
        entry = keys.get(k)
        if not entry:
            continue
        if entry.get("state") == STATE_OPEN:
            opened = float(entry.get("opened_ts") or entry.get("changed_ts") or 0)
            if opened and (now - opened) >= timeout:
                entry["state"] = STATE_HALF_OPEN
                entry["changed_ts"] = now
                entry["probe_count"] = 0
                entry["success_streak"] = 0
                entry["reason"] = "tick → half_open"
    save_breakers(data)
    return status()


def set_state(key: str, state: str, *, reason: str = "") -> Dict[str, Any]:
    if state not in VALID_STATES:
        raise ValueError("invalid state %s" % state)
    data = load_breakers()
    if ":" not in key:
        key = _key("role", key)
    entry = _ensure_key(data, key)
    entry["state"] = state
    entry["reason"] = reason
    entry["changed_ts"] = time.time()
    if state == STATE_OPEN:
        entry["opened_ts"] = time.time()
    save_breakers(data)
    if state == STATE_OPEN:
        _maybe_bridge_rollback(key, entry)
    return entry


def _maybe_bridge_rollback(key: str, entry: Dict[str, Any]) -> None:
    """PR4: policy/supervisor Open may fire guarded rollout rollback."""
    scope = (entry.get("scope") or "").lower()
    if scope not in ("policy", "supervisor") and not str(key).startswith(("policy:", "supervisor:")):
        return
    try:
        from resilience.rollout_bridge import maybe_rollback_from_breaker

        maybe_rollback_from_breaker(
            key=key,
            state=STATE_OPEN,
            reason=entry.get("reason") or "breaker_open",
        )
    except Exception:
        pass

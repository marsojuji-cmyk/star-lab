"""
Session locks for in-flight tool loops (SAAR-style continuity).

While locked, L1 routing should not freely switch modes mid-loop —
sequential prompt evolution breaks naive i.i.d. routing assumptions.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def lock_path() -> Path:
    return _lab_data() / "session_lock.json"


def get_lock() -> Optional[Dict[str, Any]]:
    p = lock_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not data.get("active"):
        return None
    return data


def acquire_lock(
    *,
    reason: str = "tool_loop",
    mode: Optional[str] = None,
    session_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    root = _lab_data()
    root.mkdir(parents=True, exist_ok=True)
    existing = get_lock()
    if existing:
        # nested: refresh ts, keep original mode
        existing["nest"] = int(existing.get("nest") or 1) + 1
        existing["updated_ts"] = time.time()
        existing["last_reason"] = reason
        lock_path().write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        return existing
    data = {
        "active": True,
        "reason": reason,
        "locked_mode": mode or os.environ.get("GROK_LOCKED_MODE"),
        "session_id": session_id or os.environ.get("GROK_SESSION_ID", ""),
        "started_ts": time.time(),
        "updated_ts": time.time(),
        "nest": 1,
        "notes": notes,
    }
    lock_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def release_lock(*, force: bool = False) -> Dict[str, Any]:
    cur = get_lock()
    if not cur:
        return {"active": False, "released": False}
    nest = int(cur.get("nest") or 1)
    if nest > 1 and not force:
        cur["nest"] = nest - 1
        cur["updated_ts"] = time.time()
        lock_path().write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
        return cur
    cur["active"] = False
    cur["nest"] = 0
    cur["released_ts"] = time.time()
    lock_path().write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
    return cur


def apply_lock_to_route(mode: str, force_mode: Optional[str] = None) -> Dict[str, Any]:
    """
    If session locked and no explicit force, pin to locked_mode when set.
    Returns {mode, locked, lock}.
    """
    lock = get_lock()
    if not lock:
        return {"mode": force_mode or mode, "locked": False, "lock": None}
    if force_mode:
        # explicit force still allowed (escape hatch) but annotated
        return {
            "mode": force_mode,
            "locked": True,
            "lock": lock,
            "override": True,
            "note": "force_mode overrides session lock",
        }
    pinned = lock.get("locked_mode")
    if pinned:
        return {
            "mode": pinned,
            "locked": True,
            "lock": lock,
            "note": "mode pinned by session lock (tool loop)",
        }
    # lock without mode: refuse escalation beyond current suggestion? soft: keep mode
    return {
        "mode": mode,
        "locked": True,
        "lock": lock,
        "note": "session lock active (no pinned mode) — prefer no mode thrash",
    }

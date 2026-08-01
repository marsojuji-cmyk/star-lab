"""
Circuit breakers for multi-agent graph roles.

One bad agent/role can be isolated without taking the whole graph down.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def breaker_path() -> Path:
    return _lab_data() / "graph_breakers.json"


def load_breakers() -> Dict[str, Any]:
    p = breaker_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"roles": {}, "updated_ts": None}


def save_breakers(data: Dict[str, Any]) -> Path:
    root = _lab_data()
    root.mkdir(parents=True, exist_ok=True)
    data["updated_ts"] = time.time()
    path = breaker_path()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def is_tripped(role: str) -> bool:
    data = load_breakers()
    entry = (data.get("roles") or {}).get((role or "").lower())
    return bool(entry and entry.get("tripped"))


def trip(role: str, *, reason: str = "", fallback_policy: str = "budgeted") -> Dict[str, Any]:
    data = load_breakers()
    roles = data.setdefault("roles", {})
    key = (role or "default").lower()
    roles[key] = {
        "tripped": True,
        "reason": reason,
        "fallback_policy": fallback_policy,
        "tripped_ts": time.time(),
    }
    save_breakers(data)
    return roles[key]


def reset(role: Optional[str] = None) -> Dict[str, Any]:
    data = load_breakers()
    roles = data.setdefault("roles", {})
    if role:
        key = role.lower()
        if key in roles:
            roles[key]["tripped"] = False
            roles[key]["reset_ts"] = time.time()
    else:
        for k, v in roles.items():
            v["tripped"] = False
            v["reset_ts"] = time.time()
    save_breakers(data)
    return data


def status() -> Dict[str, Any]:
    return load_breakers()


def apply_to_policy(role: str, policy: str) -> str:
    """If role breaker tripped, force fallback policy (default budgeted)."""
    data = load_breakers()
    entry = (data.get("roles") or {}).get((role or "").lower())
    if entry and entry.get("tripped"):
        return entry.get("fallback_policy") or "budgeted"
    return policy

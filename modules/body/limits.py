"""Body day-budget metering (charge on route, reconcile on complete)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .store import BodyStore


def _budget_path(body_id: str, store: Optional[BodyStore] = None) -> Path:
    store = store or BodyStore()
    return store.body_dir(body_id) / "budget.json"


def load_budget(body_id: str, store: Optional[BodyStore] = None) -> Dict[str, Any]:
    path = _budget_path(body_id, store)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    store = store or BodyStore()
    body = store.load(body_id)
    day_cap = int(body.limits.budget_tokens_day) if body else 100_000
    return {
        "body_id": body_id,
        "day": _day_key(),
        "charged": 0,
        "actual": 0,
        "day_cap": day_cap,
        "events": [],
    }


def save_budget(body_id: str, data: Dict[str, Any], store: Optional[BodyStore] = None) -> None:
    path = _budget_path(body_id, store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _day_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def charge(
    body_id: str,
    tokens: int,
    *,
    kind: str = "route",
    no_charge: bool = False,
    store: Optional[BodyStore] = None,
) -> Dict[str, Any]:
    """Pending charge on route (predicted). no_charge for session_boot."""
    data = load_budget(body_id, store)
    if data.get("day") != _day_key():
        data["day"] = _day_key()
        data["charged"] = 0
        data["actual"] = 0
        data["events"] = []
    if no_charge:
        data.setdefault("events", []).append(
            {"ts": time.time(), "kind": kind, "tokens": 0, "no_charge": True}
        )
        save_budget(body_id, data, store)
        return data
    data["charged"] = int(data.get("charged") or 0) + max(0, int(tokens))
    data.setdefault("events", []).append(
        {"ts": time.time(), "kind": kind, "tokens": int(tokens)}
    )
    # keep last 50 events
    data["events"] = data["events"][-50:]
    save_budget(body_id, data, store)
    return data


def reconcile(
    body_id: str,
    actual_tokens: int,
    *,
    store: Optional[BodyStore] = None,
) -> Dict[str, Any]:
    data = load_budget(body_id, store)
    if data.get("day") != _day_key():
        data["day"] = _day_key()
        data["charged"] = 0
        data["actual"] = 0
        data["events"] = []
    data["actual"] = int(data.get("actual") or 0) + max(0, int(actual_tokens))
    data.setdefault("events", []).append(
        {"ts": time.time(), "kind": "complete", "tokens": int(actual_tokens)}
    )
    data["events"] = data["events"][-50:]
    save_budget(body_id, data, store)
    return data


def remaining(body_id: str, store: Optional[BodyStore] = None) -> int:
    data = load_budget(body_id, store)
    store = store or BodyStore()
    body = store.load(body_id)
    cap = int(body.limits.budget_tokens_day) if body else int(data.get("day_cap") or 100_000)
    used = max(int(data.get("actual") or 0), int(data.get("charged") or 0))
    return max(0, cap - used)

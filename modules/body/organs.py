"""Organ bindings + in-process procedure dispatch (mind=false standing procedures)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import BodyStore

DEFAULT_BINDINGS: Dict[str, Any] = {
    "forge": {
        "module": "forge",
        "enabled": True,
        "procedures": [
            {
                "id": "on_fail_recover_once",
                "trigger": "forge_exit.nonzero",
                "action": "note_recover",
                "mind": False,
                "skip_if": "recover_already",
            },
            {
                "id": "on_fail_after_recover",
                "trigger": "forge_exit.nonzero",
                "action": "escalate_note",
                "mind": False,
            },
            {
                "id": "on_ok_close_soft",
                "trigger": "forge_exit.completed",
                "action": "note_success",
                "mind": False,
            },
        ],
    },
    "ship": {
        "module": "ship",
        "enabled": True,
        "procedures": [
            {
                "id": "on_ship_ok_note",
                "trigger": "ship_check.ok",
                "action": "note_ship",
                "mind": False,
            }
        ],
    },
    "research": {
        "module": "research",
        "enabled": True,
        "procedures": [
            {
                "id": "on_research_complete_kpi",
                "trigger": "research.complete",
                "action": "refresh_kpi_note",
                "mind": False,
            }
        ],
    },
    "tokens": {
        "module": "tokens",
        "enabled": True,
        "procedures": [
            {
                "id": "on_complete_budget",
                "trigger": "tokens.complete",
                "action": "budget_reconcile_note",
                "mind": False,
            }
        ],
    },
}


def _organs_path(body_id: str, store: BodyStore) -> Path:
    return store.body_dir(body_id) / "organs.json"


def load_bindings(body_id: str, store: Optional[BodyStore] = None) -> Dict[str, Any]:
    store = store or BodyStore()
    path = _organs_path(body_id, store)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_BINDINGS, indent=2) + "\n", encoding="utf-8")
    return dict(DEFAULT_BINDINGS)


def ensure_default_organs(body_id: str, store: Optional[BodyStore] = None) -> Dict[str, Any]:
    """Merge missing default organs/procedures into organs.json (grow standing surface)."""
    store = store or BodyStore()
    path = _organs_path(body_id, store)
    current = load_bindings(body_id, store)
    changed = False
    for name, binding in DEFAULT_BINDINGS.items():
        if name not in current:
            current[name] = json.loads(json.dumps(binding))  # deep copy via json
            changed = True
            continue
        cur_procs = {p.get("id"): p for p in (current[name].get("procedures") or [])}
        for proc in binding.get("procedures") or []:
            if proc.get("id") not in cur_procs:
                current[name].setdefault("procedures", []).append(dict(proc))
                changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


def dispatch_procedures(
    body_id: str,
    *,
    trigger: str,
    payload: Dict[str, Any],
    store: Optional[BodyStore] = None,
) -> List[Dict[str, Any]]:
    """
    Run mind=false procedures matching trigger.
    v1: log notes into events; no auto Grok spawn.
    """
    store = store or BodyStore()
    bindings = load_bindings(body_id, store)
    ran: List[Dict[str, Any]] = []

    exit_code = payload.get("exit_code")
    triggers = {trigger}
    if trigger.startswith("forge_exit") and exit_code not in (None, 0):
        triggers.add("forge_exit.nonzero")
    if trigger.startswith("forge_exit") and exit_code == 0:
        triggers.add("forge_exit.completed")

    for organ_name, binding in bindings.items():
        if not binding.get("enabled", True):
            continue
        for proc in binding.get("procedures") or []:
            if proc.get("trigger") not in triggers:
                continue
            skip_if = proc.get("skip_if")
            if skip_if and payload.get(skip_if):
                ran.append({"id": proc.get("id"), "skipped": True, "reason": skip_if})
                continue
            action = proc.get("action")
            result = {"id": proc.get("id"), "action": action, "ok": True}
            if action == "note_recover":
                result["note"] = "standing: prefer forge --recover or research recover once"
            elif action == "escalate_note":
                result["note"] = (
                    "standing: open obligation + create research packet if still red "
                    "(no auto-wake mind)"
                )
            elif action == "note_success":
                result["note"] = "standing: forge green — no mind required"
            elif action == "note_ship":
                result["note"] = "standing: ship check ok — bind showroom capture if configured"
            elif action == "refresh_kpi_note":
                result["note"] = "standing: research complete — lab research kpi is offline-safe"
            elif action == "budget_reconcile_note":
                result["note"] = "standing: tokens complete reconciles body day budget"
            else:
                result["note"] = "noop action=%s" % action
            ran.append(result)
            from .events import ingest as _ingest

            try:
                _ingest(
                    body_id,
                    channel="organ",
                    type_="dispatch",
                    payload={"procedure": proc.get("id"), "result": result},
                    dispatch=False,
                    store=store,
                )
            except Exception:
                pass
    return ran

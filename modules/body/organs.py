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
        ],
    },
    "ship": {
        "module": "ship",
        "enabled": True,
        "procedures": [],
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
    # seed defaults
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_BINDINGS, indent=2) + "\n", encoding="utf-8")
    return dict(DEFAULT_BINDINGS)


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

    # normalize forge exit trigger
    exit_code = payload.get("exit_code")
    triggers = {trigger}
    if trigger.startswith("forge_exit") and exit_code not in (None, 0):
        triggers.add("forge_exit.nonzero")

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
            else:
                result["note"] = "noop action=%s" % action
            ran.append(result)
            # append dispatch audit event without re-dispatch
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

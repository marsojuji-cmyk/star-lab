"""Contact ingest: events.jsonl + optional organ dispatch."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from .ledger import append_obligation
from .store import BodyStore


def _events_path(body_id: str, store: Optional[BodyStore] = None):
    store = store or BodyStore()
    return store.body_dir(body_id) / "events.jsonl"


def ingest(
    body_id: str,
    channel: str,
    type_: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    dispatch: bool = True,
    store: Optional[BodyStore] = None,
) -> Dict[str, Any]:
    """
    Append contact event. On forge_exit nonzero, open ledger obligation.
    Optionally dispatch standing procedures (in-process).
    """
    store = store or BodyStore()
    body = store.load(body_id)
    if not body:
        raise ValueError("unknown body_id: %s" % body_id)

    payload = dict(payload or {})
    event = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "channel": channel,
        "type": type_,
        "payload": payload,
    }
    path = _events_path(body_id, store)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")

    exit_code = payload.get("exit_code")
    if channel == "forge_exit" and exit_code not in (None, 0):
        append_obligation(
            body_id,
            kind="forge_fail",
            summary="forge exit_code=%s exp=%s"
            % (exit_code, payload.get("exp") or payload.get("exp_name") or "?"),
            payload=payload,
            store=store,
        )

    if dispatch:
        try:
            from .organs import dispatch_procedures

            dispatch_procedures(body_id, trigger="%s.%s" % (channel, type_), payload=payload, store=store)
        except Exception:
            pass

    return event


def list_events(
    body_id: str,
    *,
    limit: int = 20,
    store: Optional[BodyStore] = None,
) -> List[Dict[str, Any]]:
    path = _events_path(body_id, store)
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows[-limit:]))

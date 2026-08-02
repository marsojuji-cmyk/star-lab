"""Body obligations ledger (JSONL)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import BodyStore


def _ledger_path(body_id: str, store: Optional[BodyStore] = None) -> Path:
    store = store or BodyStore()
    return store.body_dir(body_id) / "ledger.jsonl"


def append_obligation(
    body_id: str,
    *,
    kind: str,
    summary: str,
    status: str = "open",
    payload: Optional[Dict[str, Any]] = None,
    store: Optional[BodyStore] = None,
) -> Dict[str, Any]:
    store = store or BodyStore()
    path = _ledger_path(body_id, store)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "kind": kind,
        "summary": summary,
        "status": status,
        "payload": payload or {},
        "outcome": None,
        "closed_ts": None,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def list_obligations(
    body_id: str,
    *,
    status: Optional[str] = None,
    limit: int = 50,
    store: Optional[BodyStore] = None,
) -> List[Dict[str, Any]]:
    path = _ledger_path(body_id, store)
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
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return list(reversed(rows[-limit:]))


def close_obligation(
    body_id: str,
    obl_id: str,
    *,
    outcome: str,
    store: Optional[BodyStore] = None,
) -> bool:
    """Rewrite ledger with closed status for matching id. Returns True if found."""
    store = store or BodyStore()
    path = _ledger_path(body_id, store)
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    out_lines = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        if row.get("id") == obl_id:
            row["status"] = "closed"
            row["outcome"] = outcome
            row["closed_ts"] = time.time()
            found = True
        out_lines.append(json.dumps(row))
    if found:
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return found

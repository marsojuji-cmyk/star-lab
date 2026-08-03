"""Per-body tokens/success and waste-kill signals (post-30×)."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import BodyStore
from .limits import load_budget, remaining
from .ledger import list_obligations
from .events import list_events


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def _project_key(body) -> str:
    return (body.project_key() or body.name or "").lower()


def body_kpis(body_id: str, store: Optional[BodyStore] = None) -> Dict[str, Any]:
    """
    Aggregate property-side signals for one body:
    forge exits, open obligations, day budget, token audits matching project, waste modes.
    """
    store = store or BodyStore()
    body = store.load(body_id)
    if not body:
        return {"error": "unknown body", "body_id": body_id}

    pk = _project_key(body)
    events = list_events(body_id, limit=200, store=store)
    forge_ok = sum(
        1
        for e in events
        if e.get("channel") == "forge_exit" and (e.get("payload") or {}).get("exit_code") == 0
    )
    forge_fail = sum(
        1
        for e in events
        if e.get("channel") == "forge_exit" and (e.get("payload") or {}).get("exit_code") not in (None, 0)
    )
    open_obl = list_obligations(body_id, status="open", store=store)
    bud = load_budget(body_id, store)
    rem = remaining(body_id, store)

    # Token audits: match project name / body id in task or notes
    audit_rows: List[Dict[str, Any]] = []
    try:
        from tokens.audit import AuditStore

        for r in AuditStore().recent(limit=300):
            blob = ((r.get("task") or "") + " " + (r.get("notes") or "")).lower()
            if pk and pk in blob:
                audit_rows.append(r)
            elif body_id.lower() in blob:
                audit_rows.append(r)
    except Exception:
        pass

    completed = [
        r
        for r in audit_rows
        if r.get("actual_tokens") is not None or r.get("success") is not None
    ]
    successes = [r for r in completed if r.get("success") in (1, True, "yes")]
    tokens_ok = [
        int(r["actual_tokens"])
        for r in successes
        if r.get("actual_tokens") is not None
    ]
    avg_tok = (sum(tokens_ok) / len(tokens_ok)) if tokens_ok else None

    by_mode: Dict[str, int] = defaultdict(int)
    deep_waste = 0  # deep mode with high quality ops-like tasks
    for r in completed:
        mode = str(r.get("mode") or "?")
        by_mode[mode] += 1
        task = (r.get("task") or "").lower()
        if mode == "deep" and any(k in task for k in ("status", "doctor", "typo", "list", "help")):
            deep_waste += 1

    # Research logs matching repo
    research_n = 0
    research_ok = 0
    try:
        from research.logstore import ResearchLog

        for r in ResearchLog().list(limit=100):
            repo = (r.get("repo") or r.get("project") or "").lower()
            if pk and (pk in repo or pk in (r.get("task") or "").lower()):
                research_n += 1
                if r.get("status") == "completed" and (r.get("outcome") or {}).get("success"):
                    research_ok += 1
    except Exception:
        pass

    return {
        "body_id": body_id,
        "kind": body.kind,
        "project_key": pk,
        "forge": {"ok": forge_ok, "fail": forge_fail},
        "open_obligations": len(open_obl),
        "budget": {
            "day": bud.get("day"),
            "charged": bud.get("charged"),
            "actual": bud.get("actual"),
            "remaining": rem,
            "cap": body.limits.budget_tokens_day,
        },
        "tokens": {
            "n_audits_matched": len(audit_rows),
            "n_completed": len(completed),
            "n_success": len(successes),
            "avg_tokens_per_success": avg_tok,
            "by_mode": dict(by_mode),
            "deep_waste_ops_count": deep_waste,
        },
        "research": {"n": research_n, "success": research_ok},
        "ts": time.time(),
    }


def all_body_kpis(store: Optional[BodyStore] = None) -> List[Dict[str, Any]]:
    store = store or BodyStore()
    out = []
    for row in store.list():
        out.append(body_kpis(row["body_id"], store=store))
    return out


def waste_report(store: Optional[BodyStore] = None) -> Dict[str, Any]:
    """Cross-body: deep/local mix and kill-waste recommendations."""
    rows = all_body_kpis(store)
    total_deep = sum(int((r.get("tokens") or {}).get("by_mode", {}).get("deep") or 0) for r in rows)
    total_local = sum(int((r.get("tokens") or {}).get("by_mode", {}).get("local") or 0) for r in rows)
    total_short = sum(int((r.get("tokens") or {}).get("by_mode", {}).get("short") or 0) for r in rows)
    waste = sum(int((r.get("tokens") or {}).get("deep_waste_ops_count") or 0) for r in rows)
    recs = []
    if waste:
        recs.append("Kill deep on ops/status/typo tasks (seen %d times)" % waste)
    if total_deep > total_local + total_short and (total_local + total_short) > 0:
        recs.append("Deep dominates completed audits — prefer EV route + aggressive pack on factory")
    if not recs:
        recs.append("Mode mix healthy or sparse; keep ops→local and design→deep floor")
    return {
        "by_body": rows,
        "totals": {"deep": total_deep, "local": total_local, "short": total_short, "deep_waste_ops": waste},
        "recommendations": recs,
    }

"""Human outcome scorecards per body — proofs shipped, not module count."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import BodyStore
from .kpis import body_kpis


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def _showroom_hits(project_key: str) -> List[Dict[str, Any]]:
    """Scan monorepo showroom entries for project name."""
    hits = []
    try:
        from lab_paths import repo_root

        root = repo_root() / "showroom" / "entries"
    except Exception:
        root = Path.home() / "Projects" / "grok-home" / "showroom" / "entries"
    if not root.is_dir():
        return hits
    pk = (project_key or "").lower()
    for d in root.iterdir():
        if not d.is_dir():
            continue
        name = d.name.lower()
        meta_path = d / "meta.json"
        meta = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        blob = name + " " + json.dumps(meta).lower()
        if pk and pk in blob:
            hits.append({"entry": d.name, "meta": meta})
    return hits


def scorecard(body_id: str, store: Optional[BodyStore] = None) -> Dict[str, Any]:
    """
    Score a body on human-visible outcomes:
      - forge green ratio
      - research success
      - showroom proofs
      - open obligations (penalty)
      - tokens/success when known
    """
    store = store or BodyStore()
    body = store.load(body_id)
    if not body:
        return {"error": "unknown body", "body_id": body_id}

    k = body_kpis(body_id, store=store)
    pk = k.get("project_key") or body.name
    forge_ok = int((k.get("forge") or {}).get("ok") or 0)
    forge_fail = int((k.get("forge") or {}).get("fail") or 0)
    forge_n = forge_ok + forge_fail
    forge_rate = (forge_ok / forge_n) if forge_n else None

    res_n = int((k.get("research") or {}).get("n") or 0)
    res_ok = int((k.get("research") or {}).get("success") or 0)
    res_rate = (res_ok / res_n) if res_n else None

    showroom = _showroom_hits(str(pk))
    open_obl = int(k.get("open_obligations") or 0)
    avg_tok = (k.get("tokens") or {}).get("avg_tokens_per_success")

    # Score 0..100 heuristic
    score = 40.0  # base for existing
    if forge_rate is not None:
        score += 25.0 * forge_rate
    if res_rate is not None:
        score += 15.0 * res_rate
    score += min(15.0, 5.0 * len(showroom))
    score -= min(20.0, 5.0 * open_obl)
    if avg_tok is not None and avg_tok > 0:
        # reward lower tokens/success (capped)
        score += max(0.0, 10.0 - (float(avg_tok) / 2000.0))
    score = max(0.0, min(100.0, score))

    grade = "D"
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"

    return {
        "body_id": body_id,
        "name": body.name,
        "score": round(score, 1),
        "grade": grade,
        "proofs": {
            "showroom_entries": [h["entry"] for h in showroom],
            "forge_ok": forge_ok,
            "forge_fail": forge_fail,
            "research_success": res_ok,
            "research_n": res_n,
            "open_obligations": open_obl,
            "avg_tokens_per_success": avg_tok,
        },
        "north_star": "human outcomes (shipped proofs), not module count",
        "ts": time.time(),
    }


def all_scorecards(store: Optional[BodyStore] = None) -> List[Dict[str, Any]]:
    store = store or BodyStore()
    return [scorecard(r["body_id"], store=store) for r in store.list()]

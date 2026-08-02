"""Body resolution order (KD-B16)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import Body
from .store import BodyStore


def resolve_body(
    *,
    body: Optional[str] = None,
    project: Optional[str] = None,
    cwd: Optional[str] = None,
    store: Optional[BodyStore] = None,
) -> Optional[Body]:
    """
    Ordered resolution:
      1. explicit --body / body=
      2. GROK_BODY env
      3. --project / project= → project:<name>
      4. cwd basename under ~/Projects → project:<name>
      5. GROK_BODY_FALLBACK
      6. None
    """
    store = store or BodyStore()

    candidates = []
    if body:
        candidates.append(body.strip())
    env_body = (os.environ.get("GROK_BODY") or "").strip()
    if env_body:
        candidates.append(env_body)
    if project:
        p = project.strip()
        candidates.append(p if ":" in p else "project:%s" % p)

    if cwd:
        cpath = Path(cwd).expanduser().resolve()
        # match registered bodies by repo_path
        for row in store.list():
            b = store.load(row["body_id"])
            if not b:
                continue
            rp = (b.identity or {}).get("repo_path")
            if not rp:
                continue
            try:
                if Path(rp).expanduser().resolve() == cpath:
                    candidates.append(b.body_id)
            except OSError:
                pass
        # Projects/<name>
        name = cpath.name
        if name:
            candidates.append("project:%s" % name)

    fallback = (os.environ.get("GROK_BODY_FALLBACK") or "").strip()
    if fallback:
        candidates.append(fallback)

    seen = set()
    for cid in candidates:
        if not cid or cid in seen:
            continue
        seen.add(cid)
        # allow bare name → try project: then lab:
        for try_id in (cid, "project:%s" % cid, "lab:%s" % cid):
            if try_id in seen and try_id != cid:
                continue
            loaded = store.load(try_id)
            if loaded:
                return loaded
            seen.add(try_id)
    return None


def resolve_info(**kwargs: Any) -> Dict[str, Any]:
    b = resolve_body(**kwargs)
    if not b:
        return {"resolved": False, "body_id": None}
    return {
        "resolved": True,
        "body_id": b.body_id,
        "kind": b.kind,
        "name": b.name,
        "project_key": b.project_key(),
        "mode_cap": b.limits.mode_cap,
    }

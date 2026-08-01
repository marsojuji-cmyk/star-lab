#!/usr/bin/env python3
# Grok Star Lab — Showroom capture API (PR8 stub)
"""Write portfolio candidates to ~/.grok/lab/showroom/inbox/ (no publish/regen)."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# lib/ on path when imported as modules.showroom or sibling
_REPO = Path(__file__).resolve().parent.parent.parent
_LIB = _REPO / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lab_paths import ensure_lab_dirs, lab_data_root  # noqa: E402

KINDS = ("demo", "design", "ship", "asset", "experiment", "manual")


def inbox_dir() -> Path:
    """~/.grok/lab/showroom/inbox (ensured)."""
    ensure_lab_dirs()
    path = lab_data_root() / "showroom" / "inbox"
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _slug(text: str, max_len: int = 48) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-") or "capture"
    return s[:max_len].rstrip("-")


def _capture_id(title: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"{ts}-{_slug(title)}-{short}"


def capture(
    *,
    title: str,
    kind: str = "manual",
    project: Optional[str] = None,
    source: str = "manual",
    summary: str = "",
    paths: Optional[List[str]] = None,
    proof_commands: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
    capture_id: Optional[str] = None,
) -> Path:
    """
    Write one inbox JSON entry. No git operations. No publish.

    Returns path to written file under showroom/inbox/.
    """
    if not title or not str(title).strip():
        raise ValueError("title is required")

    kind_norm = (kind or "manual").strip().lower()
    if kind_norm not in KINDS:
        kind_norm = "manual"

    cid = capture_id or _capture_id(title)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    abs_paths: List[str] = []
    for p in paths or []:
        try:
            abs_paths.append(str(Path(p).expanduser().resolve()))
        except OSError:
            abs_paths.append(str(p))

    payload: Dict[str, Any] = {
        "capture_id": cid,
        "title": str(title).strip(),
        "kind": kind_norm,
        "source": source,
        "project": project,
        "summary": summary or "",
        "paths": abs_paths,
        "proof_commands": list(proof_commands or []),
        "created_at": created,
        "published": False,
    }
    if extra:
        payload["extra"] = extra

    out = inbox_dir() / f"{cid}.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    return out


def capture_ship(
    *,
    title: str,
    project: Optional[str] = None,
    summary: str = "",
    paths: Optional[List[str]] = None,
    proof_commands: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    """Convenience: capture with kind=ship, source=from-ship."""
    return capture(
        title=title,
        kind="ship",
        project=project,
        source="from-ship",
        summary=summary,
        paths=paths,
        proof_commands=proof_commands,
        extra=extra,
    )


def capture_api(**kwargs: Any) -> Path:
    """Alias used by forge/design hooks later (same as capture)."""
    return capture(**kwargs)


def list_inbox() -> List[Path]:
    d = inbox_dir()
    return sorted(d.glob("*.json"))


if __name__ == "__main__":
    # Minimal manual smoke: python3 capture.py "title"
    t = sys.argv[1] if len(sys.argv) > 1 else "manual-capture"
    p = capture(title=t, kind="manual", source="manual", summary="cli smoke")
    print(p)

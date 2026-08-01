#!/usr/bin/env python3
# Grok Star Lab — Showroom publish (inbox → curated entries)
"""Move/copy inbox item → showroom/entries/<id>/{meta.json,body.md}; regen index."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_LIB = _REPO / "lib"
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lab_paths import lab_data_root, repo_root  # noqa: E402

from capture import inbox_dir  # noqa: E402
from regen_index import entries_dir, regenerate  # noqa: E402
from secrets_gate import scan_payload  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str, max_len: int = 40) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-") or "entry"
    return s[:max_len].rstrip("-")


def to_portable_path(raw: str, repo: Optional[Path] = None) -> str:
    """
    Prefer repo-relative or ~/… portable strings over absolute /Users/….
    """
    r = (repo or repo_root()).resolve()
    try:
        p = Path(raw).expanduser()
        try:
            resolved = p.resolve()
        except OSError:
            resolved = p
    except (TypeError, ValueError):
        return str(raw)

    try:
        rel = resolved.relative_to(r)
        return str(rel).replace("\\", "/")
    except ValueError:
        pass

    home = Path.home().resolve()
    try:
        rel_h = resolved.relative_to(home)
        return ("~/" + str(rel_h)).replace("\\", "/")
    except ValueError:
        pass

    # Unresolved relative that already looks portable
    s = str(raw)
    if s.startswith("~/") or not s.startswith("/"):
        return s
    return s


def allocate_entry_id(title: str, when: Optional[str] = None, root: Optional[Path] = None) -> str:
    """Stable entry_id = slug(title)-YYYYMMDD; on collision append short hash."""
    day = (when or _utc_now())[:10].replace("-", "")
    base = "%s-%s" % (_slug(title), day)
    ed = entries_dir(root)
    if not (ed / base).exists():
        return base
    short = uuid.uuid4().hex[:6]
    candidate = "%s-%s" % (base, short)
    while (ed / candidate).exists():
        short = uuid.uuid4().hex[:6]
        candidate = "%s-%s" % (base, short)
    return candidate


def load_inbox_item(capture_id_or_path: str) -> Tuple[Path, Dict[str, Any]]:
    """
    Resolve inbox JSON by capture_id stem, full filename, or path.
    Raises FileNotFoundError / ValueError.
    """
    raw = capture_id_or_path.strip()
    p = Path(raw).expanduser()
    if p.is_file():
        path = p
    else:
        d = inbox_dir()
        # strip .json if user passed id with suffix
        stem = raw[:-5] if raw.endswith(".json") else raw
        candidates = [
            d / ("%s.json" % stem),
            d / raw,
            d / stem,
        ]
        path = next((c for c in candidates if c.is_file()), None)
        if path is None:
            # prefix match on stem
            matches = sorted(d.glob("%s*.json" % stem))
            if len(matches) == 1:
                path = matches[0]
            elif len(matches) > 1:
                raise ValueError(
                    "ambiguous capture id %r; matches: %s"
                    % (raw, ", ".join(m.name for m in matches[:5]))
                )
            else:
                raise FileNotFoundError("inbox item not found: %s" % raw)

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("inbox JSON must be an object: %s" % path)
    return path, data


def _body_from_payload(data: Dict[str, Any]) -> str:
    title = data.get("title") or "Untitled"
    summary = data.get("summary") or ""
    kind = data.get("kind") or "manual"
    project = data.get("project")
    paths = data.get("paths") or []
    proof = data.get("proof_commands") or []
    source = data.get("source") or ""
    created = data.get("created_at") or ""

    lines = [
        "# %s" % title,
        "",
        summary,
        "",
        "- **kind:** %s" % kind,
    ]
    if project:
        lines.append("- **project:** %s" % project)
    if source:
        lines.append("- **source:** %s" % source)
    if created:
        lines.append("- **captured:** %s" % created)
    lines.append("")
    if paths:
        lines.append("## Paths")
        lines.append("")
        for p in paths:
            lines.append("- `%s`" % p)
        lines.append("")
    if proof:
        lines.append("## Proof")
        lines.append("")
        lines.append("```bash")
        for c in proof:
            lines.append(str(c))
        lines.append("```")
        lines.append("")
    extra = data.get("extra")
    if extra:
        lines.append("## Extra")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(extra, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def publish_inbox_item(
    capture_id_or_path: str,
    *,
    root: Optional[Path] = None,
    keep_inbox: bool = False,
    body_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Secrets-gate + write entries/<id>/{meta.json,body.md} + mark inbox done + regen.

    Returns dict with entry_id, entry_dir, index_path.
    Raises ValueError on secrets hit or bad payload.
    """
    r = root or repo_root()
    inbox_path, data = load_inbox_item(capture_id_or_path)
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("inbox item missing title: %s" % inbox_path.name)

    body = body_override if body_override is not None else _body_from_payload(data)
    paths = [str(p) for p in (data.get("paths") or [])]
    proof = [str(c) for c in (data.get("proof_commands") or [])]
    summary = str(data.get("summary") or "")

    hits = scan_payload(
        title=title,
        summary=summary,
        body=body,
        paths=paths,
        proof_commands=proof,
        extra_text=json.dumps(data.get("extra") or {}, sort_keys=True),
    )
    if hits:
        raise ValueError(
            "secrets gate refused publish for %s:\n  - %s"
            % (inbox_path.name, "\n  - ".join(hits))
        )

    portable_paths = [to_portable_path(p, r) for p in paths]
    created = str(data.get("created_at") or _utc_now())
    published_at = _utc_now()
    entry_id = allocate_entry_id(title, created, r)

    entry_dir = entries_dir(r) / entry_id
    entry_dir.mkdir(parents=True, exist_ok=False)

    meta: Dict[str, Any] = {
        "entry_id": entry_id,
        "title": title,
        "kind": data.get("kind") or "manual",
        "project": data.get("project"),
        "summary": summary,
        "paths": portable_paths,
        "proof_commands": proof,
        "source": data.get("source") or "inbox",
        "capture_id": data.get("capture_id") or inbox_path.stem,
        "created_at": created,
        "published_at": published_at,
    }
    if data.get("extra"):
        meta["extra"] = data["extra"]

    (entry_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (entry_dir / "body.md").write_text(body, encoding="utf-8")

    # Mark inbox published or move to inbox/done/
    data["published"] = True
    data["published_at"] = published_at
    data["entry_id"] = entry_id
    if keep_inbox:
        inbox_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        done = inbox_dir() / "done"
        done.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            os.chmod(done, 0o700)
        except OSError:
            pass
        dest = done / inbox_path.name
        if dest.exists():
            dest = done / ("%s-%s" % (inbox_path.stem, uuid.uuid4().hex[:6]) + ".json")
        # rewrite then move
        inbox_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        shutil.move(str(inbox_path), str(dest))

    index_path = regenerate(r)
    return {
        "entry_id": entry_id,
        "entry_dir": entry_dir,
        "index_path": index_path,
        "meta": meta,
    }


def list_curated(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    from regen_index import load_entries

    return load_entries(root)


def write_seed_entry(
    *,
    entry_id: str,
    title: str,
    kind: str,
    summary: str,
    paths: List[str],
    proof_commands: List[str],
    body: str,
    project: Optional[str] = None,
    created_at: Optional[str] = None,
    root: Optional[Path] = None,
) -> Path:
    """Write a curated seed entry directly (no inbox). Idempotent overwrite of same id."""
    r = root or repo_root()
    ed = entries_dir(r) / entry_id
    ed.mkdir(parents=True, exist_ok=True)
    created = created_at or _utc_now()
    published = created
    meta = {
        "entry_id": entry_id,
        "title": title,
        "kind": kind,
        "project": project,
        "summary": summary,
        "paths": [to_portable_path(p, r) for p in paths],
        "proof_commands": list(proof_commands),
        "source": "seed",
        "capture_id": None,
        "created_at": created,
        "published_at": published,
    }
    (ed / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ed / "body.md").write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
    return ed

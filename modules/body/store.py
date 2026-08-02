"""Body registry on disk under ~/.grok/lab/bodies/."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import (
    Body,
    BodyLimits,
    DEFAULT_ORGANS,
    default_contact,
    fs_dir_name,
)


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def bodies_root() -> Path:
    return _lab_data() / "bodies"


class BodyStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or bodies_root()
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.index_path = self.root / "index.json"

    def _load_index(self) -> Dict[str, Any]:
        if self.index_path.is_file():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"bodies": {}, "updated_ts": None}

    def _save_index(self, idx: Dict[str, Any]) -> None:
        idx["updated_ts"] = time.time()
        self.index_path.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8")

    def body_dir(self, body_id: str) -> Path:
        return self.root / fs_dir_name(body_id)

    def path_for(self, body_id: str) -> Path:
        return self.body_dir(body_id) / "body.json"

    def exists(self, body_id: str) -> bool:
        return self.path_for(body_id).is_file()

    def load(self, body_id: str) -> Optional[Body]:
        p = self.path_for(body_id)
        if not p.is_file():
            return None
        try:
            return Body.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def save(self, body: Body) -> Path:
        d = self.body_dir(body.body_id)
        d.mkdir(parents=True, mode=0o700, exist_ok=True)
        for sub in ("skills", "packets"):
            (d / sub).mkdir(mode=0o700, exist_ok=True)
        # touch ledger/events files
        for name in ("ledger.jsonl", "events.jsonl"):
            fp = d / name
            if not fp.exists():
                fp.write_text("", encoding="utf-8")
        path = d / "body.json"
        path.write_text(json.dumps(body.to_dict(), indent=2) + "\n", encoding="utf-8")
        idx = self._load_index()
        idx.setdefault("bodies", {})[body.body_id] = {
            "kind": body.kind,
            "name": body.name,
            "dir": fs_dir_name(body.body_id),
            "project_key": body.project_key(),
        }
        self._save_index(idx)
        return path

    def list(self) -> List[Dict[str, Any]]:
        idx = self._load_index()
        out = []
        for bid, meta in (idx.get("bodies") or {}).items():
            row = dict(meta)
            row["body_id"] = bid
            out.append(row)
        return sorted(out, key=lambda r: r.get("body_id") or "")

    def init_body(
        self,
        *,
        kind: str,
        name: str,
        repo: Optional[str] = None,
        mode_cap: str = "medium",
        budget_day: int = 100_000,
        organs: Optional[List[str]] = None,
    ) -> Body:
        kind = (kind or "project").lower()
        name = (name or "").strip()
        if not name:
            raise ValueError("name required")
        body_id = "%s:%s" % (kind if kind != "system" else "system", name)
        if kind == "lab":
            body_id = "lab:%s" % name
        elif kind == "project":
            body_id = "project:%s" % name
        existing = self.load(body_id)
        if existing:
            return existing
        repo_path = repo or (
            str(Path.home() / "Projects" / name) if kind == "project" else None
        )
        body = Body(
            body_id=body_id,
            kind=kind,
            name=name,
            tenant=os.environ.get("GROK_TENANT") or "local",
            identity={
                "address": "%s://%s" % (kind, name),
                "domain": None,
                "repo_path": repo_path,
                "created_ts": time.time(),
                "description": "",
            },
            property_map={
                "project_key": name if kind == "project" else None,
                "stores": ["forge", "design", "knowledge", "showroom", "research"],
                "ledger": "ledger.jsonl",
            },
            contact=default_contact(),
            limits=BodyLimits(
                mode_cap=mode_cap,
                budget_tokens_day=budget_day,
                require_approval_for=["distill_promote", "ship_publish"],
                breaker_parent="body:%s" % body_id,
            ),
            organs=list(organs or DEFAULT_ORGANS),
            meta={"notes": ""},
        )
        self.save(body)
        return body

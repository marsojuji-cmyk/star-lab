# Python 3.9+ Design Studio library — register/list design docs.
"""SQLite WAL catalog of design markdown paths under Projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_lib = str(_REPO / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from lab_paths import PROJECTS, ensure_lab_dirs, lab_data_root  # noqa: E402

SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def get_db_path() -> Path:
    return lab_data_root() / "design.db"


def slugify(text: str, max_len: int = 64) -> str:
    s = text.strip().lower()
    s = re.sub(r"\.[a-z0-9]+$", "", s)  # drop extension if present
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-") or "design"
    return s[:max_len].rstrip("-")


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default if default is not None else []
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def infer_project(path: Path) -> Optional[str]:
    """
    If path is under PROJECTS/<name>/..., return <name>.
    Otherwise None.
    """
    try:
        resolved = path.expanduser().resolve()
        projects = Path(PROJECTS).expanduser().resolve()
    except OSError:
        return None
    try:
        rel = resolved.relative_to(projects)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return parts[0]


def canonical_design_path(project: str, slug: str, day: Optional[str] = None) -> Path:
    """~/Projects/<project>/docs/design/<YYYY-MM-DD>-<slug>.md"""
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Path(PROJECTS) / project / "docs" / "design" / f"{day}-{slug}.md"


def extract_title(path: Path) -> Optional[str]:
    """First markdown H1, else stem."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines()[:40]:
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return path.stem


class DesignStore:
    """SQLite store for design_docs under lab data root."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        ensure_lab_dirs()
        self.db_path = Path(db_path) if db_path else get_db_path()
        self.db_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        schema_path = _HERE / "schema.sql"
        with self.connect() as conn:
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            if ver < SCHEMA_VERSION:
                sql = schema_path.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
                conn.commit()

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM design_docs WHERE id = ?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_by_slug(
        self, slug: str, project: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if project is not None:
                row = conn.execute(
                    "SELECT * FROM design_docs WHERE slug = ? "
                    "AND IFNULL(project,'') = IFNULL(?, '')",
                    (slug, project),
                ).fetchone()
            else:
                rows = conn.execute(
                    "SELECT * FROM design_docs WHERE slug = ? "
                    "ORDER BY registered_at DESC LIMIT 2",
                    (slug,),
                ).fetchall()
                if len(rows) == 1:
                    return dict(rows[0])
                if len(rows) > 1:
                    return None  # ambiguous; caller should pass --project
                return None
            return dict(row) if row else None

    def find(self, key: str, project: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Lookup by id, id prefix, slug, or absolute path."""
        if not key:
            return None
        doc = self.get(key)
        if doc:
            return doc
        # path match
        try:
            p = str(Path(key).expanduser().resolve())
        except OSError:
            p = key
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM design_docs WHERE path = ? OR source_path = ?",
                (p, p),
            ).fetchone()
            if row:
                return dict(row)
            if len(key) >= 8:
                rows = conn.execute(
                    "SELECT * FROM design_docs WHERE id LIKE ? "
                    "ORDER BY registered_at DESC LIMIT 2",
                    (key + "%",),
                ).fetchall()
                if len(rows) == 1:
                    return dict(rows[0])
        return self.get_by_slug(key, project=project)

    def list_docs(
        self,
        project: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if project is not None:
                rows = conn.execute(
                    "SELECT * FROM design_docs WHERE project = ? "
                    "ORDER BY registered_at DESC LIMIT ?",
                    (project, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM design_docs ORDER BY registered_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def register(
        self,
        path: Path,
        *,
        project: Optional[str] = None,
        slug: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        notes: Optional[str] = None,
        copy_to_canonical: bool = True,
        showroom: bool = False,
    ) -> Dict[str, Any]:
        """
        Record a design doc pointer. Optionally copy into
        ~/Projects/<project>/docs/design/<YYYY-MM-DD>-<slug>.md when
        source is outside that tree.
        """
        src = path.expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError("design doc not found: %s" % src)

        proj = project or infer_project(src)
        stem_slug = slugify(slug or src.stem)
        # If filename already looks like YYYY-MM-DD-slug, prefer that slug tail
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", src.stem)
        day: Optional[str] = None
        if m and not slug:
            day = m.group(1)
            stem_slug = slugify(m.group(2))

        doc_title = title or extract_title(src) or stem_slug
        source_path = str(src)
        dest = src
        copied = False

        if copy_to_canonical and proj:
            canon = canonical_design_path(proj, stem_slug, day=day)
            try:
                same = src.resolve() == canon.resolve()
            except OSError:
                same = False
            if not same:
                canon.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
                if canon.exists():
                    # Keep existing canonical file; still re-point registry
                    dest = canon
                else:
                    shutil.copy2(str(src), str(canon))
                    try:
                        os.chmod(canon, 0o644)
                    except OSError:
                        pass
                    dest = canon
                    copied = True
            else:
                dest = canon

        # Upsert by project+slug
        existing = self.get_by_slug(stem_slug, project=proj)
        now = utc_now_iso()
        tags_json = _json_dumps(list(tags or []))
        showroom_id: Optional[str] = None

        if existing:
            doc_id = existing["id"]
            with self.connect() as conn:
                conn.execute(
                    """
                    UPDATE design_docs SET
                      title = ?, path = ?, source_path = ?,
                      tags = COALESCE(?, tags), notes = COALESCE(?, notes)
                    WHERE id = ?
                    """,
                    (
                        doc_title,
                        str(dest),
                        source_path if copied or str(dest) != source_path else existing.get(
                            "source_path"
                        )
                        or source_path,
                        tags_json if tags is not None else None,
                        notes,
                        doc_id,
                    ),
                )
                conn.commit()
        else:
            doc_id = new_id()
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO design_docs (
                      id, slug, project, title, path, source_path,
                      registered_at, showroom_capture_id, tags, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        doc_id,
                        stem_slug,
                        proj,
                        doc_title,
                        str(dest),
                        source_path if str(dest) != source_path else None,
                        now,
                        tags_json,
                        notes,
                    ),
                )
                conn.commit()

        if showroom:
            showroom_id = write_showroom_capture(
                title=doc_title,
                project=proj,
                path=str(dest),
                design_id=doc_id,
                slug=stem_slug,
            )
            with self.connect() as conn:
                conn.execute(
                    "UPDATE design_docs SET showroom_capture_id = ? WHERE id = ?",
                    (showroom_id, doc_id),
                )
                conn.commit()

        doc = self.get(doc_id)
        assert doc is not None
        doc["_copied"] = copied
        doc["_canonical"] = str(dest)
        return doc


def write_showroom_capture(
    *,
    title: str,
    project: Optional[str],
    path: str,
    design_id: str,
    slug: str,
) -> str:
    """
    Write showroom inbox entry for a design doc.
    Prefer modules/showroom/capture.py when present (PR8+); else write
    the same inbox JSON shape locally (inbox only, no publish).
    """
    # Try shared capture API first
    try:
        showroom_path = _REPO / "modules" / "showroom"
        if showroom_path.is_dir() and (showroom_path / "capture.py").is_file():
            if str(showroom_path) not in sys.path:
                sys.path.insert(0, str(showroom_path))
            import capture  # type: ignore

            if hasattr(capture, "capture"):
                out = capture.capture(
                    title=title,
                    kind="design",
                    project=project,
                    source="from-design",
                    summary="Registered design doc: %s" % slug,
                    paths=[path],
                    proof_commands=["lab design list", "lab design open %s" % design_id[:12]],
                    extra={"design_id": design_id, "slug": slug},
                )
                # capture returns Path; derive id from filename stem
                return Path(out).stem
    except Exception:
        pass

    # Fallback: write inbox JSON directly
    ensure_lab_dirs()
    inbox = lab_data_root() / "showroom" / "inbox"
    inbox.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        os.chmod(inbox, 0o700)
    except OSError:
        pass

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = "%s-%s-%s" % (ts, slugify(title, 32), uuid.uuid4().hex[:8])
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        abs_path = str(Path(path).expanduser().resolve())
    except OSError:
        abs_path = path

    payload = {
        "capture_id": cid,
        "title": title,
        "kind": "design",
        "source": "from-design",
        "project": project,
        "summary": "Registered design doc: %s" % slug,
        "paths": [abs_path],
        "proof_commands": [
            "lab design list",
            "lab design open %s" % design_id[:12],
        ],
        "created_at": created,
        "published": False,
        "extra": {"design_id": design_id, "slug": slug},
    }
    out = inbox / ("%s.json" % cid)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    return cid


def register_doc(
    path: Path,
    *,
    project: Optional[str] = None,
    slug: Optional[str] = None,
    showroom: bool = False,
    copy_to_canonical: bool = True,
) -> Dict[str, Any]:
    """Module-level convenience wrapper."""
    store = DesignStore()
    return store.register(
        path,
        project=project,
        slug=slug,
        showroom=showroom,
        copy_to_canonical=copy_to_canonical,
    )

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


def projects_root() -> Path:
    """Resolved PROJECTS root (env PROJECTS or ~/Projects)."""
    return Path(PROJECTS).expanduser().resolve()


def _is_under(path: Path, root: Path) -> bool:
    """Python 3.9-safe Path.is_relative_to equivalent."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


class ProjectNameError(ValueError):
    """Invalid --project name (absolute, path separators, or escapes PROJECTS)."""


def sanitize_project_name(project: str) -> str:
    """
    Validate project as a single path segment under PROJECTS.

    Rejects empty, absolute paths, separators, ``..``, and names that would
    resolve outside PROJECTS after join.
    """
    if project is None:
        raise ProjectNameError("project name is required")
    name = str(project).strip()
    if not name:
        raise ProjectNameError("project name is empty")
    # Absolute (POSIX /… or Windows drive) — Path join would replace base
    if Path(name).is_absolute() or name.startswith("~"):
        raise ProjectNameError(
            "project must be a name under PROJECTS, not an absolute path: %r" % name
        )
    if name in (".", ".."):
        raise ProjectNameError("invalid project name: %r" % name)
    # No multi-segment / traversal
    if os.sep in name or (os.altsep and os.altsep in name) or "/" in name or "\\" in name:
        raise ProjectNameError(
            "project must be a single path segment (no separators): %r" % name
        )
    if ".." in Path(name).parts:
        raise ProjectNameError("project must not contain '..': %r" % name)
    # Only safe single-segment names (alnum + . _ -)
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", name):
        raise ProjectNameError(
            "project name has invalid characters (use alnum, ., _, -): %r" % name
        )
    # After join, must stay under PROJECTS (defense in depth)
    root = projects_root()
    candidate = (root / name).resolve()
    if candidate == root or not _is_under(candidate, root):
        raise ProjectNameError("project escapes PROJECTS root: %r" % name)
    return name


def infer_project(path: Path) -> Optional[str]:
    """
    If path is under PROJECTS/<name>/..., return sanitized <name>.
    Otherwise None.
    """
    try:
        resolved = path.expanduser().resolve()
        projects = projects_root()
    except OSError:
        return None
    try:
        rel = resolved.relative_to(projects)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    try:
        return sanitize_project_name(parts[0])
    except ProjectNameError:
        return None


def canonical_design_path(project: str, slug: str, day: Optional[str] = None) -> Path:
    """~/Projects/<project>/docs/design/<YYYY-MM-DD>-<slug>.md (project sanitized)."""
    safe = sanitize_project_name(project)
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = projects_root()
    canon = (root / safe / "docs" / "design" / f"{day}-{slug}.md").resolve()
    # Confine under PROJECTS/<safe>/
    project_root = (root / safe).resolve()
    if not _is_under(canon, project_root):
        raise ProjectNameError("canonical path escapes project root: %s" % canon)
    return canon


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
        if limit < 0:
            raise ValueError("limit must be >= 0 (got %s)" % limit)
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

        Re-register with copy enabled overwrites an existing canonical file
        so durable docs stay truthful after source edits.
        """
        src = path.expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError("design doc not found: %s" % src)

        if project is not None:
            proj: Optional[str] = sanitize_project_name(project)
        else:
            proj = infer_project(src)

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
                # Always refresh: copy (overwrite) so re-register updates content
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

        if existing:
            doc_id = existing["id"]
            src_col = (
                source_path
                if copied or str(dest) != source_path
                else (existing.get("source_path") or source_path)
            )
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
                        src_col,
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


def _write_inbox_json(
    *,
    title: str,
    project: Optional[str],
    path: str,
    design_id: str,
    slug: str,
) -> str:
    """Local showroom inbox write (same shape as PR8 capture)."""
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
    showroom_path = _REPO / "modules" / "showroom"
    capture_py = showroom_path / "capture.py"
    if showroom_path.is_dir() and capture_py.is_file():
        try:
            if str(showroom_path) not in sys.path:
                sys.path.insert(0, str(showroom_path))
            import capture  # type: ignore
        except ImportError:
            capture = None  # type: ignore
        else:
            if hasattr(capture, "capture"):
                # Real capture failures propagate (do not double-write)
                out = capture.capture(
                    title=title,
                    kind="design",
                    project=project,
                    source="from-design",
                    summary="Registered design doc: %s" % slug,
                    paths=[path],
                    proof_commands=[
                        "lab design list",
                        "lab design open %s" % design_id[:12],
                    ],
                    extra={"design_id": design_id, "slug": slug},
                )
                return Path(out).stem

    return _write_inbox_json(
        title=title,
        project=project,
        path=path,
        design_id=design_id,
        slug=slug,
    )



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

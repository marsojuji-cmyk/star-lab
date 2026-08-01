# Python 3.9+ — Knowledge Crucible FTS indexer
"""
Collect lab-relevant markdown and rebuild SQLite FTS5 index at
~/.grok/lab/knowledge/fts.db (override via GROK_LAB_DATA).

Does not touch Grok session_search.sqlite.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

# Allow `python3 modules/knowledge/cli.py` without install
_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lab_paths import PROJECTS, grok_home, lab_data_root  # noqa: E402

# 1 MiB hard cap (design + config.toml knowledge.max_file_bytes)
MAX_FILE_BYTES = int(os.environ.get("GROK_KNOWLEDGE_MAX_BYTES", str(1 * 1024 * 1024)))

# Directory name segments never walked into
EXCLUDE_DIR_NAMES: Set[str] = {
    "node_modules",
    ".git",
    "dist",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".eggs",
}

SCHEMA_VERSION = 1


@dataclass
class IndexStats:
    """Result of a full index rebuild."""

    indexed: int = 0
    skipped: int = 0
    errors: int = 0
    sources: List[str] = field(default_factory=list)
    db_path: str = ""
    bytes_indexed: int = 0

    def summary_line(self) -> str:
        return (
            f"indexed={self.indexed} skipped={self.skipped} "
            f"errors={self.errors} bytes={self.bytes_indexed} db={self.db_path}"
        )


def fts_db_path() -> Path:
    """Canonical FTS database path under lab data root."""
    return lab_data_root() / "knowledge" / "fts.db"


def ensure_knowledge_dir() -> Path:
    """Create ~/.grok/lab/knowledge (mode 0o700) and return it."""
    root = lab_data_root() / "knowledge"
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _is_excluded_dir(name: str) -> bool:
    return name in EXCLUDE_DIR_NAMES


def _under_root(path: Path, root: Path) -> bool:
    """True if path resolves under root (blocks symlink escape)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _read_text_if_eligible(path: Path) -> Optional[Tuple[str, int]]:
    """
    Return (text, size) if file should be indexed; else None.
    Skips oversized, unreadable, and non-UTF-8/binary content.
    """
    # Index regular files only; skip symlinks (escape + noise).
    if path.is_symlink():
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None
    size = st.st_size
    if size > MAX_FILE_BYTES:
        return None
    if size == 0:
        return None
    try:
        # Reject obvious binary: NUL in first 8k
        with path.open("rb") as fh:
            head = fh.read(8192)
        if b"\x00" in head:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text, size


def _walk_md(root: Path) -> Iterable[Path]:
    """Yield .md files under root, honoring exclude dirs and no external symlinks."""
    if not root.is_dir():
        return
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        # Also drop dirs that are symlinks (do not descend)
        kept: List[str] = []
        for d in dirnames:
            p = Path(dirpath) / d
            if p.is_symlink():
                continue
            kept.append(d)
        dirnames[:] = kept

        for name in filenames:
            if not name.lower().endswith(".md"):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            if not _under_root(path, root):
                continue
            yield path


def _title_from_body(path: Path, body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.name
        if stripped:
            break
    return path.name


def collect_sources(
    project: Optional[str] = None,
    *,
    projects_root: Optional[Path] = None,
    grok: Optional[Path] = None,
    lab_data: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> List[Tuple[str, Path]]:
    """
    Return list of (source_label, file_path) pairs to consider for indexing.

    Default sources (design Knowledge Crucible):
      - memory:  ~/.grok/memory/**/*.md
      - rules:   ~/.grok/rules/**/*.md
      - agents:  ~/Projects/*/AGENTS.md (and Agents.md)
      - design:  ~/Projects/*/docs/**/*.md
      - showroom: <repo>/showroom/entries/**/*.md
      - experiments: ~/.grok/lab/experiments/**/meta.md

    With --project NAME: still indexes global memory/rules; only that
    project tree for agents/design.
    """
    gh = (grok or grok_home()).expanduser()
    proj = (projects_root or PROJECTS).expanduser()
    lab = (lab_data or lab_data_root()).expanduser()
    repo = repo_root  # optional; showroom under monorepo

    pairs: List[Tuple[str, Path]] = []

    # Global memory + rules (always)
    for label, base in (("memory", gh / "memory"), ("rules", gh / "rules")):
        if base.is_dir():
            for p in _walk_md(base):
                pairs.append((label, p))
        # Also accept a lone MEMORY.md if layout is flat
        lone = base if base.suffix == ".md" else None
        if lone and lone.is_file():
            pairs.append((label, lone))

    # Explicit MEMORY.md common path
    mem_file = gh / "memory" / "MEMORY.md"
    if mem_file.is_file() and not any(p == mem_file for _, p in pairs):
        pairs.append(("memory", mem_file))

    # Projects
    if proj.is_dir():
        if project:
            candidates = [proj / project]
        else:
            try:
                candidates = sorted(
                    [p for p in proj.iterdir() if p.is_dir() and not p.name.startswith(".")],
                    key=lambda p: p.name.lower(),
                )
            except OSError:
                candidates = []

        for project_dir in candidates:
            if not project_dir.is_dir():
                continue
            if _is_excluded_dir(project_dir.name):
                continue
            # AGENTS.md variants at project root
            for agents_name in ("AGENTS.md", "Agents.md", "AGENT.md", "Claude.md"):
                agents = project_dir / agents_name
                if agents.is_file() and not agents.is_symlink():
                    pairs.append(("agents", agents))
            # Design docs under docs/
            docs = project_dir / "docs"
            if docs.is_dir():
                for p in _walk_md(docs):
                    pairs.append(("design", p))

    # Showroom entries in monorepo (if known)
    if repo is None:
        # Walk up from this file → modules/knowledge → modules → repo
        candidate = Path(__file__).resolve().parent.parent.parent
        if (candidate / "bin").is_dir() and (candidate / "modules").is_dir():
            repo = candidate
    if repo is not None:
        showroom = Path(repo) / "showroom" / "entries"
        if showroom.is_dir():
            for p in _walk_md(showroom):
                pairs.append(("showroom", p))

    # Experiment meta notes
    exp_root = lab / "experiments"
    if exp_root.is_dir():
        for dirpath, dirnames, filenames in os.walk(exp_root, followlinks=False):
            dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
            if "meta.md" in filenames:
                meta = Path(dirpath) / "meta.md"
                if meta.is_file() and not meta.is_symlink():
                    pairs.append(("experiments", meta))

    # Deduplicate by resolved path (keep first source label)
    seen: Set[str] = set()
    unique: List[Tuple[str, Path]] = []
    for label, path in pairs:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, path))
    return unique


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create meta + FTS5 documents table (drop/rebuild friendly)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
            path,
            source,
            title,
            body,
            tokenize = 'porter unicode61'
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def rebuild_index(
    project: Optional[str] = None,
    *,
    db_path: Optional[Path] = None,
    projects_root: Optional[Path] = None,
    grok: Optional[Path] = None,
    lab_data: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> IndexStats:
    """
    Full rebuild of the FTS index. Safe for offline use; never opens
    session_search.sqlite.
    """
    ensure_knowledge_dir()
    path = db_path or fts_db_path()
    stats = IndexStats(db_path=str(path))

    sources = collect_sources(
        project,
        projects_root=projects_root,
        grok=grok,
        lab_data=lab_data,
        repo_root=repo_root,
    )
    stats.sources = sorted({label for label, _ in sources})

    # Rebuild from scratch for v1 simplicity
    if path.exists():
        # Remove main + WAL/SHM sidecars
        for suffix in ("", "-wal", "-shm"):
            side = Path(str(path) + suffix) if suffix else path
            try:
                if side.exists():
                    side.unlink()
            except OSError:
                pass

    conn = _connect(path)
    try:
        init_schema(conn)
        # Ensure empty table
        conn.execute("DELETE FROM documents")
        conn.commit()

        rows: List[Tuple[str, str, str, str]] = []
        for label, fpath in sources:
            result = _read_text_if_eligible(fpath)
            if result is None:
                stats.skipped += 1
                continue
            body, size = result
            title = _title_from_body(fpath, body)
            try:
                path_str = str(fpath.resolve())
            except OSError:
                path_str = str(fpath)
            rows.append((path_str, label, title, body))
            stats.indexed += 1
            stats.bytes_indexed += size

        if rows:
            conn.executemany(
                "INSERT INTO documents(path, source, title, body) VALUES (?, ?, ?, ?)",
                rows,
            )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('indexed_at', ?)",
            (now,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('doc_count', ?)",
            (str(stats.indexed),),
        )
        conn.commit()
    except sqlite3.Error:
        stats.errors += 1
        raise
    finally:
        conn.close()

    return stats


def status(db_path: Optional[Path] = None) -> dict:
    """Return index status dict for CLI/status consumers."""
    path = db_path or fts_db_path()
    info = {
        "db_path": str(path),
        "exists": path.is_file(),
        "schema_version": None,
        "indexed_at": None,
        "doc_count": 0,
        "size_bytes": 0,
    }
    if not path.is_file():
        return info
    try:
        info["size_bytes"] = path.stat().st_size
    except OSError:
        pass
    try:
        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute("SELECT key, value FROM meta").fetchall()
            meta = {k: v for k, v in rows}
            info["schema_version"] = meta.get("schema_version")
            info["indexed_at"] = meta.get("indexed_at")
            info["doc_count"] = int(meta.get("doc_count") or 0)
            if not info["doc_count"]:
                # Fall back to count(*)
                try:
                    n = conn.execute("SELECT count(*) FROM documents").fetchone()
                    info["doc_count"] = int(n[0]) if n else 0
                except sqlite3.Error:
                    pass
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return info

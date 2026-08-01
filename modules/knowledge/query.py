# Python 3.9+ — Knowledge Crucible FTS query
"""Query the local FTS5 knowledge index. Offline only; no session_search."""

from __future__ import annotations

import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

_LIB = Path(__file__).resolve().parent.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from index import fts_db_path  # noqa: E402  # same package / script dir


@dataclass
class Hit:
    """One search hit."""

    path: str
    source: str
    title: str
    snippet: str
    rank: float

    def format_line(self) -> str:
        snip = " ".join(self.snippet.split())
        if len(snip) > 160:
            snip = snip[:157] + "..."
        return f"[{self.source}] {self.title}\n  {self.path}\n  {snip}"


_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")


def prepare_match_query(terms: str) -> str:
    """
    Turn user terms into an FTS5 MATCH expression.
    AND of tokens; quote tokens that need it; empty → empty string.
    """
    raw = (terms or "").strip()
    if not raw:
        return ""
    # If user already uses FTS operators, pass through lightly sanitized
    if any(op in raw for op in (" AND ", " OR ", " NOT ", '"', "*", ":")):
        return raw

    tokens = _TOKEN_RE.findall(raw)
    if not tokens:
        # fallback: quote whole string
        escaped = raw.replace('"', '""')
        return f'"{escaped}"'
    parts: List[str] = []
    for t in tokens:
        if re.fullmatch(r"[A-Za-z0-9_]+", t):
            parts.append(t)
        else:
            parts.append('"' + t.replace('"', '""') + '"')
    return " AND ".join(parts)


def search(
    terms: str,
    *,
    limit: int = 20,
    source: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Hit]:
    """
    Run FTS5 MATCH against documents. Returns ranked hits with snippets.
    Raises FileNotFoundError if index missing; sqlite3.Error on bad query.
    """
    path = db_path or fts_db_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"knowledge index not found: {path} (run: lab knowledge index)"
        )

    match = prepare_match_query(terms)
    if not match:
        return []

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        # bm25: lower is better in sqlite FTS5
        sql = """
            SELECT
                path,
                source,
                title,
                snippet(documents, 3, '>>>', '<<<', ' … ', 24) AS snip,
                bm25(documents) AS rank
            FROM documents
            WHERE documents MATCH ?
        """
        params: List[object] = [match]
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY rank LIMIT ?"
        params.append(int(limit))

        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Older/missing bm25 or snippet column index — simpler fallback
            sql_fb = """
                SELECT path, source, title, body, 0.0 AS rank
                FROM documents
                WHERE documents MATCH ?
            """
            params_fb: List[object] = [match]
            if source:
                sql_fb += " AND source = ?"
                params_fb.append(source)
            sql_fb += " LIMIT ?"
            params_fb.append(int(limit))
            rows = conn.execute(sql_fb, params_fb).fetchall()
            hits: List[Hit] = []
            for r in rows:
                body = r["body"] if "body" in r.keys() else ""
                snip = " ".join(body.split())[:160]
                hits.append(
                    Hit(
                        path=r["path"],
                        source=r["source"],
                        title=r["title"] or Path(r["path"]).name,
                        snippet=snip,
                        rank=float(r["rank"] or 0.0),
                    )
                )
            return hits

        hits = []
        for r in rows:
            hits.append(
                Hit(
                    path=r["path"],
                    source=r["source"],
                    title=r["title"] or Path(r["path"]).name,
                    snippet=r["snip"] or "",
                    rank=float(r["rank"] or 0.0),
                )
            )
        return hits
    finally:
        conn.close()


def format_results(hits: Sequence[Hit], terms: str) -> str:
    """Human-readable multi-hit report."""
    if not hits:
        return f"No matches for: {terms}"
    lines = [f"{len(hits)} hit(s) for: {terms}", ""]
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. {h.format_line()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

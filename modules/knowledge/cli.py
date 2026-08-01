#!/usr/bin/env python3
# Python 3.9+ — lab knowledge CLI
"""
lab knowledge index|query|status

Offline FTS5 knowledge crucible. Does not integrate with session_search.sqlite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# modules/knowledge on path when run as script
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB = _HERE.parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from index import rebuild_index, status as index_status  # noqa: E402
from query import format_results, search  # noqa: E402


def _cmd_index(args: argparse.Namespace) -> int:
    try:
        stats = rebuild_index(project=args.project)
    except Exception as exc:  # noqa: BLE001 — surface to CLI
        print(f"error: index failed: {exc}", file=sys.stderr)
        return 1
    print(stats.summary_line())
    if stats.sources:
        print("sources: " + ", ".join(stats.sources))
    return 0 if stats.errors == 0 else 1


def _cmd_query(args: argparse.Namespace) -> int:
    terms = " ".join(args.terms).strip()
    if not terms:
        print("error: query requires search terms", file=sys.stderr)
        return 2
    try:
        hits = search(terms, limit=args.limit, source=args.source)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: query failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = [
            {
                "path": h.path,
                "source": h.source,
                "title": h.title,
                "snippet": h.snippet,
                "rank": h.rank,
            }
            for h in hits
        ]
        print(json.dumps({"terms": terms, "count": len(hits), "hits": payload}, indent=2))
    else:
        sys.stdout.write(format_results(hits, terms))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    info = index_status()
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print(f"db:      {info['db_path']}")
    print(f"exists:  {info['exists']}")
    if info["exists"]:
        print(f"docs:    {info['doc_count']}")
        print(f"indexed: {info['indexed_at'] or 'unknown'}")
        print(f"schema:  {info['schema_version'] or 'unknown'}")
        print(f"size:    {info['size_bytes']} bytes")
    else:
        print("hint:    run  lab knowledge index")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab knowledge",
        description="Knowledge Crucible — local FTS5 over memory, AGENTS.md, design docs",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="rebuild FTS index (full rebuild)")
    p_index.add_argument(
        "--project",
        metavar="NAME",
        help="limit project sources to ~/Projects/NAME (memory/rules still global)",
    )
    p_index.set_defaults(func=_cmd_index)

    p_query = sub.add_parser("query", help="search the knowledge index")
    p_query.add_argument(
        "terms",
        nargs="*",
        help="search terms (required; empty exits 2)",
    )
    p_query.add_argument(
        "--limit",
        type=int,
        default=20,
        help="max hits (default 20)",
    )
    p_query.add_argument(
        "--source",
        choices=("memory", "rules", "agents", "design", "showroom", "experiments"),
        help="filter by source label",
    )
    p_query.add_argument(
        "--json",
        action="store_true",
        help="emit JSON results",
    )
    p_query.set_defaults(func=_cmd_query)

    p_status = sub.add_parser("status", help="show index path and doc count")
    p_status.add_argument("--json", action="store_true", help="emit JSON")
    p_status.set_defaults(func=_cmd_status)

    return p


def main(argv: list | None = None) -> int:
    # Python 3.9: list | None needs from __future__ annotations (present)
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

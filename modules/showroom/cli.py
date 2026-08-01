#!/usr/bin/env python3
# Grok Star Lab — Showroom CLI (PR8: capture stub only; publish/regen in PR9)
"""lab showroom capture|list — inbox writes for later curation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from capture import KINDS, capture, list_inbox  # noqa: E402


def cmd_capture(args: argparse.Namespace) -> int:
    source = "manual"
    kind = args.kind or "manual"
    if args.from_ship:
        source = "from-ship"
        kind = args.kind or "ship"
    elif args.from_forge is not None:
        source = "from-forge"
        kind = args.kind or "experiment"
    elif args.from_design is not None:
        source = "from-design"
        kind = args.kind or "design"

    if not args.title:
        print("error: --title is required", file=sys.stderr)
        return 2

    paths: List[str] = list(args.path or [])
    if args.from_design:
        paths.append(args.from_design)
    proof: List[str] = list(args.proof or [])
    extra = {}
    if args.from_forge is not None:
        extra["forge_id"] = args.from_forge

    try:
        out = capture(
            title=args.title,
            kind=kind,
            project=args.project,
            source=source,
            summary=args.summary or "",
            paths=paths,
            proof_commands=proof,
            extra=extra or None,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: write failed: {exc}", file=sys.stderr)
        return 1

    print(f"showroom: captured → {out}")
    print("  (inbox only; publish/regen lands in a later PR)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    # PR8: inbox listing only. Curated entries come with publish in PR9.
    files = list_inbox()
    if not files:
        print("showroom inbox: (empty)")
        return 0
    print(f"showroom inbox: {len(files)} item(s)")
    for f in files:
        title = f.stem
        kind = "?"
        created = ""
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            title = data.get("title") or title
            kind = data.get("kind") or "?"
            created = data.get("created_at") or ""
        except (OSError, json.JSONDecodeError):
            pass
        print(f"  {f.name}  [{kind}]  {title}  {created}")
    if args.paths:
        for f in files:
            print(f"  path: {f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab showroom",
        description="Showroom — capture best work to inbox (no publish in PR8).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("capture", help="write ~/.grok/lab/showroom/inbox/*.json")
    src = sp.add_mutually_exclusive_group()
    src.add_argument("--from-ship", action="store_true", help="mark source=from-ship")
    src.add_argument(
        "--from-forge",
        metavar="ID",
        default=None,
        help="mark source=from-forge with experiment id",
    )
    src.add_argument(
        "--from-design",
        metavar="PATH",
        default=None,
        help="mark source=from-design and attach path",
    )
    src.add_argument("--manual", action="store_true", help="manual capture (default)")
    sp.add_argument("--title", required=True, help="short title")
    sp.add_argument("--project", default=None, help="project name")
    sp.add_argument(
        "--kind",
        choices=list(KINDS),
        default=None,
        help="entry kind (default depends on source)",
    )
    sp.add_argument("--summary", default="", help="one-line summary")
    sp.add_argument(
        "--path",
        action="append",
        default=[],
        help="absolute or relative path to attach (repeatable)",
    )
    sp.add_argument(
        "--proof",
        action="append",
        default=[],
        help="proof command string (repeatable)",
    )
    sp.set_defaults(func=cmd_capture)

    sp_list = sub.add_parser("list", help="list showroom inbox entries")
    sp_list.add_argument(
        "--inbox",
        action="store_true",
        default=True,
        help="list inbox (default; only mode in PR8)",
    )
    sp_list.add_argument(
        "--paths",
        action="store_true",
        help="print full paths",
    )
    sp_list.set_defaults(func=cmd_list)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

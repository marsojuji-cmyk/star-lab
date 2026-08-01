#!/usr/bin/env python3
# lab design — Design Studio CLI
"""CLI entry: lab design list|open|register"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Ensure lib/ and package parent are importable when invoked as a script.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_MODULES = _HERE.parent
for p in (str(_REPO / "lib"), str(_MODULES)):
    if p not in sys.path:
        sys.path.insert(0, p)

from design.design import (  # noqa: E402
    DesignStore,
    ProjectNameError,
    register_doc,
)


def _usage() -> str:
    return """lab design — Design Studio (register/list design docs)

Usage:
  lab design register <path> [--project P] [--slug S] [--showroom] [--no-copy]
  lab design list [--project P] [--limit N] [--json]
  lab design open <id|slug|path> [--project P]

Environment:
  GROK_LAB_DATA   lab data root (default: ~/.grok/lab)
  GROK_HOME       grok home (default: ~/.grok)
  GROK_LAB_REPO   monorepo root override
  PROJECTS        projects root (default: ~/Projects)

Canonical path (when --project set and copy enabled):
  ~/Projects/<project>/docs/design/<YYYY-MM-DD>-<slug>.md

--showroom writes showroom inbox only (no publish).
"""


def cmd_register(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.expanduser().exists():
        print("error: path not found: %s" % path, file=sys.stderr)
        return 1
    try:
        doc = register_doc(
            path,
            project=args.project,
            slug=args.slug,
            showroom=bool(args.showroom),
            copy_to_canonical=not bool(args.no_copy),
        )
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except ProjectNameError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print("error: register failed: %s" % exc, file=sys.stderr)
        return 1

    print(
        "registered  id=%s  slug=%s  project=%s"
        % (doc["id"][:12], doc["slug"], doc.get("project") or "—")
    )
    print("path        %s" % doc["path"])
    if doc.get("_copied"):
        print("copied      yes (canonical docs/design/)")
    if doc.get("showroom_capture_id"):
        print("showroom    inbox capture_id=%s" % doc["showroom_capture_id"])
    elif args.showroom:
        print("showroom    (capture attempted; see showroom/inbox)", file=sys.stderr)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if args.limit < 0:
        print("error: --limit must be >= 0 (got %s)" % args.limit, file=sys.stderr)
        return 2
    store = DesignStore()
    try:
        docs = store.list_docs(project=args.project, limit=args.limit)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        out = []
        for d in docs:
            row = {k: d[k] for k in d.keys()}
            if row.get("tags"):
                try:
                    row["tags"] = json.loads(row["tags"])
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(row)
        print(json.dumps(out, indent=2))
        return 0

    if not docs:
        print("(no design docs registered)")
        return 0

    print(
        "%-12s  %-20s  %-16s  %-24s  %s"
        % ("id", "slug", "project", "registered", "path")
    )
    for d in docs:
        print(
            "%-12s  %-20s  %-16s  %-24s  %s"
            % (
                d["id"][:12],
                (d.get("slug") or "")[:20],
                (d.get("project") or "—")[:16],
                (d.get("registered_at") or "")[:24],
                d.get("path") or "",
            )
        )
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    store = DesignStore()
    key = args.key
    doc = store.find(key, project=args.project)
    if not doc:
        # Allow opening an unregistered path
        p = Path(key).expanduser()
        if p.is_file():
            return _open_path(p)
        print("error: not found: %s" % key, file=sys.stderr)
        print("hint: lab design list", file=sys.stderr)
        return 1

    path = Path(doc["path"])
    if not path.is_file():
        print("error: registered path missing: %s" % path, file=sys.stderr)
        return 1
    print("open  %s  (%s)" % (path, doc.get("slug") or doc["id"][:12]))
    return _open_path(path)


def _open_path(path: Path) -> int:
    """Open with $EDITOR, else macOS open / xdg-open, else print path."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        try:
            return int(subprocess.call([editor, str(path)]))
        except OSError as exc:
            print("error: EDITOR failed: %s" % exc, file=sys.stderr)
            return 1
    if sys.platform == "darwin" and _which("open"):
        return int(subprocess.call(["open", str(path)]))
    if _which("xdg-open"):
        return int(subprocess.call(["xdg-open", str(path)]))
    print(path)
    return 0


def _which(name: str) -> bool:
    from shutil import which

    return which(name) is not None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab design",
        description="Design Studio — register and list design docs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_usage(),
    )
    sub = p.add_subparsers(dest="command")

    pr = sub.add_parser("register", help="Register a design markdown path")
    pr.add_argument("path", help="Path to markdown design doc")
    pr.add_argument("--project", default=None, help="Project name under ~/Projects")
    pr.add_argument("--slug", default=None, help="Stable slug (default: from filename)")
    pr.add_argument(
        "--showroom",
        action="store_true",
        help="Also write showroom inbox capture (no publish)",
    )
    pr.add_argument(
        "--no-copy",
        action="store_true",
        help="Record pointer only; do not copy to docs/design/",
    )
    pr.set_defaults(func=cmd_register)

    pl = sub.add_parser("list", help="List registered design docs")
    pl.add_argument("--project", default=None)
    pl.add_argument(
        "--limit",
        type=int,
        default=100,
        help="max rows (default 100; must be >= 0)",
    )
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_list)

    po = sub.add_parser("open", help="Open a registered design doc")
    po.add_argument("key", help="id, slug, or path")
    po.add_argument("--project", default=None)
    po.set_defaults(func=cmd_open)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        print(_usage())
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

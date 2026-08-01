#!/usr/bin/env python3
# Grok Star Lab — Showroom CLI
"""lab showroom capture|list|publish|open — inbox capture + curated publish."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_LIB = _REPO / "lib"
for p in (str(_HERE), str(_LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from capture import KINDS, capture, list_inbox  # noqa: E402
from lab_paths import repo_root  # noqa: E402
from publish import list_curated, load_inbox_item, publish_inbox_item  # noqa: E402
from regen_index import regenerate, showroom_dir  # noqa: E402


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
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: write failed: %s" % exc, file=sys.stderr)
        return 1

    print("showroom: captured → %s" % out)
    print("  (inbox only; publish with: lab showroom publish %s)" % out.stem)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if args.inbox:
        files = list_inbox()
        if not files:
            print("showroom inbox: (empty)")
            return 0
        print("showroom inbox: %d item(s)" % len(files))
        for f in files:
            title = f.stem
            kind = "?"
            created = ""
            published = ""
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                title = data.get("title") or title
                kind = data.get("kind") or "?"
                created = data.get("created_at") or ""
                if data.get("published"):
                    published = " [published]"
            except (OSError, json.JSONDecodeError):
                pass
            print("  %s  [%s]  %s  %s%s" % (f.name, kind, title, created, published))
            if args.paths:
                print("    path: %s" % f)
        return 0

    # Curated entries (default)
    entries = list_curated(repo_root())
    if not entries:
        print("showroom entries: (empty) — try lab showroom list --inbox")
        return 0
    print("showroom entries: %d" % len(entries))
    for e in entries:
        eid = e.get("entry_id") or "?"
        kind = e.get("kind") or "?"
        title = e.get("title") or eid
        date = e.get("published_at") or e.get("created_at") or ""
        print("  %s  [%s]  %s  %s" % (eid, kind, title, date))
        if args.paths:
            print("    dir: showroom/entries/%s" % (e.get("_dir") or eid))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    root = repo_root()
    ids: List[str] = list(args.ids or [])
    if args.all:
        files = list_inbox()
        # only unpublished (not already in done/)
        ids = [f.stem for f in files]
        if not ids:
            print("showroom: inbox empty — nothing to publish")
            return 0
        if not args.yes:
            print("showroom: about to publish %d inbox item(s):" % len(ids))
            for i in ids:
                print("  %s" % i)
            try:
                ans = input("Continue? [y/N] ").strip().lower()
            except EOFError:
                ans = ""
            if ans not in ("y", "yes"):
                print("showroom: publish cancelled")
                return 1
    elif not ids:
        print("error: provide capture id(s) or --all", file=sys.stderr)
        return 2

    ok = 0
    failed = 0
    for cid in ids:
        try:
            # skip if already published flag in file
            try:
                _path, data = load_inbox_item(cid)
                if data.get("published") and not args.force:
                    print("showroom: skip %s (already published; use --force)" % cid)
                    continue
            except FileNotFoundError:
                pass
            result = publish_inbox_item(
                cid,
                root=root,
                keep_inbox=bool(args.keep_inbox),
            )
        except FileNotFoundError as exc:
            print("error: %s" % exc, file=sys.stderr)
            failed += 1
            continue
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            failed += 1
            continue
        except OSError as exc:
            print("error: publish failed: %s" % exc, file=sys.stderr)
            failed += 1
            continue

        eid = result["entry_id"]
        print("showroom: published → showroom/entries/%s/" % eid)
        print("  index: %s" % result["index_path"])
        print(
            "  optional: git add showroom/entries/%s showroom/index.html"
            % eid
        )
        ok += 1

    if ok == 0 and failed > 0:
        return 1
    if failed > 0:
        print("showroom: published %d, failed %d" % (ok, failed), file=sys.stderr)
        return 1
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    root = repo_root()
    if args.entry:
        body = root / "showroom" / "entries" / args.entry / "body.md"
        meta = root / "showroom" / "entries" / args.entry / "meta.json"
        target = body if body.is_file() else meta
        if not target.is_file():
            # try prefix match
            ed = root / "showroom" / "entries"
            matches = sorted(ed.glob("%s*" % args.entry)) if ed.is_dir() else []
            if len(matches) == 1:
                body = matches[0] / "body.md"
                target = body if body.is_file() else matches[0] / "meta.json"
            else:
                print("error: entry not found: %s" % args.entry, file=sys.stderr)
                return 1
    else:
        # Ensure index exists
        idx = showroom_dir(root) / "index.html"
        if not idx.is_file():
            regenerate(root)
        target = showroom_dir(root) / "index.html"

    print("showroom: open %s" % target)
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(target)], check=False)
        else:
            # fall back: print path only
            pass
    except OSError as exc:
        print("warn: could not open viewer: %s" % exc, file=sys.stderr)
        print(target)
        return 0
    return 0


def cmd_regen(args: argparse.Namespace) -> int:
    path = regenerate(repo_root())
    print("showroom: regenerated %s" % path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab showroom",
        description="Showroom — capture inbox, publish curated gallery, open index.",
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

    sp_list = sub.add_parser("list", help="list curated entries (or --inbox)")
    sp_list.add_argument(
        "--inbox",
        action="store_true",
        help="list ~/.grok/lab/showroom/inbox instead of curated entries",
    )
    sp_list.add_argument(
        "--paths",
        action="store_true",
        help="print full paths",
    )
    sp_list.set_defaults(func=cmd_list)

    sp_pub = sub.add_parser(
        "publish",
        help="promote inbox item(s) → showroom/entries + regen index",
    )
    sp_pub.add_argument(
        "ids",
        nargs="*",
        help="capture id(s) or inbox json path",
    )
    sp_pub.add_argument(
        "--all",
        action="store_true",
        help="publish all inbox items (prompts unless --yes)",
    )
    sp_pub.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="skip confirm for --all",
    )
    sp_pub.add_argument(
        "--keep-inbox",
        action="store_true",
        help="leave item in inbox (mark published) instead of moving to inbox/done/",
    )
    sp_pub.add_argument(
        "--force",
        action="store_true",
        help="allow re-publish of items already marked published",
    )
    sp_pub.set_defaults(func=cmd_publish)

    sp_open = sub.add_parser("open", help="open showroom/index.html (or an entry body)")
    sp_open.add_argument(
        "entry",
        nargs="?",
        default=None,
        help="optional entry_id to open body.md",
    )
    sp_open.set_defaults(func=cmd_open)

    sp_regen = sub.add_parser(
        "regen",
        help="rebuild showroom/index.html from entries (no publish)",
    )
    sp_regen.set_defaults(func=cmd_regen)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

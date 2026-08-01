#!/usr/bin/env python3
# lab arena — Agent Arena CLI
"""CLI entry: lab arena list|run|describe|help

Offline script pipelines (kind: script) run under this process.
Workflow pipelines (kind: workflow) print session-tier handoff only — no headless Rhai (K19).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_MODULES = _HERE.parent
for p in (str(_REPO / "lib"), str(_MODULES)):
    if p not in sys.path:
        sys.path.insert(0, p)

from arena.runner import (  # noqa: E402
    describe_pipeline,
    list_pipelines,
    load_pipeline,
    run_pipeline,
)


def _usage() -> str:
    return """lab arena — Agent Arena (offline scripts + session workflow handoff)

Usage:
  lab arena list
  lab arena describe <pipeline>
  lab arena run <pipeline> [--no-forge] [--handoff-prompt FILE] [-- ARGS...]
  lab arena help

Pipeline kinds:
  script     Offline bash/python. Runs immediately under lab arena run.
             forge: true → wrap with lab forge run contract (GROK_LAB_RUN_ID).
  workflow   Session-tier only. Prints /workflow instructions. Never headless (K19).

Built-in:
  lab-audit   kind:script   — module presence, safety, disk, ollama, version pin
  home-audit  kind:workflow — multi-agent Rhai handoff (requires Grok session)

Environment:
  GROK_LAB_REPO   monorepo root override
  GROK_LAB_DATA   lab data root (default: ~/.grok/lab)
  GROK_HOME       grok home (default: ~/.grok)

Examples:
  lab arena list
  lab arena run lab-audit
  lab arena run lab-audit --no-forge
  lab arena run home-audit
  lab arena run home-audit --handoff-prompt /tmp/home-audit-prompt.txt
  lab arena describe lab-audit
"""


def cmd_list(_args: argparse.Namespace) -> int:
    pipes = list_pipelines()
    if not pipes:
        print("(no pipelines in modules/arena/pipelines/)")
        return 0
    print("%-16s  %-10s  %-6s  %s" % ("name", "kind", "forge", "description"))
    for p in pipes:
        print(
            "%-16s  %-10s  %-6s  %s"
            % (
                (p.get("name") or "?")[:16],
                (p.get("kind") or "?")[:10],
                "yes" if p.get("forge") else "no",
                (p.get("description") or "")[:60],
            )
        )
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    name = args.pipeline
    if not name:
        print("error: pipeline name required", file=sys.stderr)
        return 2
    try:
        pipe = load_pipeline(name)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    print(describe_pipeline(pipe))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    name = args.pipeline
    if not name:
        print("error: pipeline name required", file=sys.stderr)
        return 2
    handoff = Path(args.handoff_prompt) if args.handoff_prompt else None
    extra = list(getattr(args, "extra", None) or [])
    return run_pipeline(
        name,
        extra_args=extra,
        no_forge=bool(args.no_forge),
        handoff_prompt=handoff,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab arena",
        description="Agent Arena — offline pipelines + workflow handoff",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_usage(),
    )
    sub = p.add_subparsers(dest="command")

    pl = sub.add_parser("list", help="List registered pipelines")
    pl.set_defaults(func=cmd_list)

    pd = sub.add_parser("describe", help="Show pipeline detail")
    pd.add_argument("pipeline", help="Pipeline name (e.g. lab-audit)")
    pd.set_defaults(func=cmd_describe)

    pr = sub.add_parser("run", help="Run script pipeline or print workflow handoff")
    pr.add_argument("pipeline", help="Pipeline name (e.g. lab-audit)")
    pr.add_argument(
        "--no-forge",
        action="store_true",
        help="Skip forge wrap even when pipeline has forge: true",
    )
    pr.add_argument(
        "--handoff-prompt",
        default=None,
        metavar="FILE",
        help="For kind:workflow, write a pasteable prompt to FILE",
    )
    # Extra script args are split manually on `--` in main() so flags like
    # --no-forge are not swallowed by argparse.REMAINDER.
    pr.set_defaults(func=cmd_run, extra=[])

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0

    # Split `run … -- script-args` before argparse so option flags parse cleanly.
    extra: List[str] = []
    if argv and argv[0] == "run" and "--" in argv:
        i = argv.index("--")
        extra = argv[i + 1 :]
        argv = argv[:i]

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        print(_usage())
        return 0
    if args.command == "run":
        args.extra = extra
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# lab forge — Experiment Forge CLI
"""CLI entry: lab forge run|list|show|init|export"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Ensure lib/ and modules/ are importable when invoked as a script.
# Prefer package import: modules/forge/{__init__,forge,cli}.py
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_MODULES = _HERE.parent
for p in (str(_REPO / "lib"), str(_MODULES)):
    if p not in sys.path:
        sys.path.insert(0, p)

from forge.forge import ForgeStore, run_command  # noqa: E402
from lab_paths import lab_data_root  # noqa: E402


def _usage() -> str:
    return """lab forge — local experiment tracking (SQLite + Markdown)

Usage:
  lab forge run  --exp NAME [--project P] [--tag TAG ...] [--timeout SECS] -- CMD [ARGS...]
  lab forge list [--exp NAME] [--limit N]
  lab forge show <run_id|exp_name>
  lab forge init --exp NAME [--project P] [--tag TAG ...]
  lab forge export [--exp NAME] [--jsonl]

Environment:
  GROK_LAB_DATA   lab data root (default: ~/.grok/lab)
  GROK_HOME       grok home (default: ~/.grok)
  GROK_LAB_REPO   monorepo root override

Run sets GROK_LAB_RUN_ID for the child process. Exit code matches child.
"""


def cmd_run(args: argparse.Namespace) -> int:
    if not args.cmd:
        print("error: command required after --", file=sys.stderr)
        return 2
    exp = args.exp
    if not exp:
        print("error: --exp NAME is required", file=sys.stderr)
        return 2
    store = ForgeStore()
    tags = list(args.tag or [])
    return run_command(
        store,
        exp_name=exp,
        command=args.cmd,
        project=args.project,
        tags=tags,
        timeout=args.timeout,
    )


def cmd_list(args: argparse.Namespace) -> int:
    store = ForgeStore()
    if args.exp:
        exp = store.get_experiment_by_name(args.exp, project=args.project)
        if not exp:
            print("error: experiment not found: %s" % args.exp, file=sys.stderr)
            return 1
        runs = store.list_runs(experiment_id=exp["id"], limit=args.limit)
        print(
            "experiment  %s  id=%s  project=%s"
            % (exp["name"], exp["id"], exp.get("project") or "—")
        )
        print("")
        _print_runs(runs)
        return 0

    # Default: recent runs (most useful for gym/mission control)
    if args.experiments:
        exps = store.list_experiments()
        if not exps:
            print("(no experiments)")
            return 0
        print(
            "%-12s  %-24s  %-16s  %5s  %s"
            % ("id", "name", "project", "runs", "last")
        )
        for e in exps:
            print(
                "%-12s  %-24s  %-16s  %5s  %s"
                % (
                    e["id"][:12],
                    (e["name"] or "")[:24],
                    (e.get("project") or "—")[:16],
                    e.get("run_count", 0),
                    e.get("last_status") or "—",
                )
            )
        return 0

    runs = store.list_runs(limit=args.limit)
    _print_runs(runs)
    return 0


def _print_runs(runs: List[dict]) -> None:
    if not runs:
        print("(no runs)")
        return
    print(
        "%-12s  %-20s  %-10s  %6s  %8s  %s"
        % ("run_id", "exp", "status", "exit", "ms", "created")
    )
    for r in runs:
        print(
            "%-12s  %-20s  %-10s  %6s  %8s  %s"
            % (
                r["id"][:12],
                (r.get("experiment_name") or "")[:20],
                r["status"],
                r.get("exit_code") if r.get("exit_code") is not None else "—",
                r.get("duration_ms") if r.get("duration_ms") is not None else "—",
                r.get("created_at") or "",
            )
        )


def cmd_show(args: argparse.Namespace) -> int:
    store = ForgeStore()
    key = args.id
    run = store.get_run(key)
    if not run and len(key) >= 8:
        # Prefix match on run id
        with store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE id LIKE ? ORDER BY created_at DESC LIMIT 2",
                (key + "%",),
            ).fetchall()
        if len(row) == 1:
            run = dict(row[0])
        elif len(row) > 1:
            print("error: ambiguous run id prefix: %s" % key, file=sys.stderr)
            return 1

    if run:
        exp = store.get_experiment(run["experiment_id"])
        payload = {
            "run": {k: run[k] for k in run.keys()},
            "experiment": exp,
            "dir": str(lab_data_root() / "experiments" / run["id"]),
        }
        # Pretty human + JSON-friendly
        if args.json:
            # Parse JSON columns for readability
            for col in ("command", "tags", "params", "metrics"):
                if payload["run"].get(col):
                    try:
                        payload["run"][col] = json.loads(payload["run"][col])
                    except (json.JSONDecodeError, TypeError):
                        pass
            print(json.dumps(payload, indent=2))
        else:
            print("run_id:        %s" % run["id"])
            print("experiment:    %s (%s)" % (
                exp["name"] if exp else "?",
                run["experiment_id"],
            ))
            print("project:       %s" % ((exp or {}).get("project") or "—"))
            print("status:        %s" % run["status"])
            print("exit_code:     %s" % run.get("exit_code"))
            print("duration_ms:   %s" % run.get("duration_ms"))
            print("created_at:    %s" % run["created_at"])
            print("finished_at:   %s" % (run.get("finished_at") or "—"))
            print("git_sha:       %s" % (run.get("git_sha") or "—"))
            print("command:       %s" % run.get("command"))
            print("tags:          %s" % run.get("tags"))
            print("params:        %s" % run.get("params"))
            print("metrics:       %s" % run.get("metrics"))
            print("dir:           %s" % (lab_data_root() / "experiments" / run["id"]))
            meta = lab_data_root() / "experiments" / run["id"] / "meta.md"
            if meta.is_file():
                print("")
                print("--- meta.md ---")
                print(meta.read_text(encoding="utf-8"), end="")
        return 0

    # Fall back: experiment by name or id
    exp = store.get_experiment(key) or store.get_experiment_by_name(key)
    if not exp:
        print("error: not found: %s" % key, file=sys.stderr)
        return 1
    runs = store.list_runs(experiment_id=exp["id"], limit=args.limit)
    if args.json:
        print(json.dumps({"experiment": exp, "runs": runs}, indent=2, default=str))
    else:
        print("experiment:  %s" % exp["name"])
        print("id:          %s" % exp["id"])
        print("project:     %s" % (exp.get("project") or "—"))
        print("created_at:  %s" % exp["created_at"])
        print("")
        _print_runs(runs)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    exp_name = args.exp
    if not exp_name:
        print("error: --exp NAME is required", file=sys.stderr)
        return 2
    store = ForgeStore()
    exp = store.get_or_create_experiment(
        exp_name, project=args.project, tags=args.tag, description=args.description
    )
    print("experiment id=%s name=%s project=%s" % (
        exp["id"], exp["name"], exp.get("project") or "—",
    ))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = ForgeStore()
    experiment_id = None
    if args.exp:
        exp = store.get_experiment_by_name(args.exp, project=args.project)
        if not exp:
            print("error: experiment not found: %s" % args.exp, file=sys.stderr)
            return 1
        experiment_id = exp["id"]
    runs = store.list_runs(experiment_id=experiment_id, limit=args.limit)
    for r in runs:
        out = dict(r)
        for col in ("command", "tags", "params", "metrics"):
            if out.get(col):
                try:
                    out[col] = json.loads(out[col])
                except (json.JSONDecodeError, TypeError):
                    pass
        print(json.dumps(out, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab forge",
        description="Experiment Forge — local run tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_usage(),
    )
    sub = p.add_subparsers(dest="command")

    # run
    pr = sub.add_parser("run", help="Run command under GROK_LAB_RUN_ID wrapper")
    pr.add_argument(
        "--exp",
        "--name",
        dest="exp",
        default=None,
        help="Experiment name (--name is an alias)",
    )
    pr.add_argument("--project", default=None, help="Project label")
    pr.add_argument("--tag", action="append", default=[], help="Tag (repeatable)")
    pr.add_argument("--timeout", type=float, default=None, help="Optional timeout seconds")
    pr.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="Command after -- ",
    )
    pr.set_defaults(func=cmd_run)

    # list
    pl = sub.add_parser("list", help="List recent runs (or experiments)")
    pl.add_argument("--exp", default=None, help="Filter by experiment name")
    pl.add_argument("--project", default=None)
    pl.add_argument("--limit", type=int, default=50)
    pl.add_argument(
        "--experiments",
        action="store_true",
        help="List experiments instead of runs",
    )
    pl.set_defaults(func=cmd_list)

    # show
    ps = sub.add_parser("show", help="Show run or experiment detail")
    ps.add_argument("id", help="Run id (or prefix) or experiment name/id")
    ps.add_argument("--json", action="store_true")
    ps.add_argument("--limit", type=int, default=20)
    ps.set_defaults(func=cmd_show)

    # init
    pi = sub.add_parser("init", help="Create experiment without running")
    pi.add_argument(
        "--exp",
        "--name",
        dest="exp",
        default=None,
        help="Experiment name (--name is an alias)",
    )
    pi.add_argument("--project", default=None)
    pi.add_argument("--tag", action="append", default=[])
    pi.add_argument("--description", default=None)
    pi.set_defaults(func=cmd_init)

    # export
    pe = sub.add_parser("export", help="Export runs as JSONL to stdout")
    pe.add_argument("--exp", default=None)
    pe.add_argument("--project", default=None)
    pe.add_argument("--limit", type=int, default=1000)
    pe.set_defaults(func=cmd_export)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0

    # Strip a leading "--" only used as separator before the command for `run`.
    parser = build_parser()
    # Special-case: `run ... -- cmd` — argparse REMAINDER keeps leading --
    args = parser.parse_args(argv)
    if not args.command:
        print(_usage())
        return 0

    if args.command == "run":
        cmd = list(args.cmd or [])
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        args.cmd = cmd

    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

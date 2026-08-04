#!/usr/bin/env python3
"""lab auto — zero-ceremony operate session for 1000× (human least / Grok most).

Commands:
  lab auto "goal…"              begin (alias)
  lab auto begin "goal…"        route + research + save session state
  lab auto finish               complete research/tokens + factory + galaxy
  lab auto status               show open auto session
  lab auto go "goal…"           begin → factory → finish (full autopilot)

State: ~/.grok/lab/session_auto.json
Human never pastes audit/research ids.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_MOD = str(_HERE.parent)
if _MOD not in sys.path:
    sys.path.insert(0, _MOD)


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def _state_path() -> Path:
    return _lab_data() / "session_auto.json"


def _lab_bin() -> str:
    env = os.environ.get("LAB_BIN")
    if env and Path(env).is_file():
        return env
    home = Path.home() / ".local" / "bin" / "lab"
    if home.is_file():
        return str(home)
    repo = Path(__file__).resolve().parents[2] / "bin" / "lab"
    if repo.is_file():
        return str(repo)
    return "lab"


def _run_lab(
    argv: List[str], *, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None
) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [_lab_bin()] + argv, cwd=cwd, env=e, text=True, capture_output=True
    )


def _load_state() -> Optional[Dict[str, Any]]:
    p = _state_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_state(data: Dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    data["updated_ts"] = time.time()
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _clear_state() -> None:
    p = _state_path()
    if p.is_file():
        p.unlink()


def _resolve_body(
    *, body: Optional[str], project: Optional[str], cwd: str
) -> Optional[Any]:
    try:
        from body.resolve import resolve_body
        from body.store import BodyStore
    except Exception:
        return None

    b = resolve_body(body=body, project=project, cwd=cwd)
    if b:
        return b
    # Auto-init project body when cwd is under ~/Projects/<name>
    cpath = Path(cwd).resolve()
    projects = (Path.home() / "Projects").resolve()
    try:
        cpath.relative_to(projects)
    except ValueError:
        return None
    name = cpath.name
    if not name or name.startswith("."):
        return None
    store = BodyStore()
    existing = store.load("project:%s" % name)
    if existing:
        return existing
    return store.init_body(kind="project", name=name, repo=str(cpath), mode_cap="medium")


def cmd_status(_args: argparse.Namespace) -> int:
    st = _load_state()
    if not st:
        print("auto: no open session (lab auto begin \"goal\")")
        return 0
    print("═══ lab auto session ═══")
    for k in (
        "goal",
        "body_id",
        "repo",
        "audit_id",
        "research_id",
        "mode",
        "budget_tokens",
        "phase",
    ):
        if st.get(k) is not None:
            print("%-14s %s" % (k + ":", st.get(k)))
    return 0


def cmd_begin(args: argparse.Namespace) -> int:
    goal = (args.goal or "").strip()
    if not goal:
        print("error: goal required", file=sys.stderr)
        return 2
    cwd_path = Path(args.cwd or os.getcwd()).expanduser()
    try:
        cwd_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    cwd = str(cwd_path.resolve())
    body = _resolve_body(body=args.body, project=args.project, cwd=cwd)
    body_id = body.body_id if body else None
    project = (body.project_key() if body else None) or args.project
    repo = None
    if body:
        repo = (body.identity or {}).get("repo_path") or cwd
        cwd = str(Path(repo).expanduser()) if repo else cwd

    env: Dict[str, str] = {}
    if body_id:
        env["GROK_BODY"] = body_id
    if project:
        env["GROK_PROJECT"] = project

    route_argv = ["tokens", "route", goal]
    if body_id:
        route_argv += ["--body", body_id]
    if project:
        route_argv += ["--project", str(project)]
    if args.force_mode:
        route_argv += ["--force-mode", args.force_mode]

    print("═══ lab auto begin ═══")
    print("goal: %s" % goal)
    if body_id:
        print("body: %s" % body_id)
    print("cwd:  %s" % cwd)

    r = _run_lab(route_argv, cwd=cwd, env=env)
    sys.stdout.write(r.stdout or "")
    if r.stderr:
        sys.stderr.write(r.stderr)
    if r.returncode != 0:
        return int(r.returncode)

    audit_id = None
    mode = "short"
    budget = 512
    m = re.search(r"audit_id:\s*(\S+)", r.stdout or "")
    if m:
        audit_id = m.group(1)
    mm = re.search(r"mode:\s+(\S+)", r.stdout or "")
    if mm:
        mode = mm.group(1)
    bm = re.search(r"budget_tokens:\s+(\d+)", r.stdout or "")
    if bm:
        budget = int(bm.group(1))

    research_id = None
    if not args.no_research:
        rargv = ["research", "start", goal, "--repo", cwd, "--mode", mode or "short"]
        if audit_id:
            rargv += ["--token-audit-id", audit_id]
        rr = _run_lab(rargv, cwd=cwd, env=env)
        sys.stdout.write(rr.stdout or "")
        if rr.stderr:
            sys.stderr.write(rr.stderr)
        rm = re.search(r"started id=(\S+)", rr.stdout or "")
        if rm:
            research_id = rm.group(1)

    state = {
        "phase": "open",
        "goal": goal,
        "body_id": body_id,
        "project": project,
        "repo": cwd,
        "audit_id": audit_id,
        "research_id": research_id,
        "mode": mode,
        "budget_tokens": budget,
        "started_ts": time.time(),
    }
    _save_state(state)
    print("─── auto state saved ───")
    print("audit_id:    %s" % (audit_id or "(none)"))
    print("research_id: %s" % (research_id or "(none)"))
    print("next: work, then  lab auto finish [--success yes|no]")
    print("     or full:     lab auto go is already mid-flight — use finish")
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    st = _load_state()
    if not st or st.get("phase") == "closed":
        print("error: no open auto session — lab auto begin \"goal\" first", file=sys.stderr)
        return 1

    cwd = st.get("repo") or os.getcwd()
    body_id = st.get("body_id")
    project = st.get("project")
    audit_id = st.get("audit_id")
    research_id = st.get("research_id")
    budget = int(st.get("budget_tokens") or 512)
    tokens = args.tokens if args.tokens is not None else budget
    quality = args.quality if args.quality is not None else 0.85
    success = args.success or "yes"
    env: Dict[str, str] = {}
    if body_id:
        env["GROK_BODY"] = body_id
    if project:
        env["GROK_PROJECT"] = str(project)

    print("═══ lab auto finish ═══")
    print("goal: %s" % st.get("goal"))
    fac_ec = 0

    # Optional factory when body has repo + tests
    if body_id and not args.no_factory:
        fr = _run_lab(["body", "factory", body_id], cwd=cwd, env=env)
        sys.stdout.write(fr.stdout or "")
        if fr.stderr:
            sys.stderr.write(fr.stderr)
        fac_ec = int(fr.returncode)
        if fac_ec != 0 and success == "yes" and not args.force_success:
            success = "no"
            print("auto: factory nonzero → success=no (pass --force-success to override)")

    if research_id:
        cargv = [
            "research",
            "complete",
            research_id,
            "--success",
            success,
            "--tests-passed",
            "yes" if fac_ec == 0 else "no",
            "--actual-tokens",
            str(int(tokens)),
            "--notes",
            "lab auto finish factory_exit=%s" % fac_ec,
        ]
        rc = _run_lab(cargv, cwd=cwd, env=env)
        sys.stdout.write(rc.stdout or "")
        if rc.stderr:
            sys.stderr.write(rc.stderr)

    if audit_id:
        targv = [
            "tokens",
            "complete",
            "--audit-id",
            audit_id,
            "--actual-tokens",
            str(int(tokens)),
            "--quality",
            str(quality),
            "--success",
            success,
        ]
        if body_id:
            targv += ["--body", body_id]
        if project:
            targv += ["--project", str(project)]
        tc = _run_lab(targv, cwd=cwd, env=env)
        sys.stdout.write(tc.stdout or "")
        if tc.stderr:
            sys.stderr.write(tc.stderr)

    if args.publish:
        title = "auto: %s" % ((st.get("goal") or "")[:70])
        sc = _run_lab(
            [
                "showroom",
                "capture",
                "--manual",
                "--title",
                title,
                "--project",
                str(project or "lab"),
                "--kind",
                "experiment",
                "--summary",
                "auto finish success=%s factory=%s" % (success, fac_ec),
                "--publish",
            ],
            cwd=cwd,
            env=env,
        )
        sys.stdout.write(sc.stdout or "")
        if sc.stderr:
            sys.stderr.write(sc.stderr)

    if not args.no_galaxy:
        gc = _run_lab(["galaxy", "collect"], cwd=cwd, env=env)
        # status glance only summary
        gs = _run_lab(["galaxy", "status"], cwd=cwd, env=env)
        # print last status block compact
        if gs.stdout:
            for line in (gs.stdout or "").splitlines()[:12]:
                print(line)

    st["phase"] = "closed"
    st["finished_ts"] = time.time()
    st["success"] = success
    st["factory_exit"] = fac_ec
    st["actual_tokens"] = tokens
    _save_state(st)
    if not args.keep_state:
        _clear_state()
        print("auto: session closed + state cleared")
    else:
        print("auto: session closed (state kept)")

    print("─── finish summary ───")
    print("success:  %s" % success)
    print("factory:  exit=%s" % fac_ec)
    print("tokens:   %s" % tokens)
    return 0 if success == "yes" and fac_ec == 0 else 1


def cmd_go(args: argparse.Namespace) -> int:
    """Full autopilot: begin → factory (via finish) → finish."""
    # begin
    b = argparse.Namespace(
        goal=args.goal,
        body=args.body,
        project=args.project,
        cwd=args.cwd,
        force_mode=args.force_mode,
        no_research=False,
    )
    ec = cmd_begin(b)
    if ec != 0:
        return ec
    f = argparse.Namespace(
        tokens=args.tokens,
        quality=args.quality if args.quality is not None else 0.9,
        success=args.success or "yes",
        no_factory=False,
        force_success=bool(args.force_success),
        publish=bool(args.publish),
        no_galaxy=False,
        keep_state=False,
    )
    return cmd_finish(f)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab auto",
        description="Human-minimal operate session (Grok carries ceremony)",
    )
    sub = p.add_subparsers(dest="cmd")

    # bare: lab auto "goal" handled in main
    b = sub.add_parser("begin", help="Route + research + save session (no id paste)")
    b.add_argument("goal", nargs="?", default="", help="Task goal")
    b.add_argument("--body", default=None)
    b.add_argument("--project", default=None)
    b.add_argument("--cwd", default=None, help="Working directory / repo")
    b.add_argument("--force-mode", default=None)
    b.add_argument("--no-research", action="store_true")
    b.set_defaults(func=cmd_begin)

    f = sub.add_parser("finish", help="Complete open session + factory + galaxy")
    f.add_argument("--tokens", type=int, default=None, help="Actual tokens (default: route budget)")
    f.add_argument("--quality", type=float, default=None)
    f.add_argument("--success", choices=["yes", "no"], default=None)
    f.add_argument("--no-factory", action="store_true")
    f.add_argument("--force-success", action="store_true")
    f.add_argument("--publish", action="store_true")
    f.add_argument("--no-galaxy", action="store_true")
    f.add_argument("--keep-state", action="store_true")
    f.set_defaults(func=cmd_finish)

    g = sub.add_parser("go", help="Full autopilot begin→factory→finish")
    g.add_argument("goal", help="Task goal")
    g.add_argument("--body", default=None)
    g.add_argument("--project", default=None)
    g.add_argument("--cwd", default=None)
    g.add_argument("--force-mode", default=None)
    g.add_argument("--tokens", type=int, default=None)
    g.add_argument("--quality", type=float, default=None)
    g.add_argument("--success", choices=["yes", "no"], default=None)
    g.add_argument("--force-success", action="store_true")
    g.add_argument("--publish", action="store_true")
    g.set_defaults(func=cmd_go)

    s = sub.add_parser("status", help="Show open auto session")
    s.set_defaults(func=cmd_status)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # lab auto "goal text…" → begin
    if argv and not argv[0].startswith("-") and argv[0] not in (
        "begin",
        "finish",
        "go",
        "status",
        "help",
        "-h",
        "--help",
    ):
        # treat remaining as goal words if first isn't a subcommand
        argv = ["begin"] + argv

    p = build_parser()
    if not argv or argv[0] in ("help", "-h", "--help"):
        p.print_help()
        return 0
    args = p.parse_args(argv)
    if not hasattr(args, "func"):
        p.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

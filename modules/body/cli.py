#!/usr/bin/env python3
"""lab body — identity / ledger / contact CLI (PR-B1–B2)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# modules/ on path
_HERE = Path(__file__).resolve().parent
_MOD = str(_HERE.parent)
if _MOD not in sys.path:
    sys.path.insert(0, _MOD)

from body.store import BodyStore
from body.resolve import resolve_body, resolve_info
from body.ledger import list_obligations, close_obligation, append_obligation
from body.events import ingest, list_events
from body.organs import load_bindings


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_init(args: argparse.Namespace) -> int:
    store = BodyStore()
    body = store.init_body(
        kind=args.kind,
        name=args.name,
        repo=args.repo,
        mode_cap=args.mode_cap,
        budget_day=args.budget_day,
        validation_cmd=getattr(args, "validation_cmd", None),
    )
    # Allow updating validation_cmd on existing body
    vcmd = (getattr(args, "validation_cmd", None) or "").strip()
    if vcmd:
        meta = dict(body.meta or {})
        meta["validation_cmd"] = vcmd
        body.meta = meta
        store.save(body)
    print("body: %s" % body.body_id)
    print("  dir: %s" % store.body_dir(body.body_id))
    print("  kind: %s name: %s" % (body.kind, body.name))
    if (body.meta or {}).get("validation_cmd"):
        print("  validation_cmd: %s" % body.meta.get("validation_cmd"))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = BodyStore().list()
    if args.json:
        _print_json(rows)
        return 0
    if not rows:
        print("(no bodies — lab body init --kind lab --name grok-home)")
        return 0
    for r in rows:
        print("%s  kind=%s  project=%s" % (r.get("body_id"), r.get("kind"), r.get("project_key")))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = BodyStore()
    body = store.load(args.body_id) or store.load("project:%s" % args.body_id) or store.load(
        "lab:%s" % args.body_id
    )
    if not body:
        print("error: body not found: %s" % args.body_id, file=sys.stderr)
        return 1
    if args.json:
        _print_json(body.to_dict())
        return 0
    d = body.to_dict()
    print("body_id:   %s" % d["body_id"])
    print("kind:      %s" % d["kind"])
    print("name:      %s" % d["name"])
    print("repo:      %s" % (d.get("identity") or {}).get("repo_path"))
    print("mode_cap:  %s" % (d.get("limits") or {}).get("mode_cap"))
    print("organs:    %s" % ", ".join(d.get("organs") or []))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = BodyStore()
    bid = args.body_id
    body = store.load(bid) or store.load("project:%s" % bid) or store.load("lab:%s" % bid)
    if not body:
        print("error: body not found: %s" % bid, file=sys.stderr)
        return 1
    open_obl = list_obligations(body.body_id, status="open", store=store)
    events = list_events(body.body_id, limit=5, store=store)
    print("═══ Body status ═══")
    print("body_id:        %s" % body.body_id)
    print("kind/name:      %s / %s" % (body.kind, body.name))
    print("mode_cap:       %s" % body.limits.mode_cap)
    print("budget_day:     %s" % body.limits.budget_tokens_day)
    print("organs:         %s" % ", ".join(body.organs))
    print("open_obligations: %d" % len(open_obl))
    for o in open_obl[:5]:
        print("  - %s %s" % (o.get("id"), o.get("summary")))
    print("recent_events:  %d" % len(events))
    for e in events[:5]:
        print("  - %s %s/%s" % (e.get("id"), e.get("channel"), e.get("type")))
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    info = resolve_info(body=args.body, project=args.project, cwd=args.cwd)
    if args.json:
        _print_json(info)
        return 0 if info.get("resolved") else 1
    if not info.get("resolved"):
        print("resolved: false")
        return 1
    print("resolved:  true")
    print("body_id:   %s" % info["body_id"])
    print("kind:      %s" % info["kind"])
    print("mode_cap:  %s" % info["mode_cap"])
    return 0


def cmd_ledger_list(args: argparse.Namespace) -> int:
    rows = list_obligations(args.body_id, status=args.status, limit=args.limit)
    if args.json:
        _print_json(rows)
        return 0
    for r in rows:
        print("%s  [%s] %s" % (r.get("id"), r.get("status"), r.get("summary")))
    return 0


def cmd_ledger_close(args: argparse.Namespace) -> int:
    ok = close_obligation(args.body_id, args.obl_id, outcome=args.outcome)
    if not ok:
        print("error: obligation not found", file=sys.stderr)
        return 1
    print("closed %s" % args.obl_id)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    payload: Dict[str, Any] = {}
    if args.payload_json:
        payload = json.loads(args.payload_json)
    ev = ingest(args.body_id, args.channel, args.type, payload)
    print("event: %s channel=%s type=%s" % (ev["id"], ev["channel"], ev["type"]))
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    rows = list_events(args.body_id, limit=args.limit)
    if args.json:
        _print_json(rows)
        return 0
    for r in rows:
        print("%s  %s/%s  %s" % (r.get("id"), r.get("channel"), r.get("type"), r.get("payload")))
    return 0


def cmd_organs(args: argparse.Namespace) -> int:
    from body.organs import ensure_default_organs

    if getattr(args, "grow", False):
        b = ensure_default_organs(args.body_id)
        print("organs: grew defaults for %s" % args.body_id)
    else:
        b = load_bindings(args.body_id)
    if args.json:
        _print_json(b)
        return 0
    for name, binding in b.items():
        en = "on" if binding.get("enabled", True) else "off"
        nproc = len(binding.get("procedures") or [])
        print("%s  [%s] procedures=%d" % (name, en, nproc))
        for proc in binding.get("procedures") or []:
            mind = "mind" if proc.get("mind") else "mind=false"
            print("    - %s  trigger=%s  %s" % (proc.get("id"), proc.get("trigger"), mind))
    return 0


def cmd_kpi(args: argparse.Namespace) -> int:
    from body.kpis import body_kpis, all_body_kpis, waste_report

    if args.waste:
        rep = waste_report()
        if args.json:
            _print_json(rep)
            return 0
        print("═══ Waste / mode mix ═══")
        print("totals: %s" % rep.get("totals"))
        for rec in rep.get("recommendations") or []:
            print("  · %s" % rec)
        for b in rep.get("by_body") or []:
            tok = b.get("tokens") or {}
            print(
                "%s  completed=%s success=%s by_mode=%s avg_tok=%s"
                % (
                    b.get("body_id"),
                    tok.get("n_completed"),
                    tok.get("n_success"),
                    tok.get("by_mode"),
                    tok.get("avg_tokens_per_success"),
                )
            )
        return 0
    if args.body_id in (None, "all", "*"):
        rows = all_body_kpis()
        if args.json:
            _print_json(rows)
            return 0
        for k in rows:
            _print_kpi_human(k)
        return 0
    k = body_kpis(args.body_id)
    if args.json:
        _print_json(k)
        return 0
    _print_kpi_human(k)
    return 0


def _print_kpi_human(k: Dict[str, Any]) -> None:
    print("═══ Body KPI %s ═══" % k.get("body_id"))
    if k.get("error"):
        print("error: %s" % k["error"])
        return
    print("forge:     ok=%s fail=%s" % ((k.get("forge") or {}).get("ok"), (k.get("forge") or {}).get("fail")))
    print("research:  %s" % k.get("research"))
    print("open_obl:  %s" % k.get("open_obligations"))
    print("budget:    %s" % k.get("budget"))
    tok = k.get("tokens") or {}
    print(
        "tokens:    completed=%s success=%s avg/success=%s by_mode=%s"
        % (tok.get("n_completed"), tok.get("n_success"), tok.get("avg_tokens_per_success"), tok.get("by_mode"))
    )


def cmd_outcomes(args: argparse.Namespace) -> int:
    from body.outcomes import scorecard, all_scorecards

    if args.body_id in (None, "all", "*"):
        rows = all_scorecards()
        if args.json:
            _print_json(rows)
            return 0
        print("═══ Body outcome scorecards ═══")
        print("(north-star: human outcomes / shipped proofs, not module count)")
        for s in sorted(rows, key=lambda x: -float(x.get("score") or 0)):
            print(
                "%s  grade=%s score=%.1f  showroom=%s forge=%s/%s open_obl=%s"
                % (
                    s.get("body_id"),
                    s.get("grade"),
                    float(s.get("score") or 0),
                    len((s.get("proofs") or {}).get("showroom_entries") or []),
                    (s.get("proofs") or {}).get("forge_ok"),
                    (s.get("proofs") or {}).get("forge_fail"),
                    (s.get("proofs") or {}).get("open_obligations"),
                )
            )
        return 0
    s = scorecard(args.body_id)
    if args.json:
        _print_json(s)
        return 0
    print("═══ Outcome scorecard ═══")
    print("body:   %s" % s.get("body_id"))
    print("grade:  %s  score=%.1f" % (s.get("grade"), float(s.get("score") or 0)))
    print("proofs: %s" % json.dumps(s.get("proofs"), indent=2))
    return 0


def cmd_factory(args: argparse.Namespace) -> int:
    """Run body-scoped validation (mind=false standing path): forge unittest."""
    import subprocess
    from body.store import BodyStore
    from body.organs import ensure_default_organs
    from body.events import ingest

    store = BodyStore()
    body = store.load(args.body_id) or store.load("project:%s" % args.body_id)
    if not body:
        print("error: body not found: %s" % args.body_id, file=sys.stderr)
        return 1
    ensure_default_organs(body.body_id, store)
    repo = (body.identity or {}).get("repo_path")
    if not repo or not Path(repo).expanduser().is_dir():
        print("error: body has no repo_path", file=sys.stderr)
        return 2
    cwd = str(Path(repo).expanduser())
    meta_cmd = ((body.meta or {}).get("validation_cmd") or "").strip()
    cmd = args.cmd or meta_cmd or "python3 -m unittest discover -s tests -q"
    print("factory: body=%s cwd=%s" % (body.body_id, cwd))
    print("factory: cmd=%s" % cmd)
    # Prefer lab forge when available for ledger dual-write
    argv = [
        "lab",
        "forge",
        "run",
        "--exp",
        body.name,
        "--project",
        body.project_key() or body.name,
        "--",
    ] + cmd.split()
    env = os.environ.copy()
    env["GROK_BODY"] = body.body_id
    env["GROK_PROJECT"] = body.project_key() or body.name
    try:
        r = subprocess.run(argv, cwd=cwd, env=env)
        ec = int(r.returncode)
    except FileNotFoundError:
        r = subprocess.run(cmd, shell=True, cwd=cwd, env=env)
        ec = int(r.returncode)
        ingest(
            body.body_id,
            channel="forge_exit",
            type_="completed" if ec == 0 else "nonzero",
            payload={"exit_code": ec, "exp": body.name, "source": "body_factory"},
        )
    print("factory: exit=%s" % ec)
    return ec


def _lab_bin() -> str:
    env = os.environ.get("LAB_BIN")
    if env and Path(env).is_file():
        return env
    home_lab = Path.home() / ".local" / "bin" / "lab"
    if home_lab.is_file():
        return str(home_lab)
    # modules/body/cli.py → repo bin/lab
    repo_lab = Path(__file__).resolve().parents[2] / "bin" / "lab"
    if repo_lab.is_file():
        return str(repo_lab)
    return "lab"


def _run_lab(
    argv: List[str], *, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None
) -> "subprocess.CompletedProcess[str]":
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run([_lab_bin()] + argv, cwd=cwd, env=e, text=True, capture_output=True)


def cmd_loop(args: argparse.Namespace) -> int:
    """One-shot operate path: route → research → factory → complete (+ optional showroom)."""
    import re

    store = BodyStore()
    body = store.load(args.body_id) or store.load("project:%s" % args.body_id)
    if not body:
        print("error: body not found: %s" % args.body_id, file=sys.stderr)
        return 1
    repo = (body.identity or {}).get("repo_path")
    if not repo or not Path(repo).expanduser().is_dir():
        print("error: body has no repo_path", file=sys.stderr)
        return 2
    cwd = str(Path(repo).expanduser())
    goal = (args.goal or "").strip()
    if not goal:
        print("error: --goal is required", file=sys.stderr)
        return 2

    env = {
        "GROK_BODY": body.body_id,
        "GROK_PROJECT": body.project_key() or body.name,
    }
    print("═══ lab body loop ═══")
    print("body:  %s" % body.body_id)
    print("repo:  %s" % cwd)
    print("goal:  %s" % goal)

    # 1) tokens route with explicit body
    r = _run_lab(
        ["tokens", "route", goal, "--body", body.body_id, "--project", body.project_key() or body.name],
        cwd=cwd,
        env=env,
    )
    sys.stdout.write(r.stdout or "")
    if r.stderr:
        sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print("error: tokens route failed", file=sys.stderr)
        return int(r.returncode)
    audit_id = None
    mode = "short"
    m = re.search(r"audit_id:\s*(\S+)", r.stdout or "")
    if m:
        audit_id = m.group(1)
    mm = re.search(r"mode:\s+(\S+)", r.stdout or "")
    if mm:
        mode = mm.group(1)

    research_id = None
    if not args.no_research:
        rargv = [
            "research",
            "start",
            goal,
            "--repo",
            cwd,
            "--mode",
            mode or "short",
        ]
        if audit_id:
            rargv += ["--token-audit-id", audit_id]
        rr = _run_lab(rargv, cwd=cwd, env=env)
        sys.stdout.write(rr.stdout or "")
        if rr.stderr:
            sys.stderr.write(rr.stderr)
        rm = re.search(r"started id=(\S+)", rr.stdout or "")
        if rm:
            research_id = rm.group(1)

    # 2) factory
    class _A:
        pass

    fac_args = _A()
    fac_args.body_id = body.body_id
    fac_args.cmd = args.cmd
    fac_ec = cmd_factory(fac_args)

    success = "yes" if fac_ec == 0 else "no"
    if research_id:
        cargv = [
            "research",
            "complete",
            research_id,
            "--success",
            success,
            "--tests-passed",
            success,
        ]
        if args.tokens is not None:
            cargv += ["--actual-tokens", str(int(args.tokens))]
        cargv += ["--notes", "body loop factory_exit=%s" % fac_ec]
        rc = _run_lab(cargv, cwd=cwd, env=env)
        sys.stdout.write(rc.stdout or "")
        if rc.stderr:
            sys.stderr.write(rc.stderr)

    if audit_id and args.tokens is not None:
        targv = [
            "tokens",
            "complete",
            "--audit-id",
            audit_id,
            "--actual-tokens",
            str(int(args.tokens)),
            "--success",
            success,
            "--body",
            body.body_id,
            "--project",
            body.project_key() or body.name,
        ]
        if args.quality is not None:
            targv += ["--quality", str(args.quality)]
        tc = _run_lab(targv, cwd=cwd, env=env)
        sys.stdout.write(tc.stdout or "")
        if tc.stderr:
            sys.stderr.write(tc.stderr)
    elif audit_id:
        print("loop: skip tokens complete (pass --tokens N to join audit %s)" % audit_id)

    if args.publish and not args.no_showroom:
        title = "body loop: %s" % (goal[:60] + ("…" if len(goal) > 60 else ""))
        sc = _run_lab(
            [
                "showroom",
                "capture",
                "--manual",
                "--title",
                title,
                "--project",
                body.project_key() or body.name,
                "--kind",
                "experiment",
                "--summary",
                "factory_exit=%s research=%s audit=%s" % (fac_ec, research_id, audit_id),
                "--proof",
                "lab body factory %s" % body.body_id,
                "--publish",
            ],
            cwd=cwd,
            env=env,
        )
        sys.stdout.write(sc.stdout or "")
        if sc.stderr:
            sys.stderr.write(sc.stderr)

    print("─── loop summary ───")
    print("body:        %s" % body.body_id)
    print("audit_id:    %s" % (audit_id or "(none)"))
    print("research_id: %s" % (research_id or "(skipped)"))
    print("factory:     exit=%s" % fac_ec)
    if args.json:
        print(
            json.dumps(
                {
                    "body_id": body.body_id,
                    "audit_id": audit_id,
                    "research_id": research_id,
                    "factory_exit": fac_ec,
                    "success": fac_ec == 0,
                },
                indent=2,
            )
        )
    return int(fac_ec)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lab body", description="Body registry (identity/property/contact/limits)")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="Create body registry entry")
    i.add_argument("--kind", choices=["lab", "project", "system"], required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--repo", default=None)
    i.add_argument("--mode-cap", default="medium")
    i.add_argument("--budget-day", type=int, default=100_000)
    i.add_argument(
        "--validation-cmd",
        default=None,
        help="Standing factory command (stored on body.meta)",
    )
    i.set_defaults(func=cmd_init)

    ls = sub.add_parser("list", help="List bodies")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="Show body.json")
    sh.add_argument("body_id")
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    st = sub.add_parser("status", help="Organs + open obligations")
    st.add_argument("body_id")
    st.set_defaults(func=cmd_status)

    rs = sub.add_parser("resolve", help="KD-B16 resolve")
    rs.add_argument("--body", default=None)
    rs.add_argument("--project", default=None)
    rs.add_argument("--cwd", default=None)
    rs.add_argument("--json", action="store_true")
    rs.set_defaults(func=cmd_resolve)

    ll = sub.add_parser("ledger", help="Obligations ledger")
    ll_sub = ll.add_subparsers(dest="ledger_cmd", required=True)
    llist = ll_sub.add_parser("list")
    llist.add_argument("body_id")
    llist.add_argument("--status", default=None)
    llist.add_argument("--limit", type=int, default=50)
    llist.add_argument("--json", action="store_true")
    llist.set_defaults(func=cmd_ledger_list)
    lclose = ll_sub.add_parser("close")
    lclose.add_argument("body_id")
    lclose.add_argument("obl_id")
    lclose.add_argument("--outcome", required=True)
    lclose.set_defaults(func=cmd_ledger_close)

    ing = sub.add_parser("ingest", help="Contact ingest")
    ing.add_argument("body_id")
    ing.add_argument("--channel", required=True)
    ing.add_argument("--type", required=True)
    ing.add_argument("--payload-json", default=None)
    ing.set_defaults(func=cmd_ingest)

    ev = sub.add_parser("events", help="List contact events")
    ev.add_argument("body_id")
    ev.add_argument("--limit", type=int, default=20)
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=cmd_events)

    org = sub.add_parser("organs", help="List organ bindings")
    org.add_argument("body_id")
    org.add_argument("--json", action="store_true")
    org.add_argument("--grow", action="store_true", help="Merge default standing procedures")
    org.set_defaults(func=cmd_organs)

    kpi = sub.add_parser("kpi", help="Tokens/success and forge KPIs for a body")
    kpi.add_argument("body_id", nargs="?", default="all")
    kpi.add_argument("--waste", action="store_true", help="Cross-body waste / mode mix report")
    kpi.add_argument("--json", action="store_true")
    kpi.set_defaults(func=cmd_kpi)

    outc = sub.add_parser("outcomes", help="Human outcome scorecards (proofs, not modules)")
    outc.add_argument("body_id", nargs="?", default="all")
    outc.add_argument("--json", action="store_true")
    outc.set_defaults(func=cmd_outcomes)

    fac = sub.add_parser("factory", help="Body-scoped forge/unittest (mind=false standing path)")
    fac.add_argument("body_id")
    fac.add_argument("--cmd", default=None, help="Override validation command")
    fac.set_defaults(func=cmd_factory)

    loop = sub.add_parser(
        "loop",
        help="One-shot operate: route → research → factory → complete",
    )
    loop.add_argument("body_id", help="e.g. project:pulse-board")
    loop.add_argument("--goal", required=True, help="Task goal string")
    loop.add_argument("--cmd", default=None, help="Factory validation override")
    loop.add_argument("--tokens", type=int, default=None, help="Actual tokens for complete join")
    loop.add_argument("--quality", type=float, default=None, help="0..1 quality for tokens complete")
    loop.add_argument("--no-research", action="store_true", help="Skip research start/complete")
    loop.add_argument("--no-showroom", action="store_true", help="Skip showroom even with --publish")
    loop.add_argument("--publish", action="store_true", help="Capture + publish showroom entry")
    loop.add_argument("--json", action="store_true")
    loop.set_defaults(func=cmd_loop)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

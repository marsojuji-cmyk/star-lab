#!/usr/bin/env python3
"""lab research — golden workflow logger + Loop 4 KPIs (10× research sprint)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "modules"))

from research.logstore import ResearchLog
from research.kpi_board import write_kpi_board
from research.packet import create_packet, load_packet
from research.recover import recover


def _load_route(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_start(args: argparse.Namespace) -> int:
    log = ResearchLog()
    mode = args.mode or ""
    horizon = args.horizon
    ev = args.ev
    audit_id = args.token_audit_id or ""
    risk = args.risk
    pack: Dict[str, Any] = {}
    packet_id = ""

    route = _load_route(args.route_json)
    if route:
        mode = mode or route.get("mode") or ""
        horizon = horizon if horizon is not None else route.get("predicted_horizon")
        ev = ev if ev is not None else route.get("expected_value")
        audit_id = audit_id or route.get("audit_id") or ""
        pack = dict(route.get("packing") or {})

    if args.packet:
        try:
            pkt = load_packet(args.packet)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        packet_id = str(pkt.get("id") or "")
        mode = mode or pkt.get("mode") or ""
        horizon = horizon if horizon is not None else pkt.get("predicted_horizon")
        ev = ev if ev is not None else pkt.get("route_ev")
        audit_id = audit_id or pkt.get("token_audit_id") or ""
        if risk is None and pkt.get("risk_score") is not None:
            risk = pkt.get("risk_score")
        # Prefer packet goal/repo when caller left defaults empty
        goal = args.goal or pkt.get("task_goal") or ""
        repo = args.repo or pkt.get("repo") or ""
        pack = {
            **pack,
            **(pkt.get("packing") or {}),
            "packet_id": packet_id,
            "files": pkt.get("files") or [],
            "failing_tests": pkt.get("failing_tests") or "",
            "validation_requirements": pkt.get("validation_requirements") or [],
            "token_budget": pkt.get("token_budget"),
            "user_priority": pkt.get("user_priority"),
            "route": pkt.get("route") or {},
        }
    else:
        goal = args.goal
        repo = args.repo or ""

    if not goal:
        print("error: goal required (positional or from --packet)", file=sys.stderr)
        return 2

    tid = log.start(
        goal,
        repo=repo,
        mode=mode,
        token_audit_id=audit_id,
        predicted_horizon=horizon,
        route_ev=ev,
        risk_score=risk,
        context_pack=pack,
    )
    if packet_id:
        log.attach_context_pack(tid, {"id": packet_id, **pack})

    if args.json:
        print(
            json.dumps(
                {
                    "id": tid,
                    "status": "open",
                    "task_goal": goal,
                    "packet_id": packet_id or None,
                }
            )
        )
    else:
        print(f"research: started id={tid}")
        print(f"  goal: {goal}")
        if packet_id:
            print(f"  packet: {packet_id}")
        print(f"  complete with: lab research complete {tid} --success yes|no ...")
    return 0


def cmd_packet(args: argparse.Namespace) -> int:
    """Create or show a context packet (Loop 1 structured escalate)."""
    if args.packet_cmd == "show":
        try:
            pkt = load_packet(args.id)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(pkt, indent=2))
        else:
            md = Path(pkt.get("md_path") or "")
            if md.is_file():
                print(md.read_text(encoding="utf-8"), end="")
            else:
                from research.packet import render_markdown

                print(render_markdown(pkt), end="")
        return 0

    # create (default)
    route = _load_route(args.route_json)
    files = list(args.file or [])
    reqs = list(args.require or []) or None
    pkt = create_packet(
        args.goal,
        repo=args.repo or "",
        files=files,
        route=route,
        failing_tests=args.failing_tests or "",
        validation_requirements=reqs,
        risk_score=args.risk,
        user_priority=args.priority or "normal",
        notes=args.notes or "",
    )
    if args.task_id:
        log = ResearchLog()
        try:
            log.attach_context_pack(
                args.task_id,
                {
                    "id": pkt["id"],
                    "files": pkt.get("files"),
                    "failing_tests": pkt.get("failing_tests"),
                    "validation_requirements": pkt.get("validation_requirements"),
                    "token_budget": pkt.get("token_budget"),
                    "route": pkt.get("route"),
                    "packing": pkt.get("packing"),
                    "md_path": pkt.get("md_path"),
                    "path": pkt.get("path"),
                },
            )
        except KeyError:
            print(
                f"error: unknown task id {args.task_id} (packet still saved)",
                file=sys.stderr,
            )
            return 2

    if args.json:
        print(json.dumps(pkt, indent=2))
    else:
        print(f"research: packet id={pkt['id']}")
        print(f"  json: {pkt['path']}")
        print(f"  md:   {pkt['md_path']}")
        if args.task_id:
            print(f"  attached to task: {args.task_id}")
        print(f"  escalate with: cat {pkt['md_path']}")
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    """LEAD-style short-horizon recovery on an open research task."""
    cmd = args.cmd
    try:
        result = recover(
            args.id,
            cmd_str=cmd,
            cwd=args.cwd,
            timeout=float(args.timeout),
        )
    except KeyError:
        print(f"error: unknown task id: {args.id}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: recovery failed: {e}", file=sys.stderr)
        return 1

    d = result.to_dict()
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print(f"research: recovery on {result.task_id}")
        print(f"  retried: {result.retried} retry_ok={result.retry_ok}")
        print(f"  cmd: {result.cmd}")
        print("  plan:")
        for line in result.plan:
            print(f"    - {line}")
        if result.notes:
            print("  notes (tail):")
            for line in result.notes.strip().splitlines()[-8:]:
                print(f"    {line}")
        if result.retry_ok is True:
            print(
                f"  next: lab research complete {result.task_id} "
                "--success yes --recovery ..."
            )
        elif result.retry_ok is False:
            print(
                "  next: lab research packet \"…\" --failing-tests \"…\" "
                f"--task-id {result.task_id}"
            )
    # exit 0 if retry ok or no retry needed path; 1 if still failing
    if result.retry_ok is False:
        return 1
    return 0


def cmd_action(args: argparse.Namespace) -> int:
    log = ResearchLog()
    log.action(args.id, type=args.type, name=args.name, ok=not args.fail, notes=args.notes or "")
    print(f"research: action logged on {args.id}")
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    log = ResearchLog()
    success = args.success == "yes"
    # Optional SQC gate reminder
    if args.require_sqc and args.sqc_quality_ok != "yes":
        print(
            "error: --require-sqc set but --sqc-quality-ok is not yes "
            "(run lab sqc loop and pass quality first)",
            file=sys.stderr,
        )
        return 2
    p = log.complete(
        args.id,
        success=success,
        actual_tokens=args.actual_tokens,
        tests_passed=(
            None
            if args.tests_passed is None
            else args.tests_passed == "yes"
        ),
        sqc_loop_id=args.sqc_loop_id,
        sqc_quality_ok=(
            None
            if args.sqc_quality_ok is None
            else args.sqc_quality_ok == "yes"
        ),
        recovery_triggered=args.recovery,
        recovery_notes=args.recovery_notes or "",
        human_interruptions=args.human_interruptions,
        notes=args.notes or "",
    )
    if args.json:
        print(json.dumps(p, indent=2))
    else:
        print(
            f"research: completed id={args.id} success={success} "
            f"tokens={p.get('actual_tokens')} latency_s={p['metrics'].get('latency_s')}"
        )
    # refresh KPI board
    write_kpi_board()
    return 0 if success else 1


def cmd_list(args: argparse.Namespace) -> int:
    log = ResearchLog()
    rows = log.list(limit=args.limit, status=args.status)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            oc = r.get("outcome") or {}
            print(
                f"{r['id']} {r['status']:10} success={oc.get('success')} "
                f"mode={r.get('mode')} goal={r.get('task_goal','')[:60]}"
            )
    return 0


def cmd_kpi(args: argparse.Namespace) -> int:
    log = ResearchLog()
    k = log.kpi()
    path = write_kpi_board(k)
    if args.json:
        print(json.dumps(k, indent=2))
    else:
        def fmt(x):
            if x is None:
                return "n/a"
            if isinstance(x, float):
                return f"{x:.3f}"
            return str(x)

        print("═══ Research KPIs (Loop 4) ═══")
        print(f"completed logs:           {k.get('n_completed_logs')}")
        print(f"accepted_patch_rate:      {fmt(k.get('accepted_patch_rate'))}")
        print(f"test_pass_rate:           {fmt(k.get('test_pass_rate'))}")
        print(f"avg_tokens_per_success:   {fmt(k.get('average_tokens_per_success'))}")
        print(f"recovery_rate:            {fmt(k.get('recovery_rate_after_failure'))}")
        print(f"latency_per_task_s:       {fmt(k.get('latency_per_completed_task_s'))}")
        print(f"human_interruptions_avg:  {fmt(k.get('human_interruptions_avg'))}")
        print(f"sqc_pass_rate (tasks):    {fmt(k.get('sqc_pass_rate'))}")
        print(f"sqc_loop_accept_rate:     {fmt(k.get('sqc_loop_accept_rate'))}")
        print(f"sqc_loops_total:          {k.get('sqc_loops_total')}")
        print(f"last_sqc_decision:        {k.get('last_sqc_decision')}")
        ts = k.get("token_audit_stats") or {}
        print(f"token audits n:           {ts.get('n')}")
        print(f"token horizon MAE:        {fmt(ts.get('mae'))}")
        print(f"board: {path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lab research", description="Golden workflow research log")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="Start instrumented task log")
    s.add_argument("goal", nargs="?", default="", help="Task goal string (optional if --packet)")
    s.add_argument("--repo", default="")
    s.add_argument("--mode", default="")
    s.add_argument("--token-audit-id", default="")
    s.add_argument("--horizon", type=int, default=None)
    s.add_argument("--ev", type=float, default=None)
    s.add_argument("--risk", type=float, default=None)
    s.add_argument("--route-json", help="Path to lab tokens route --json output")
    s.add_argument("--packet", help="Context packet id or path (Loop 1)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_start)

    a = sub.add_parser("action", help="Log an action on an open task")
    a.add_argument("id")
    a.add_argument("--type", default="tool", choices=["tool", "local", "grok", "validate", "other"])
    a.add_argument("--name", required=True)
    a.add_argument("--fail", action="store_true")
    a.add_argument("--notes", default="")
    a.set_defaults(func=cmd_action)

    c = sub.add_parser("complete", help="Complete a task log")
    c.add_argument("id")
    c.add_argument("--success", required=True, choices=["yes", "no"])
    c.add_argument("--actual-tokens", type=int, default=None)
    c.add_argument("--tests-passed", choices=["yes", "no"], default=None)
    c.add_argument("--sqc-loop-id", default=None)
    c.add_argument("--sqc-quality-ok", choices=["yes", "no"], default=None)
    c.add_argument("--require-sqc", action="store_true", help="Refuse complete success without SQC ok")
    c.add_argument("--recovery", action="store_true")
    c.add_argument("--recovery-notes", default="")
    c.add_argument("--human-interruptions", type=int, default=0)
    c.add_argument("--notes", default="")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_complete)

    l = sub.add_parser("list", help="List recent task logs")
    l.add_argument("--limit", type=int, default=20)
    l.add_argument("--status", choices=["open", "completed", "aborted"], default=None)
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    k = sub.add_parser("kpi", help="Loop 4 KPI board")
    k.add_argument("--json", action="store_true")
    k.set_defaults(func=cmd_kpi)

    # packet create | show
    pk = sub.add_parser("packet", help="Context packets for disciplined Grok escalate (Loop 1)")
    pk_sub = pk.add_subparsers(dest="packet_cmd", required=True)

    pk_c = pk_sub.add_parser("create", help="Create a context packet")
    pk_c.add_argument("goal", help="Escalation goal")
    pk_c.add_argument("--repo", default="")
    pk_c.add_argument("--file", action="append", default=[], help="Top file path (repeatable)")
    pk_c.add_argument("--route-json", help="lab tokens route --json file")
    pk_c.add_argument("--failing-tests", default="", help="Failing test output / summary")
    pk_c.add_argument("--require", action="append", default=[], help="Validation requirement")
    pk_c.add_argument("--risk", type=float, default=None)
    pk_c.add_argument("--priority", default="normal", choices=["low", "normal", "high"])
    pk_c.add_argument("--notes", default="")
    pk_c.add_argument("--task-id", help="Attach packet to open research task")
    pk_c.add_argument("--json", action="store_true")
    pk_c.set_defaults(func=cmd_packet, packet_cmd="create")

    pk_s = pk_sub.add_parser("show", help="Show packet by id or path")
    pk_s.add_argument("id", help="Packet id or path")
    pk_s.add_argument("--json", action="store_true")
    pk_s.set_defaults(func=cmd_packet, packet_cmd="show")

    r = sub.add_parser("recover", help="LEAD short-horizon recovery (Loop 2)")
    r.add_argument("id", help="Open research task id")
    r.add_argument(
        "--cmd",
        default=None,
        help='Validation command to re-run once (default: python3 -m unittest discover -s tests -q)',
    )
    r.add_argument("--cwd", default=None)
    r.add_argument("--timeout", type=float, default=120.0)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_recover)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""lab research — golden workflow logger + Loop 4 KPIs (10× research sprint)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "modules"))

from research.logstore import ResearchLog
from research.kpi_board import write_kpi_board


def cmd_start(args: argparse.Namespace) -> int:
    log = ResearchLog()
    # optional: pull latest tokens route if --route-json
    mode = args.mode or ""
    horizon = args.horizon
    ev = args.ev
    audit_id = args.token_audit_id or ""
    if args.route_json:
        d = json.loads(Path(args.route_json).read_text(encoding="utf-8"))
        mode = mode or d.get("mode") or ""
        horizon = horizon if horizon is not None else d.get("predicted_horizon")
        ev = ev if ev is not None else d.get("expected_value")
        audit_id = audit_id or d.get("audit_id") or ""
        pack = d.get("packing") or {}
    else:
        pack = {}
    tid = log.start(
        args.goal,
        repo=args.repo or "",
        mode=mode,
        token_audit_id=audit_id,
        predicted_horizon=horizon,
        route_ev=ev,
        risk_score=args.risk,
        context_pack=pack,
    )
    if args.json:
        print(json.dumps({"id": tid, "status": "open", "task_goal": args.goal}))
    else:
        print(f"research: started id={tid}")
        print(f"  goal: {args.goal}")
        print(f"  complete with: lab research complete {tid} --success yes|no ...")
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
    s.add_argument("goal", help="Task goal string")
    s.add_argument("--repo", default="")
    s.add_argument("--mode", default="")
    s.add_argument("--token-audit-id", default="")
    s.add_argument("--horizon", type=int, default=None)
    s.add_argument("--ev", type=float, default=None)
    s.add_argument("--risk", type=float, default=None)
    s.add_argument("--route-json", help="Path to lab tokens route --json output")
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

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""lab tokens — Token-Aware Control Plane CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Allow running as python3 modules/tokens/cli.py
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "modules") not in sys.path:
    sys.path.insert(0, str(_ROOT / "modules"))
if str(_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_ROOT / "lib"))

import os

from tokens.policy import route_task, annotate_task, MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP
from tokens.audit import AuditStore
from tokens.distill import distill_rules
from tokens.shadow import ShadowStore
from tokens.session_lock import apply_lock_to_route, acquire_lock, release_lock, get_lock
from tokens.gates import (
    evaluate_graduation,
    load_canary,
    load_data_bar,
)
from tokens.eval_router import eval_frozen, eval_drift, freeze_baseline
from tokens import rollout as rollout_mod


def _print_decision(d, as_json: bool) -> None:
    if as_json:
        print(json.dumps(d.to_dict(), indent=2))
        return
    print("═══ Token-Aware Route ═══")
    print(f"mode:              {d.mode}")
    print(f"budget_tokens:     {d.budget_tokens}")
    print(f"predicted_horizon: {d.predicted_horizon}")
    print(f"confidence:        {d.confidence}")
    print(f"expected_reward:   {d.expected_reward:.3f}")
    print(f"predicted_cost:    {d.predicted_cost:.4f}")
    print(f"expected_value:    {d.expected_value:.4f}")
    print(f"local_EV:          {d.local_expected_value:.4f}")
    print(f"escalate:          {d.escalate}")
    print("packing:")
    for k, v in d.packing.items():
        print(f"  {k}: {v}")
    print("reasons:")
    for r in d.reasons:
        print(f"  - {r}")
    print("drivers (length regime):")
    for dr in d.annotation.horizon.drivers:
        print(f"  - {dr.get('token_or_pattern')}: Δ={dr.get('delta_tokens')} → {dr.get('regime')}")
    if not d.annotation.horizon.drivers:
        print("  (none)")
    print(f"horizon_method: {d.annotation.horizon.method}")
    print(f"notes: {d.annotation.horizon.notes}")


def cmd_route(args: argparse.Namespace) -> int:
    task = args.task
    if args.file:
        task = Path(args.file).read_text(encoding="utf-8")
    if not task or not str(task).strip():
        print("error: empty task", file=sys.stderr)
        return 2
    # Session lock: pin mode mid tool-loop unless --force-mode (escape hatch)
    lock_info = apply_lock_to_route(
        args.force_mode or "", force_mode=args.force_mode
    )
    force = args.force_mode
    if (
        lock_info.get("locked")
        and not lock_info.get("override")
        and lock_info.get("lock", {}).get("locked_mode")
    ):
        force = lock_info["lock"]["locked_mode"]
    d = route_task(
        str(task),
        context_chars=args.context_chars,
        force_mode=force,
    )
    store = AuditStore()
    aid = store.log_route(
        task=str(task)[:500],
        mode=d.mode,
        predicted_horizon=d.predicted_horizon,
        budget_tokens=d.budget_tokens,
        expected_value=d.expected_value,
        drivers=d.annotation.horizon.drivers,
        notes="route",
    )
    # L1 shadow dual-log (log-only). Default mirror = same policy (instrumentation).
    # Later: shadow can use alternate scorer without serving it.
    shadow_id = None
    if not getattr(args, "no_shadow", False) and os.environ.get("GROK_TOKEN_SHADOW", "1") != "0":
        try:
            served = d.to_dict()
            # optional alternate force for shadow experiments
            shadow_force = getattr(args, "shadow_force_mode", None)
            if shadow_force:
                d_shadow = route_task(
                    str(task),
                    context_chars=args.context_chars,
                    force_mode=shadow_force,
                )
                shadow_dict = d_shadow.to_dict()
                policy_id = f"force_{shadow_force}"
            else:
                shadow_dict = served
                policy_id = "heuristic_v1_mirror"
            shadow_id = ShadowStore().log(
                audit_id=aid,
                task=str(task)[:500],
                served={
                    "mode": d.mode,
                    "predicted_horizon": d.predicted_horizon,
                    "budget_tokens": d.budget_tokens,
                    "expected_value": d.expected_value,
                },
                shadow={
                    "mode": shadow_dict.get("mode"),
                    "predicted_horizon": shadow_dict.get("predicted_horizon"),
                    "budget_tokens": shadow_dict.get("budget_tokens"),
                    "expected_value": shadow_dict.get("expected_value"),
                },
                shadow_policy_id=policy_id,
                session_id=os.environ.get("GROK_SESSION_ID", ""),
                tenant=os.environ.get("GROK_TENANT", "local"),
            )
        except Exception:
            shadow_id = None
    if args.json:
        out = d.to_dict()
        out["audit_id"] = aid
        if shadow_id:
            out["shadow_id"] = shadow_id
            out["policy_id"] = "heuristic_v1"
        if lock_info.get("locked"):
            out["session_lock"] = lock_info
        print(json.dumps(out, indent=2))
    else:
        _print_decision(d, as_json=False)
        print(f"audit_id: {aid}")
        if shadow_id:
            print(f"shadow_id: {shadow_id} (log-only)")
        if lock_info.get("locked"):
            print(f"session_lock: active reason={lock_info.get('lock', {}).get('reason')} "
                  f"mode={lock_info.get('mode')} ({lock_info.get('note')})")
    return 0


def cmd_shadow(args: argparse.Namespace) -> int:
    store = ShadowStore()
    if getattr(args, "shadow_cmd", None) == "compare" or getattr(args, "compare", False):
        out = rollout_mod.shadow_compare(limit=args.limit)
        print(json.dumps(out, indent=2))
        return 0 if out.get("similar_enough") else 1
    if args.stats or args.shadow_cmd == "stats":
        print(json.dumps(store.stats(), indent=2))
        return 0
    rows = store.recent(limit=args.limit)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(
                f"{r['id']} audit={r.get('audit_id')} "
                f"served={r.get('served_mode')} shadow={r.get('shadow_mode')} "
                f"policy={r.get('shadow_policy_id')}"
            )
    return 0


def cmd_annotate(args: argparse.Namespace) -> int:
    ann = annotate_task(args.task, context_chars=args.context_chars)
    print(json.dumps(ann.to_dict(), indent=2) if args.json else ann.to_dict())
    if not args.json:
        print(json.dumps(ann.to_dict(), indent=2))
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    store = AuditStore()
    store.complete(
        args.audit_id,
        actual_tokens=args.actual_tokens,
        outcome_quality=args.quality,
        success=None if args.success is None else (args.success == "yes"),
        notes=args.notes or "",
    )
    print(f"completed audit {args.audit_id}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    store = AuditStore()
    if args.stats:
        print(json.dumps(store.error_stats(), indent=2))
        return 0
    rows = store.recent(limit=args.limit)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(
                f"{r['id']} mode={r['mode']} pred={r['predicted_horizon']} "
                f"actual={r['actual_tokens']} q={r['outcome_quality']} "
                f"ev={r['expected_value']:.3f}"
            )
    return 0


def cmd_distill(args: argparse.Namespace) -> int:
    from tokens.distill import SQCGateError

    store = AuditStore()
    try:
        rules, gate = distill_rules(
            store,
            min_support=args.min_support,
            require_sqc=not args.ungated,
            allow_ungated=args.ungated,
        )
    except SQCGateError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = {"rules": rules, "sqc_gate": gate, "n_rules": len(rules)}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(json.dumps(rules, indent=2))
        print(
            f"# distilled {len(rules)} rule(s) · sqc_gate={gate}",
            file=sys.stderr,
        )
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    """Print the operating policy (forceful form)."""
    text = """
TOKEN AWARENESS IS THE OPERATING POLICY (Grok Star Lab / Grok Build)

1. Every task gets a predicted token horizon (LenVM-style value signal; free
   heuristic online, optional GROK_LENVM_CMD for trained probe).
2. Every call gets a budgeted mode: local | short | medium | deep.
3. Escalation must beat local-resolution EV: reward − λ·tokens.
   λ is a tunable control signal — not a blind day-one rule for all modes.
4. Cheap / ops tasks never consume deep budget.
5. Packing, retrieval_k, subagents, continuation are governed by mode.
6. Audit actual tokens vs outcome → distill rules → redeploy continuously.
7. Distill is gated by lab sqc loop (Loop 3) — quality_sufficient required.
8. Shadow dual-log on every route (log-only); serve baseline until gates pass.
9. Multi-agent: optimize context carriage (lab graph) under per-node budgets.
10. Four-stage rollout: shadow → canary 1–5% → ramp 10/25/50 → full.
11. Session locks pin mode during tool loops (no i.i.d. thrash mid-loop).
12. Graph circuit breakers isolate one bad agent/role.

CLI:
  lab tokens route "your task"
  lab tokens shadow compare
  lab tokens eval | gates
  lab tokens rollout status|start|check|advance|rollback|drill
  lab tokens session lock|unlock|status
  lab graph breaker trip|reset|status
  docs/research/CLOSED-LOOP-GATES.md
""".strip()
    print(text)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    frozen = eval_frozen()
    if args.freeze_baseline:
        path = freeze_baseline(frozen)
        print(f"froze baseline → {path}")
    if args.drift:
        out = eval_drift(frozen, window=args.window)
    else:
        out = frozen
        if not args.verbose and "items" in out:
            out = {k: v for k, v in out.items() if k != "items"}
            out["n_items_hidden"] = frozen.get("n")
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if args.drift:
            print("═══ Router drift (vs frozen baseline) ═══")
            print(f"n_shadow window:     {out.get('n_shadow')}")
            print(f"mode_mix:            {out.get('mode_mix')}")
            print(f"horizon_mae:         {out.get('horizon_mae')}")
            print(f"frozen_agreement:    {out.get('frozen_agreement')}")
            print(f"drift_detected:      {out.get('drift_detected')}")
            for f in out.get("flags") or []:
                print(f"  flag: {f}")
        else:
            print("═══ Frozen router golden (router_v1) ═══")
            print(f"n:                   {out.get('n')}")
            print(f"agreement:           {out.get('agreement')}")
            print(f"adjacent_agreement:  {out.get('adjacent_agreement')}")
            print(f"deep_violations:     {out.get('deep_violations')}")
            if out.get("error"):
                print(f"error: {out['error']}")
    return 0


def cmd_gates(args: argparse.Namespace) -> int:
    frozen = eval_frozen()
    agr = frozen.get("agreement")
    report = evaluate_graduation(golden_agreement=agr)
    d = report.to_dict()
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print("═══ Graduation gates (shadow → canary → online) ═══")
        print(f"ready_for_canary:  {report.ready_for_canary}")
        print(f"ready_for_online:  {report.ready_for_online}")
        print("checks:")
        for c in report.checks:
            mark = "✓" if c.ok else "✗"
            print(f"  {mark} {c.name:24} obs={c.observed} thr={c.threshold}  {c.detail}")
        print("DROP:")
        for line in report.drop_rules:
            print(f"  - {line}")
        print("order:", " → ".join(d["order"]))
    # exit 0 if canary-ready, 1 if not online, 2 if neither
    if report.ready_for_online:
        return 0
    if report.ready_for_canary:
        return 1
    return 2


def cmd_canary(args: argparse.Namespace) -> int:
    """Thin wrapper over four-stage rollout (compat)."""
    sub = args.canary_cmd
    if sub == "status" or sub is None:
        print(json.dumps(rollout_mod.status(), indent=2))
        return 0
    if sub == "propose":
        st = rollout_mod.propose(args.policy_id, notes=args.notes or "")
        print(json.dumps(st, indent=2))
        return 0
    if sub == "start":
        # mark shadow_ok then canary
        rollout_mod.mark_shadow_ok(force=args.force)
        res = rollout_mod.start_canary(
            frac=getattr(args, "traffic_frac", None),
            force=args.force,
            serve=getattr(args, "serve", False),
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 2
    if sub == "rollback":
        st = rollout_mod.rollback(reason=args.reason or "")
        print(json.dumps(st, indent=2))
        return 0
    if sub == "promote":
        # maps to advance (no jump to full)
        res = rollout_mod.advance(force=args.force)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 2
    print("error: unknown canary subcommand", file=sys.stderr)
    return 2


def cmd_rollout(args: argparse.Namespace) -> int:
    sub = args.rollout_cmd
    if sub == "status":
        print(json.dumps(rollout_mod.status(), indent=2))
        return 0
    if sub == "propose":
        st = rollout_mod.propose(args.policy_id, notes=args.notes or "")
        print(json.dumps(st, indent=2))
        return 0
    if sub == "shadow-ok":
        res = rollout_mod.mark_shadow_ok(force=args.force)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 2
    if sub == "start":
        if getattr(args, "policy_id", None):
            rollout_mod.propose(args.policy_id)
        rollout_mod.mark_shadow_ok(force=args.force)
        res = rollout_mod.start_canary(
            frac=args.frac, force=args.force, serve=args.serve
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 2
    if sub == "check":
        res = rollout_mod.check_and_maybe_rollback()
        print(json.dumps(res, indent=2))
        if res.get("rolled_back"):
            return 3
        return 0 if res.get("ok") else 1
    if sub == "advance":
        res = rollout_mod.advance(force=args.force)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 2
    if sub == "rollback":
        st = rollout_mod.rollback(reason=args.reason or "")
        print(json.dumps(st, indent=2))
        return 0
    if sub == "drill":
        res = rollout_mod.drill()
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    print("error: rollout status|propose|shadow-ok|start|check|advance|rollback|drill", file=sys.stderr)
    return 2


def cmd_session(args: argparse.Namespace) -> int:
    sub = args.session_cmd
    if sub == "status":
        lock = get_lock()
        out = {"active": bool(lock), "lock": lock}
        print(json.dumps(out, indent=2))
        return 0
    if sub == "lock":
        st = acquire_lock(
            reason=args.reason or "tool_loop",
            mode=args.mode,
            notes=args.notes or "",
        )
        print(json.dumps(st, indent=2))
        return 0
    if sub == "unlock":
        st = release_lock(force=args.force)
        print(json.dumps(st, indent=2))
        return 0
    print("error: session status|lock|unlock", file=sys.stderr)
    return 2


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(prog="lab tokens", description="Token-Aware Control Plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("route", help="Annotate + route a task")
    r.add_argument("task", nargs="?", default="", help="Task text")
    r.add_argument("--file", help="Read task from file")
    r.add_argument("--context-chars", type=int, default=0)
    r.add_argument("--force-mode", choices=[MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP])
    r.add_argument("--no-shadow", action="store_true", help="Skip shadow dual-log")
    r.add_argument(
        "--shadow-force-mode",
        choices=[MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP],
        help="Log-only alternate mode for shadow experiments",
    )
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_route)

    sh = sub.add_parser("shadow", help="Shadow dual-log status (L1)")
    sh_sub = sh.add_subparsers(dest="shadow_cmd")
    sh_st = sh_sub.add_parser("stats", help="Shadow agreement stats")
    sh_st.add_argument("--json", action="store_true")
    sh_st.set_defaults(func=cmd_shadow, stats=True)
    sh_ls = sh_sub.add_parser("list", help="Recent shadow rows")
    sh_ls.add_argument("--limit", type=int, default=20)
    sh_ls.add_argument("--json", action="store_true")
    sh_ls.set_defaults(func=cmd_shadow, stats=False)
    sh_cmp = sh_sub.add_parser("compare", help="Stage-1 similarity: served vs shadow")
    sh_cmp.add_argument("--limit", type=int, default=100)
    sh_cmp.set_defaults(func=cmd_shadow, shadow_cmd="compare", stats=False, compare=True)
    sh.add_argument("--stats", action="store_true")
    sh.add_argument("--limit", type=int, default=20)
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_shadow, stats=True, shadow_cmd="stats")

    a = sub.add_parser("annotate", help="Horizon annotation only")
    a.add_argument("task")
    a.add_argument("--context-chars", type=int, default=0)
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_annotate)

    c = sub.add_parser("complete", help="Close an audit with actuals")
    c.add_argument("--audit-id", required=True)
    c.add_argument("--actual-tokens", type=int, default=None)
    c.add_argument("--quality", type=float, default=None)
    c.add_argument("--success", choices=["yes", "no"], default=None)
    c.add_argument("--notes", default="")
    c.set_defaults(func=cmd_complete)

    u = sub.add_parser("audit", help="List audits or stats")
    u.add_argument("--limit", type=int, default=20)
    u.add_argument("--stats", action="store_true")
    u.add_argument("--json", action="store_true")
    u.set_defaults(func=cmd_audit)

    d = sub.add_parser(
        "distill",
        help="Distill routing rules from audits (blocked unless last lab sqc loop passed)",
    )
    d.add_argument("--min-support", type=int, default=3)
    d.add_argument(
        "--ungated",
        action="store_true",
        help="Bypass SQC Loop 3 gate (bootstrap/debug only)",
    )
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_distill)

    pol = sub.add_parser("policy", help="Print operating policy")
    pol.set_defaults(func=cmd_policy)

    ev = sub.add_parser("eval", help="Frozen golden suite and/or drift report")
    ev.add_argument("--drift", action="store_true", help="Live drift vs frozen baseline")
    ev.add_argument("--freeze-baseline", action="store_true", help="Snapshot frozen eval as drift baseline")
    ev.add_argument("--window", type=int, default=50)
    ev.add_argument("--verbose", action="store_true")
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=cmd_eval)

    g = sub.add_parser("gates", help="Graduation data bar: ready_for_canary / online")
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_gates)

    cy = sub.add_parser("canary", help="Guarded promotion registry + rollback")
    cy_sub = cy.add_subparsers(dest="canary_cmd")
    cy_st = cy_sub.add_parser("status")
    cy_st.add_argument("--json", action="store_true")
    cy_st.set_defaults(func=cmd_canary, canary_cmd="status")
    cy_pr = cy_sub.add_parser("propose")
    cy_pr.add_argument("--policy-id", required=True)
    cy_pr.add_argument("--notes", default="")
    cy_pr.set_defaults(func=cmd_canary, canary_cmd="propose")
    cy_go = cy_sub.add_parser("start")
    cy_go.add_argument("--traffic-frac", type=float, default=0.01)
    cy_go.add_argument("--force", action="store_true")
    cy_go.add_argument("--serve", action="store_true")
    cy_go.set_defaults(func=cmd_canary, canary_cmd="start")
    cy_rb = cy_sub.add_parser("rollback")
    cy_rb.add_argument("--reason", default="")
    cy_rb.set_defaults(func=cmd_canary, canary_cmd="rollback")
    cy_pm = cy_sub.add_parser("promote")
    cy_pm.add_argument("--force", action="store_true")
    cy_pm.set_defaults(func=cmd_canary, canary_cmd="promote")
    cy.set_defaults(func=cmd_canary, canary_cmd="status")

    ro = sub.add_parser("rollout", help="Four-stage: shadow→canary→ramp→full")
    ro_sub = ro.add_subparsers(dest="rollout_cmd", required=True)
    ro_st = ro_sub.add_parser("status")
    ro_st.set_defaults(func=cmd_rollout, rollout_cmd="status")
    ro_pr = ro_sub.add_parser("propose")
    ro_pr.add_argument("--policy-id", required=True)
    ro_pr.add_argument("--notes", default="")
    ro_pr.set_defaults(func=cmd_rollout, rollout_cmd="propose")
    ro_so = ro_sub.add_parser("shadow-ok")
    ro_so.add_argument("--force", action="store_true")
    ro_so.set_defaults(func=cmd_rollout, rollout_cmd="shadow-ok")
    ro_go = ro_sub.add_parser("start")
    ro_go.add_argument("--policy-id", default=None, help="optional; use propose first")
    ro_go.add_argument("--frac", type=float, default=None)
    ro_go.add_argument("--force", action="store_true")
    ro_go.add_argument("--serve", action="store_true")
    ro_go.set_defaults(func=cmd_rollout, rollout_cmd="start")
    ro_ck = ro_sub.add_parser("check")
    ro_ck.set_defaults(func=cmd_rollout, rollout_cmd="check")
    ro_ad = ro_sub.add_parser("advance")
    ro_ad.add_argument("--force", action="store_true")
    ro_ad.set_defaults(func=cmd_rollout, rollout_cmd="advance")
    ro_rb = ro_sub.add_parser("rollback")
    ro_rb.add_argument("--reason", default="")
    ro_rb.set_defaults(func=cmd_rollout, rollout_cmd="rollback")
    ro_dr = ro_sub.add_parser("drill")
    ro_dr.set_defaults(func=cmd_rollout, rollout_cmd="drill")

    se = sub.add_parser("session", help="Session lock for in-flight tool loops")
    se_sub = se.add_subparsers(dest="session_cmd", required=True)
    se_s = se_sub.add_parser("status")
    se_s.set_defaults(func=cmd_session, session_cmd="status")
    se_l = se_sub.add_parser("lock")
    se_l.add_argument("--reason", default="tool_loop")
    se_l.add_argument("--mode", choices=[MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP])
    se_l.add_argument("--notes", default="")
    se_l.set_defaults(func=cmd_session, session_cmd="lock")
    se_u = se_sub.add_parser("unlock")
    se_u.add_argument("--force", action="store_true")
    se_u.set_defaults(func=cmd_session, session_cmd="unlock")

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

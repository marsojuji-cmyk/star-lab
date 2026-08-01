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

from tokens.policy import route_task, annotate_task, MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP
from tokens.audit import AuditStore
from tokens.distill import distill_rules


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
    d = route_task(
        str(task),
        context_chars=args.context_chars,
        force_mode=args.force_mode,
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
    if args.json:
        out = d.to_dict()
        out["audit_id"] = aid
        print(json.dumps(out, indent=2))
    else:
        _print_decision(d, as_json=False)
        print(f"audit_id: {aid}")
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
    store = AuditStore()
    rules = distill_rules(store, min_support=args.min_support)
    print(json.dumps(rules, indent=2))
    print(f"# distilled {len(rules)} rule(s)", file=sys.stderr)
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    """Print the operating policy (forceful form)."""
    text = """
TOKEN AWARENESS IS THE OPERATING POLICY (Grok Star Lab / Grok Build)

1. Every task gets a predicted token horizon (LenVM-style value signal; free
   heuristic online, optional GROK_LENVM_CMD for trained probe).
2. Every call gets a budgeted mode: local | short | medium | deep.
3. Escalation must beat local-resolution EV: reward − λ·tokens.
4. Cheap / ops tasks never consume deep budget.
5. Packing, retrieval_k, subagents, continuation are governed by mode.
6. Audit actual tokens vs outcome → distill rules → redeploy continuously.

CLI:
  lab tokens route "your task"
  lab tokens complete --audit-id ID --actual-tokens N --quality 0.0-1.0
  lab tokens audit --stats
  lab tokens distill
""".strip()
    print(text)
    return 0


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(prog="lab tokens", description="Token-Aware Control Plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("route", help="Annotate + route a task")
    r.add_argument("task", nargs="?", default="", help="Task text")
    r.add_argument("--file", help="Read task from file")
    r.add_argument("--context-chars", type=int, default=0)
    r.add_argument("--force-mode", choices=[MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP])
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_route)

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

    d = sub.add_parser("distill", help="Distill routing rules from audits")
    d.add_argument("--min-support", type=int, default=3)
    d.set_defaults(func=cmd_distill)

    pol = sub.add_parser("policy", help="Print operating policy")
    pol.set_defaults(func=cmd_policy)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

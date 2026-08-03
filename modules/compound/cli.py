#!/usr/bin/env python3
"""lab compound — 10×/20×/30× rounds and evolved next-steps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "modules"))

from compound.engine import evaluate_rounds, load_state
from compound.thousandx import evaluate_1000x


def cmd_status(args: argparse.Namespace) -> int:
    r = evaluate_rounds()
    x = evaluate_1000x(compound=r)
    if args.json:
        out = dict(r)
        out["thousandx"] = x
        print(json.dumps(out, indent=2, default=str))
        return 0
    print("═══ Compounding rounds ═══")
    print("highest:   %s" % r.get("highest_round"))
    print("product:   %s× (lever product)" % r.get("product"))
    print("1000×:     %s× system  tier=%s  gap×%s  (%s)" % (
        x.get("system_product"),
        x.get("tier"),
        x.get("gap_factor"),
        x.get("doctrine"),
    ))
    print("canary:    ready=%s  online=%s" % (
        (r.get("gates") or {}).get("ready_for_canary"),
        (r.get("gates") or {}).get("ready_for_online"),
    ))
    print("\nRounds:")
    for name, info in (r.get("rounds") or {}).items():
        mark = "✓" if info.get("unlocked") else "·"
        print("  %s %s  %s" % (mark, name, info.get("label")))
        for k, v in (info.get("checks") or {}).items():
            print("      %s %s" % ("✓" if v else "✗", k))
    print("\nLevers:")
    for k, v in (r.get("levers") or {}).items():
        mark = "✓" if v.get("unlocked") else "·"
        print("  %s %-22s ×%.2f  %s" % (mark, k, float(v.get("mult") or 1), v.get("why")))
    print("\nEvolved next steps (post-%s):" % r.get("highest_round"))
    for i, s in enumerate(r.get("next_steps") or [], 1):
        print("  %d. %s" % (i, s.get("title")))
        print("     adds: %s | risks: %s" % (s.get("adds"), s.get("risks")))
        print("     why:  %s" % s.get("why"))
    return 0


def cmd_1000x(args: argparse.Namespace) -> int:
    r = evaluate_rounds()
    x = evaluate_1000x(compound=r)
    if args.json:
        print(json.dumps(x, indent=2, default=str))
        return 0
    print("═══ 1000× system scorecard ═══")
    print("doctrine:  %s" % x.get("doctrine"))
    print("formula:   %s" % x.get("formula"))
    print("system:    %s×   target=%s×   gap_factor=×%s" % (
        x.get("system_product"), x.get("target"), x.get("gap_factor"),
    ))
    print("tier:      %s" % x.get("tier"))
    print("claim:     %s" % x.get("claim_language"))
    print("\nSix levers:")
    for name, lev in (x.get("levers") or {}).items():
        print("  ×%-6s %-12s  %s" % (lev.get("mult"), name, lev.get("why")))
    sig = x.get("signals") or {}
    print("\nSignals:")
    print("  compound_product:  %s  (round %s)" % (
        sig.get("compound_lever_product"), sig.get("compound_highest_round"),
    ))
    print("  savings_suite:     %s" % sig.get("savings_suite_ratio"))
    body = sig.get("body") or {}
    print("  body outcomes avg: %s  deep_waste_ops=%s" % (
        body.get("avg_outcome_score"), body.get("deep_waste_ops"),
    ))
    rec = sig.get("recovery") or {}
    print("  recovery retry_ok: %s  (n=%s)" % (
        rec.get("retry_ok_rate"), rec.get("retry_n"),
    ))
    g = sig.get("gates") or {}
    print("  gates canary/online: %s / %s  golden=%s" % (
        g.get("ready_for_canary"), g.get("ready_for_online"), g.get("golden"),
    ))
    print("\nBlockers toward 1000×:")
    for b in x.get("blockers") or ["(none listed)"]:
        print("  · %s" % b)
    print("\nWeekly: lab body kpi --waste && lab body outcomes && lab compound 1000x")
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    r = evaluate_rounds()
    steps = r.get("next_steps") or []
    if args.json:
        print(json.dumps(steps, indent=2))
        return 0
    print("Next steps evolved for round %s (product %.2f×):\n" % (
        r.get("highest_round"), float(r.get("product") or 1)
    ))
    for i, s in enumerate(steps, 1):
        print("%d. **%s**" % (i, s.get("title")))
        print("   - Adds: %s" % s.get("adds"))
        print("   - Risks taking away: %s" % s.get("risks"))
        print("   - Why: %s" % s.get("why"))
        print()
    return 0


def cmd_round(args: argparse.Namespace) -> int:
    r = evaluate_rounds()
    name = args.name
    info = (r.get("rounds") or {}).get(name)
    if not info:
        print("error: unknown round %s (use 10x|20x|30x)" % name, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print("%s unlocked=%s" % (name, info.get("unlocked")))
        print(info.get("label"))
        for k, v in (info.get("checks") or {}).items():
            print("  %s %s" % ("✓" if v else "✗", k))
    return 0 if info.get("unlocked") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lab compound")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="Evaluate 10×/20×/30× and lever product")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)
    nx = sub.add_parser("next", help="Print evolved next-steps for current round")
    nx.add_argument("--json", action="store_true")
    nx.set_defaults(func=cmd_next)
    rd = sub.add_parser("round", help="Show one round unlock detail")
    rd.add_argument("name", choices=["10x", "20x", "30x"])
    rd.add_argument("--json", action="store_true")
    rd.set_defaults(func=cmd_round)
    tx = sub.add_parser(
        "1000x",
        help="1000× system scorecard (waste×context×recover×eval×body×reuse)",
    )
    tx.add_argument("--json", action="store_true")
    tx.set_defaults(func=cmd_1000x)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

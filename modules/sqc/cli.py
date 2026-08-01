#!/usr/bin/env python3
"""lab sqc — Statistical quality control (annotation quality skill / Loop 3)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "modules"))

from sqc.loop import QualityLoop
from sqc.risk import score_item_risk, prioritize_for_audit
from sqc.sampling import asn_curve, render_asn_ascii, single_sample, double_sample, SequentialState, sequential_sprt_step


def _load_items(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return list(data["items"])
    raise SystemExit("JSON must be a list of items or {items: [...]}")


def cmd_risk(args: argparse.Namespace) -> int:
    if args.file:
        items = _load_items(args.file)
        ranked = prioritize_for_audit(items, top_k=args.top)
        if args.json:
            print(json.dumps(ranked, indent=2))
        else:
            for r in ranked:
                risk = r["risk"]
                print(f"{risk['score']:.3f} audit={risk['recommend_audit']} id={r.get('id','?')} drivers={[d['feature'] for d in risk['drivers']]}")
        return 0
    text = args.text or sys.stdin.read()
    rs = score_item_risk(text)
    print(json.dumps(rs.to_dict(), indent=2) if args.json else rs)
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    items = _load_items(args.file)
    # outcomes from is_correct
    outcomes = []
    for it in items:
        if "is_correct" not in it:
            raise SystemExit("each item needs is_correct for sample plans")
        outcomes.append(bool(it["is_correct"]))
    if args.plan == "single":
        d = single_sample(outcomes, n=args.n, c=args.c)
    elif args.plan == "double":
        d = double_sample(outcomes, n1=args.n1, c1=args.c1, c2=args.c2, n2=args.n2)
    else:
        st = SequentialState(p0=args.p0, p1=args.p1, alpha=args.alpha, beta=args.beta)
        d = None
        for good in outcomes:
            st, d = sequential_sprt_step(st, good)
            if d.decision in ("accept", "reject"):
                break
        if d is None:
            raise SystemExit("empty outcomes")
    print(json.dumps(d.to_dict(), indent=2))
    return 0 if d.decision == "accept" else 1


def cmd_loop(args: argparse.Namespace) -> int:
    items = _load_items(args.file)
    loop = QualityLoop()
    result = loop.evaluate_batch(items, plan=args.plan, max_error_rate=args.max_error_rate)
    print(json.dumps(result.to_dict(), indent=2))
    # exit 0 only if quality sufficient (safe to distill)
    return 0 if result.quality_sufficient else 2


def cmd_asn(args: argparse.Namespace) -> int:
    asn = asn_curve(
        n=args.n,
        c=args.c,
        n1=args.n1,
        c1=args.c1,
        c2=args.c2,
        n2=args.n2,
        p0=args.p0,
        p1=args.p1,
        trials=args.trials,
    )
    if args.json:
        print(json.dumps(asn, indent=2))
    else:
        print(render_asn_ascii(asn))
        # also write plot data for portal
        out = Path(args.out) if args.out else Path.home() / ".grok/lab/sqc/asn_last.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(asn, indent=2) + "\n")
        print(f"\nwrote {out}")
    return 0


def cmd_diagram(args: argparse.Namespace) -> int:
    """Emit mermaid for Figure 1 quality loop."""
    mermaid = """flowchart TD
  Start([Start]) --> Annotate[Annotate]
  Annotate --> Evaluate[Evaluate Annotation Quality]
  Evaluate --> Q{Quality Sufficient?}
  Q -->|Yes| End((End / Distill OK))
  Q -->|No| Improve[Apply Quality Improving Methods]
  Improve --> C[Correct Annotations]
  Improve --> G[Update Guidelines]
  Improve --> T[Train Annotators]
  Improve --> O[Other interventions…]
  C --> Annotate
  G --> Annotate
  T --> Annotate
  O --> Annotate
"""
    if args.json:
        print(json.dumps({"mermaid": mermaid, "figure": 1, "name": "Iterative Annotation Quality Loop"}))
    else:
        print(mermaid)
    return 0


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(prog="lab sqc", description="SQC for annotation quality / Loop 3")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("risk", help="Score risk / prioritize audits")
    r.add_argument("--file", help="JSON list of items")
    r.add_argument("--text", help="Single text to score")
    r.add_argument("--top", type=int, default=None)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_risk)

    s = sub.add_parser("sample", help="Run acceptance sampling on labeled items")
    s.add_argument("--file", required=True)
    s.add_argument("--plan", choices=["single", "double", "sequential"], default="double")
    s.add_argument("--n", type=int, default=40)
    s.add_argument("--c", type=int, default=2)
    s.add_argument("--n1", type=int, default=25)
    s.add_argument("--c1", type=int, default=0)
    s.add_argument("--c2", type=int, default=3)
    s.add_argument("--n2", type=int, default=25)
    s.add_argument("--p0", type=float, default=0.02)
    s.add_argument("--p1", type=float, default=0.10)
    s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--beta", type=float, default=0.10)
    s.set_defaults(func=cmd_sample)

    l = sub.add_parser("loop", help="Run iterative quality loop gate (annotate→audit→distill)")
    l.add_argument("--file", required=True)
    l.add_argument("--plan", choices=["single", "double", "sequential"], default="double")
    l.add_argument("--max-error-rate", type=float, default=0.08)
    l.set_defaults(func=cmd_loop)

    a = sub.add_parser("asn", help="ASN curves (Fig 3) — efficiency of sampling plans")
    a.add_argument("--n", type=int, default=50)
    a.add_argument("--c", type=int, default=2)
    a.add_argument("--n1", type=int, default=30)
    a.add_argument("--c1", type=int, default=0)
    a.add_argument("--c2", type=int, default=3)
    a.add_argument("--n2", type=int, default=30)
    a.add_argument("--p0", type=float, default=0.02)
    a.add_argument("--p1", type=float, default=0.10)
    a.add_argument("--trials", type=int, default=150)
    a.add_argument("--json", action="store_true")
    a.add_argument("--out", default="")
    a.set_defaults(func=cmd_asn)

    d = sub.add_parser("diagram", help="Emit Figure 1 mermaid quality loop")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_diagram)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

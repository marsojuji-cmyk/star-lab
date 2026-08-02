#!/usr/bin/env python3
"""lab resilience — agentic circuit breaker surface (PR1/PR2 lean)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

_HERE = Path(__file__).resolve().parent
_MOD = str(_HERE.parent)
if _MOD not in sys.path:
    sys.path.insert(0, _MOD)

from graph import breaker as br


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_status(args: argparse.Namespace) -> int:
    data = br.status()
    if args.json:
        _print_json(data)
        return 0
    print("═══ Resilience / circuit breakers ═══")
    print("schema:  %s" % data.get("schema_version"))
    print("kill:    %s" % data.get("kill"))
    keys = data.get("keys") or {}
    if not keys:
        print("(no keys — closed default)")
    for k, e in sorted(keys.items()):
        print(
            "%s  state=%s  reason=%s"
            % (k, e.get("state"), (e.get("reason") or "")[:60])
        )
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    entry = br.record(
        args.key,
        success=args.success == "yes",
        weight=args.weight,
        class_=args.cls,
        reason=args.reason or "",
    )
    if args.json:
        _print_json(entry)
        return 0
    print("recorded %s → state=%s" % (args.key, entry.get("state")))
    return 0


def cmd_tick(args: argparse.Namespace) -> int:
    data = br.tick(args.key)
    if args.json:
        _print_json(data)
        return 0
    print("tick ok; keys=%d" % len(data.get("keys") or {}))
    return 0


def cmd_trip(args: argparse.Namespace) -> int:
    e = br.trip(args.role, reason=args.reason or "manual")
    print("tripped role:%s state=%s" % (args.role, e.get("state")))
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    br.reset(args.role)
    print("reset %s" % (args.role or "all"))
    return 0


def cmd_drill(args: argparse.Namespace) -> int:
    print("drill requires PR4 rollout bridge — stub ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lab resilience")
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    rec = sub.add_parser("record")
    rec.add_argument("key", help="scope:name e.g. role:implementer")
    rec.add_argument("--success", choices=["yes", "no"], required=True)
    rec.add_argument("--weight", type=float, default=1.0)
    rec.add_argument("--class", dest="cls", default="behavioral")
    rec.add_argument("--reason", default="")
    rec.add_argument("--json", action="store_true")
    rec.set_defaults(func=cmd_record)

    tk = sub.add_parser("tick")
    tk.add_argument("--key", default=None)
    tk.add_argument("--json", action="store_true")
    tk.set_defaults(func=cmd_tick)

    tr = sub.add_parser("trip")
    tr.add_argument("role")
    tr.add_argument("--reason", default="")
    tr.set_defaults(func=cmd_trip)

    rs = sub.add_parser("reset")
    rs.add_argument("role", nargs="?", default=None)
    rs.set_defaults(func=cmd_reset)

    dr = sub.add_parser("drill")
    dr.set_defaults(func=cmd_drill)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

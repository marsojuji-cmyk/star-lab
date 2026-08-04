#!/usr/bin/env python3
"""lab galaxy — Astro Galaxy automated key-data tracking & logging."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "modules") not in sys.path:
    sys.path.insert(0, str(_ROOT / "modules"))
if str(_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_ROOT / "lib"))

from galaxy.collector import collect_and_persist, harvest  # noqa: E402
from galaxy.render import ensure_html, write_embed  # noqa: E402
from galaxy.store import GalaxyStore  # noqa: E402


def _repo() -> Path:
    env = os.environ.get("GROK_LAB_REPO")
    if env:
        return Path(env).resolve()
    return _ROOT


def _print_status(payload: Dict[str, Any]) -> None:
    print("═══ Astro Galaxy ═══")
    print("health:    %s" % payload.get("health_score"))
    print("generated: %s" % payload.get("generated_at"))
    print("snapshot:  %s" % (payload.get("snapshot_id") or "(live harvest)"))
    summ = payload.get("summary") or {}
    print(
        "stars:     bright=%s stable=%s dim=%s dark=%s alert=%s"
        % (
            summ.get("bright"),
            summ.get("stable"),
            summ.get("dim"),
            summ.get("dark"),
            summ.get("alert"),
        )
    )
    if payload.get("alerts"):
        print("alerts:    %s" % ", ".join(payload["alerts"]))
    print("")
    stars = payload.get("stars") or {}
    for name in sorted(stars.keys()):
        s = stars[name]
        print(
            "  %-12s %-7s  mag=%.3f  %s"
            % (name, s.get("status"), float(s.get("magnitude") or 0), s.get("note") or "")
        )
    paths = payload.get("paths") or {}
    if paths:
        print("")
        for k, v in paths.items():
            print("  %s: %s" % (k, v))


def cmd_collect(args: argparse.Namespace) -> int:
    payload = collect_and_persist(source="collect" if not args.auto else "auto")
    paths = write_embed(payload, _repo())
    ensure_html(_repo())
    payload.setdefault("paths", {})
    payload["paths"]["embed"] = str(paths["embed"])
    payload["paths"]["index"] = str(paths["index"])
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_status(payload)
        print("\ncollect ok → %s" % paths["index"])
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = GalaxyStore()
    snap = store.latest_snapshot()
    if snap and not args.fresh:
        payload = snap.get("payload") or {}
        payload["snapshot_id"] = snap.get("id")
        # attach store stats
        payload["store"] = store.stats()
    else:
        payload = harvest(repo=_repo())
        payload["store"] = store.stats()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_status(payload)
        st = payload.get("store") or {}
        print(
            "\nledger: snapshots=%s events=%s db=%s"
            % (st.get("n_snapshots"), st.get("n_events"), st.get("db_path"))
        )
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    store = GalaxyStore()
    value: Any = args.value
    if value is not None:
        # try parse JSON / number
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            try:
                if "." in str(args.value):
                    value = float(args.value)
                else:
                    value = int(args.value)
            except (ValueError, TypeError):
                value = args.value
    eid = store.log_event(
        args.star,
        args.key,
        value,
        note=args.note or "",
        source="manual",
    )
    if args.json:
        print(json.dumps({"event_id": eid, "star": args.star, "key": args.key, "value": value}))
    else:
        print("logged event %s  star=%s key=%s" % (eid, args.star, args.key))
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    store = GalaxyStore()
    rows = store.recent_events(limit=args.limit, star=args.star or "")
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("no events")
        return 0
    for r in rows:
        ts = r.get("ts") or 0
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))
        print(
            "%s  %-10s %-16s %s  %s"
            % (
                when,
                r.get("star"),
                r.get("key"),
                r.get("value"),
                (r.get("note") or "")[:40],
            )
        )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = GalaxyStore()
    snap = store.latest_snapshot()
    if not snap:
        print("No snapshots yet — run: lab galaxy collect", file=sys.stderr)
        return 1
    payload = snap.get("payload") or {}
    report = {
        "snapshot_id": snap.get("id"),
        "ts": snap.get("ts"),
        "day": snap.get("day"),
        "health_score": snap.get("health_score"),
        "summary": payload.get("summary"),
        "alerts": payload.get("alerts"),
        "stars": {
            k: {
                "status": v.get("status"),
                "magnitude": v.get("magnitude"),
                "note": v.get("note"),
            }
            for k, v in (payload.get("stars") or {}).items()
        },
        "store": store.stats(),
        "recent_events": store.recent_events(limit=10),
    }
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("Astro Galaxy report")
        print("  snapshot=%s day=%s health=%s" % (
            report["snapshot_id"], report["day"], report["health_score"],
        ))
        print("  summary=%s" % report["summary"])
        print("  alerts=%s" % (report["alerts"] or []))
        for name, s in sorted((report["stars"] or {}).items()):
            print("  · %-12s %s mag=%s" % (name, s.get("status"), s.get("magnitude")))
    return 0


def _open_file(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        try:
            subprocess.run(["xdg-open", str(path)], check=False)
        except OSError:
            print("Open: %s" % path.resolve().as_uri())


def cmd_dash(args: argparse.Namespace) -> int:
    # always refresh first
    payload = collect_and_persist(source="dash")
    paths = write_embed(payload, _repo())
    ensure_html(_repo())
    index = paths["index"]
    if not args.no_open:
        _open_file(index)
    if args.json:
        print(json.dumps({"index": str(index), "health_score": payload.get("health_score")}))
    else:
        print("galaxy dash → %s  health=%s" % (index, payload.get("health_score")))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lab galaxy",
        description="Astro Galaxy — automated tracking & logging of key Grok lab data",
    )
    sub = parser.add_subparsers(dest="command")

    p_col = sub.add_parser("collect", help="Harvest all stars → snapshot + daily JSON + embed")
    p_col.add_argument("--json", action="store_true")
    p_col.add_argument(
        "--auto",
        action="store_true",
        help="Tag source as auto (for cron/hooks)",
    )
    p_col.set_defaults(func=cmd_collect)

    p_st = sub.add_parser("status", help="Show latest constellation (or --fresh harvest)")
    p_st.add_argument("--json", action="store_true")
    p_st.add_argument("--fresh", action="store_true", help="Re-harvest without persisting")
    p_st.set_defaults(func=cmd_status)

    p_log = sub.add_parser("log", help="Manually log a key data point")
    p_log.add_argument("star", help="Star name (tokens|research|core|…)")
    p_log.add_argument("key", help="Metric key")
    p_log.add_argument("value", nargs="?", default=None, help="Optional value (JSON/number/string)")
    p_log.add_argument("--note", default="")
    p_log.add_argument("--json", action="store_true")
    p_log.set_defaults(func=cmd_log)

    p_ev = sub.add_parser("events", help="List recent galaxy events")
    p_ev.add_argument("--limit", type=int, default=30)
    p_ev.add_argument("--star", default="")
    p_ev.add_argument("--json", action="store_true")
    p_ev.set_defaults(func=cmd_events)

    p_rep = sub.add_parser("report", help="Compact report from latest snapshot")
    p_rep.add_argument("--json", action="store_true")
    p_rep.set_defaults(func=cmd_report)

    p_dash = sub.add_parser("dash", help="Collect + open constellation UI (file://)")
    p_dash.add_argument("--no-open", action="store_true")
    p_dash.add_argument("--json", action="store_true")
    p_dash.set_defaults(func=cmd_dash)

    p_auto = sub.add_parser("auto", help="Alias for collect --auto (cron/hooks)")
    p_auto.add_argument("--json", action="store_true")
    p_auto.set_defaults(func=lambda a: cmd_collect(argparse.Namespace(json=a.json, auto=True)))

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

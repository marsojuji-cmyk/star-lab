#!/usr/bin/env python3
"""lab handoff — assemble repos + key data for new-chat warm start.

  lab handoff close [--next …] [--open …] [--note …]
  lab handoff brief
  lab handoff status
  lab handoff open
  lab handoff write   # alias of close without requiring next
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_MOD = str(_HERE.parent)
if _MOD not in sys.path:
    sys.path.insert(0, _MOD)

STALE_DAYS = 7
MAX_REPOS = 12
MAX_NEXT = 5
MAX_OPEN = 5


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def _handoff_dir() -> Path:
    d = _lab_data() / "handoff"
    d.mkdir(parents=True, mode=0o700, exist_ok=True)
    (d / "history").mkdir(parents=True, mode=0o700, exist_ok=True)
    return d


def _lab_bin() -> str:
    env = os.environ.get("LAB_BIN")
    if env and Path(env).is_file():
        return env
    p = Path.home() / ".local" / "bin" / "lab"
    if p.is_file():
        return str(p)
    alt = Path.home() / "Projects" / "grok-home" / "bin" / "lab"
    if alt.is_file():
        return str(alt)
    return "lab"


def _run(argv: List[str], timeout: int = 45) -> Tuple[int, str]:
    try:
        r = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={
                **os.environ,
                "PATH": f"{Path.home()}/.local/bin:{Path.home()}/homebrew/bin:"
                + os.environ.get("PATH", ""),
            },
        )
        return int(r.returncode), (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _scan_projects() -> List[Dict[str, Any]]:
    root = Path.home() / "Projects"
    rows: List[Dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith(".") or p.name.endswith(".git"):
            continue
        if p.name in ("AGENTS.md", "README.md"):
            continue
        git = p / ".git"
        if not git.exists():
            continue
        branch = ""
        dirty = False
        remote = ""
        code, out = _run(["git", "-C", str(p), "status", "-sb"], timeout=10)
        if code == 0 and out.strip():
            first = out.splitlines()[0]
            # ## main...github/main [ahead 1]
            m = re.match(r"##\s+(\S+)", first)
            if m:
                branch = m.group(1).split("...")[0]
            dirty = len(out.splitlines()) > 1 or " [" in first
        code, out = _run(["git", "-C", str(p), "remote", "-v"], timeout=10)
        if code == 0:
            for line in out.splitlines():
                if "\t" in line and "(fetch)" in line:
                    remote = line.split("\t", 1)[1].replace(" (fetch)", "").strip()
                    if "github.com" in remote:
                        break
        agents = ""
        ap = p / "AGENTS.md"
        if ap.is_file():
            try:
                agents = ap.read_text(encoding="utf-8").strip().splitlines()[0][:80]
            except OSError:
                pass
        rows.append(
            {
                "name": p.name,
                "path": str(p),
                "branch": branch,
                "dirty": dirty,
                "remote": remote,
                "agents_head": agents,
            }
        )
    return rows


def _body_index() -> Dict[str, Dict[str, Any]]:
    code, out = _run([_lab_bin(), "body", "list"], timeout=15)
    bodies: Dict[str, Dict[str, Any]] = {}
    if code != 0:
        return bodies
    for line in out.splitlines():
        # project:pulse-board  kind=project  project=pulse-board
        m = re.match(r"(\S+)\s+kind=(\S+)\s+project=(\S+)", line.strip())
        if not m:
            continue
        bid, kind, proj = m.group(1), m.group(2), m.group(3)
        repo = ""
        c2, o2 = _run([_lab_bin(), "body", "show", bid], timeout=10)
        if c2 == 0:
            for ln in o2.splitlines():
                if ln.startswith("repo:"):
                    repo = ln.split(":", 1)[1].strip()
        bodies[bid] = {"body_id": bid, "kind": kind, "project": proj, "repo": repo}
    return bodies


def _plane_snapshot() -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    code, out = _run([_lab_bin(), "doctor"], timeout=60)
    snap["doctor_exit"] = code
    m = re.search(r"pass=(\d+)\s+warn=(\d+)\s+fail=(\d+)", out)
    if m:
        snap["doctor"] = m.group(0)
    snap["doctor_operational"] = code == 0 and "OPERATIONAL" in out

    code, out = _run([_lab_bin(), "galaxy", "status"], timeout=30)
    hm = re.search(r"health:\s+([0-9.]+)", out)
    dim = re.search(r"dim=(\d+)", out)
    snap["galaxy_health"] = float(hm.group(1)) if hm else None
    snap["galaxy_dim"] = int(dim.group(1)) if dim else None

    code, out = _run([_lab_bin(), "compound", "status"], timeout=20)
    hm = re.search(r"highest:\s+(\S+)", out)
    snap["compound_highest"] = hm.group(1) if hm else None

    # prove-me latest if present
    prove = Path.home() / "Projects" / "prove-me" / "proof" / "latest.json"
    if prove.is_file():
        try:
            data = json.loads(prove.read_text(encoding="utf-8"))
            snap["prove_me"] = {
                "overall_ok": data.get("overall_ok"),
                "pass_count": data.get("pass_count"),
                "fail_count": data.get("fail_count"),
                "generated_at": data.get("generated_at"),
            }
        except (OSError, json.JSONDecodeError):
            snap["prove_me"] = {"error": "unreadable"}
    else:
        snap["prove_me"] = None

    # canary serve
    code, out = _run([_lab_bin(), "tokens", "canary", "status"], timeout=15)
    serve = None
    if code == 0:
        try:
            d = json.loads(out)
            st = d.get("state") or d
            serve = st.get("serve_enabled")
        except json.JSONDecodeError:
            if "serve_enabled" in out:
                serve = "false" in out.lower() and False or None
    snap["canary_serve_enabled"] = serve

    auto = _lab_data() / "session_auto.json"
    if auto.is_file():
        try:
            snap["auto_session"] = json.loads(auto.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            snap["auto_session"] = {"error": "unreadable"}
    else:
        snap["auto_session"] = None

    return snap


def _focus_repos(
    projects: List[Dict[str, Any]], bodies: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    body_by_name = {}
    for b in bodies.values():
        body_by_name[b.get("project") or ""] = b
        # also map repo basename
        rp = b.get("repo") or ""
        if rp:
            body_by_name[Path(rp).name] = b

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for p in projects:
        score = 0
        name = p["name"]
        b = body_by_name.get(name)
        if b:
            score += 10
            p = dict(p)
            p["body_id"] = b.get("body_id")
        if p.get("dirty"):
            score += 5
        if p.get("remote") and "github.com" in (p.get("remote") or ""):
            score += 3
        # prefer known lab demos
        if name in (
            "grok-home",
            "prove-me",
            "pulse-board",
            "starlab-demo",
            "claude-home",
            "claude-compare-demo",
        ):
            score += 4
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return [p for _, p in scored[:MAX_REPOS]]


def assemble(
    *,
    next_intents: Optional[List[str]] = None,
    open_work: Optional[List[str]] = None,
    note: str = "",
) -> Dict[str, Any]:
    projects = _scan_projects()
    bodies = _body_index()
    focus = _focus_repos(projects, bodies)
    plane = _plane_snapshot()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pkg = {
        "schema_version": 1,
        "generated_at": now,
        "generated_ts": time.time(),
        "standing_contract": [
            "Human: chat-only intents — no lab ceremony",
            "Grok: route → work → auto finish / galaxy (absorb ids)",
            "Hold: canary serve off; no Galaxy collectors unless dim/alert",
        ],
        "do_not": [
            "Do not ask human for audit_id / research_id",
            "Do not enable canary serve without explicit ask",
            "Do not expand Galaxy collectors while dim=0",
            "Do not deep-budget ops (doctor/status/typos)",
            "Do not invent product goals the user never stated",
        ],
        "note": (note or "").strip(),
        "next_intents": [x.strip() for x in (next_intents or []) if x.strip()][:MAX_NEXT],
        "open_work": [x.strip() for x in (open_work or []) if x.strip()][:MAX_OPEN],
        "active_repos": focus,
        "bodies": list(bodies.values()),
        "plane": plane,
        "paths": {
            "memory": str(Path.home() / ".grok" / "memory" / "MEMORY.md"),
            "home_rules": str(Path.home() / ".grok" / "rules" / "home.md"),
            "human_minimal": str(
                Path.home() / "Projects" / "grok-home" / "docs" / "HUMAN-MINIMAL-1000X.md"
            ),
            "daily_operating": str(
                Path.home() / "Projects" / "grok-home" / "docs" / "DAILY-OPERATING.md"
            ),
            "handoff_doc": str(
                Path.home() / "Projects" / "grok-home" / "docs" / "NEW-CHAT-HANDOFF.md"
            ),
            "prove_html": str(
                Path.home() / "Projects" / "prove-me" / "proof" / "latest.html"
            ),
        },
        "agent_first_tools": [
            "lab handoff brief",
            'lab tokens route "<first task>" --project <focus>',
            "lab auto begin|finish or lab body loop when multi-file",
        ],
    }
    return pkg


def render_md(pkg: Dict[str, Any], *, stale: bool = False) -> str:
    lines: List[str] = []
    lines.append("# New-chat handoff brief")
    lines.append("")
    lines.append(f"Generated: **{pkg.get('generated_at')}**" + (" · **STALE**" if stale else ""))
    lines.append("")
    lines.append("## Standing contract")
    for b in pkg.get("standing_contract") or []:
        lines.append(f"- {b}")
    lines.append("")
    lines.append("## Do not")
    for b in pkg.get("do_not") or []:
        lines.append(f"- {b}")
    lines.append("")
    if pkg.get("note"):
        lines.append("## Last session note")
        lines.append(pkg["note"])
        lines.append("")
    ow = pkg.get("open_work") or []
    if ow:
        lines.append("## Open work")
        for x in ow:
            lines.append(f"- {x}")
        lines.append("")
    ni = pkg.get("next_intents") or []
    if ni:
        lines.append("## Next intents (priority)")
        for i, x in enumerate(ni, 1):
            lines.append(f"{i}. {x}")
        lines.append("")
    else:
        lines.append("## Next intents")
        lines.append("- (none recorded — wait for user chat intent)")
        lines.append("")

    plane = pkg.get("plane") or {}
    lines.append("## Plane snapshot")
    lines.append(f"- doctor: `{plane.get('doctor')}` operational={plane.get('doctor_operational')}")
    lines.append(
        f"- galaxy: health={plane.get('galaxy_health')} dim={plane.get('galaxy_dim')}"
    )
    lines.append(f"- compound: highest={plane.get('compound_highest')}")
    pm = plane.get("prove_me")
    if pm:
        lines.append(
            f"- prove-me: ok={pm.get('overall_ok')} {pm.get('pass_count')}/{int(pm.get('pass_count') or 0)+int(pm.get('fail_count') or 0)} @ {pm.get('generated_at')}"
        )
    lines.append(f"- canary serve_enabled: {plane.get('canary_serve_enabled')}")
    auto = plane.get("auto_session")
    if auto and auto.get("phase") == "open":
        lines.append(
            f"- **lab auto OPEN** goal={auto.get('goal')!r} audit={auto.get('audit_id')} research={auto.get('research_id')}"
        )
    else:
        lines.append("- lab auto: none open")
    lines.append("")

    lines.append("## Active repos (attention set)")
    for r in pkg.get("active_repos") or []:
        flags = []
        if r.get("body_id"):
            flags.append(r["body_id"])
        if r.get("dirty"):
            flags.append("dirty")
        if r.get("remote"):
            flags.append("remote")
        flag_s = ", ".join(flags) if flags else "-"
        lines.append(
            f"- **{r.get('name')}** `{r.get('path')}` branch={r.get('branch') or '?'} [{flag_s}]"
        )
    lines.append("")

    lines.append("## Agent first moves")
    for x in pkg.get("agent_first_tools") or []:
        lines.append(f"- `{x}`")
    lines.append("")

    lines.append("## Paths")
    for k, v in (pkg.get("paths") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Paste into new chat")
    lines.append("")
    lines.append("```")
    lines.append("NEW CHAT HANDOFF — read this first, then wait for my intent.")
    lines.append(f"ts: {pkg.get('generated_at')}" + (" STALE" if stale else ""))
    lines.append("Contract: human chat-only; Grok absorbs lab ceremony; canary serve OFF.")
    if ni:
        lines.append("Next: " + " | ".join(ni[:3]))
    if ow:
        lines.append("Open: " + " | ".join(ow[:3]))
    names = [r.get("name") for r in (pkg.get("active_repos") or [])[:8]]
    lines.append("Repos: " + ", ".join(names))
    lines.append(
        f"Plane: {plane.get('doctor')} · galaxy={plane.get('galaxy_health')} dim={plane.get('galaxy_dim')} · compound={plane.get('compound_highest')}"
    )
    if pm:
        lines.append(f"prove-me: ok={pm.get('overall_ok')} {pm.get('pass_count')}pass")
    lines.append("Commands: lab handoff brief · lab auto · lab body loop · prove-me HTML")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _is_stale(pkg: Dict[str, Any]) -> bool:
    ts = pkg.get("generated_ts")
    if not ts:
        return True
    return (time.time() - float(ts)) > STALE_DAYS * 86400


def _write_pkg(pkg: Dict[str, Any]) -> Dict[str, Path]:
    hd = _handoff_dir()
    latest_json = hd / "latest.json"
    latest_md = hd / "latest.md"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hist_json = hd / "history" / f"{stamp}.json"
    hist_md = hd / "history" / f"{stamp}.md"
    md = render_md(pkg, stale=False)
    blob = json.dumps(pkg, indent=2) + "\n"
    latest_json.write_text(blob, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    hist_json.write_text(blob, encoding="utf-8")
    hist_md.write_text(md, encoding="utf-8")
    return {"json": latest_json, "md": latest_md, "hist_json": hist_json, "hist_md": hist_md}


def _load_latest() -> Optional[Dict[str, Any]]:
    p = _handoff_dir() / "latest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cmd_close(args: argparse.Namespace) -> int:
    nexts = list(args.next or [])
    opens = list(args.open_work or [])
    pkg = assemble(next_intents=nexts, open_work=opens, note=args.note or "")
    paths = _write_pkg(pkg)
    print("═══ lab handoff close ═══")
    print(f"json: {paths['json']}")
    print(f"md:   {paths['md']}")
    print(f"repos: {len(pkg.get('active_repos') or [])} focused")
    print(f"next:  {len(pkg.get('next_intents') or [])}")
    if args.print_brief:
        print()
        print(render_md(pkg, stale=False))
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    pkg = _load_latest()
    if not pkg or args.refresh:
        pkg = assemble(
            next_intents=(pkg or {}).get("next_intents") if pkg else [],
            open_work=(pkg or {}).get("open_work") if pkg else [],
            note=(pkg or {}).get("note") or "",
        )
        if args.refresh:
            _write_pkg(pkg)
    stale = _is_stale(pkg)
    md = render_md(pkg, stale=stale)
    print(md)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    pkg = _load_latest()
    if not pkg:
        print("handoff: no latest — run lab handoff close")
        return 1
    stale = _is_stale(pkg)
    print("═══ lab handoff status ═══")
    print(f"generated: {pkg.get('generated_at')}" + (" STALE" if stale else ""))
    print(f"repos:     {len(pkg.get('active_repos') or [])}")
    print(f"next:      {pkg.get('next_intents') or []}")
    print(f"open:      {pkg.get('open_work') or []}")
    plane = pkg.get("plane") or {}
    print(f"doctor:    {plane.get('doctor')}")
    print(f"galaxy:    health={plane.get('galaxy_health')} dim={plane.get('galaxy_dim')}")
    print(f"path:      {_handoff_dir() / 'latest.md'}")
    return 0


def cmd_open(_args: argparse.Namespace) -> int:
    md = _handoff_dir() / "latest.md"
    if not md.is_file():
        print("error: no latest.md — lab handoff close first", file=sys.stderr)
        return 1
    print(md)
    if sys.platform == "darwin":
        subprocess.run(["open", str(md)], check=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab handoff",
        description="Cross-chat handoff: assemble repos + key plane data",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("close", help="Write handoff package (end of chat)")
    c.add_argument("--next", action="append", default=[], dest="next", help="Next intent (repeatable)")
    c.add_argument(
        "--open",
        action="append",
        default=[],
        dest="open_work",
        help="Open work / WIP note (repeatable)",
    )
    c.add_argument("--note", default="", help="One-line session summary")
    c.add_argument("--print-brief", action="store_true", help="Also print markdown brief")
    c.set_defaults(func=cmd_close)

    w = sub.add_parser("write", help="Alias for close")
    w.add_argument("--next", action="append", default=[], dest="next")
    w.add_argument("--open", action="append", default=[], dest="open_work")
    w.add_argument("--note", default="")
    w.add_argument("--print-brief", action="store_true")
    w.set_defaults(func=cmd_close)

    b = sub.add_parser("brief", help="Print markdown brief for new chat")
    b.add_argument(
        "--refresh",
        action="store_true",
        help="Re-assemble plane/repos; keep prior next/open/note",
    )
    b.set_defaults(func=cmd_brief)

    s = sub.add_parser("status", help="One-screen handoff status")
    s.set_defaults(func=cmd_status)

    o = sub.add_parser("open", help="Open latest.md")
    o.set_defaults(func=cmd_open)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

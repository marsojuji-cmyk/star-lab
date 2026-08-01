#!/usr/bin/env python3
# Grok Star Lab — Integration Dock CLI (PR12)
# lab dock status|probe
"""
Optional MCP presence with offline fallbacks.

Design (K10): MCP Dock is optional; never doctor-fail.
Offline fallback matrix: gh / docs / skip calendar.
Probes are light (config parse + optional `grok mcp list`); no network required
for status. Missing MCP is off/warn, never fail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# lib/ on sys.path when run as modules/dock/cli.py
_REPO = Path(__file__).resolve().parent.parent.parent
_LIB = _REPO / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lab_paths import grok_home, repo_root  # noqa: E402

# Python 3.9+ — avoid 3.10+ syntax (match/, X | Y).

# ---------------------------------------------------------------------------
# Catalog — offline fallback matrix (gh / docs / skip calendar)
# ---------------------------------------------------------------------------

# mcp_aliases: names that may appear in config.toml, grok mcp list, or
# session-managed gateway ids (e.g. grok_com_github).
INTEGRATIONS: List[Dict[str, Any]] = [
    {
        "id": "github",
        "label": "GitHub",
        "mcp_aliases": ("github", "grok_com_github"),
        "fallback": {
            "kind": "cli",
            "command": "gh",
            "description": "GitHub CLI (gh) — issues/PRs/API offline of MCP",
        },
    },
    {
        "id": "docs",
        "label": "Docs / wiki",
        "mcp_aliases": (
            "notion",
            "grok_com_notion",
            "google_drive",
            "docs",
        ),
        "fallback": {
            "kind": "local_docs",
            "description": "Local docs (MEMORY, design docs, AGENTS)",
        },
    },
    {
        "id": "calendar",
        "label": "Calendar",
        "mcp_aliases": ("google_calendar", "calendar", "gcal"),
        "fallback": {
            "kind": "skip",
            "description": "Skip offline — calendar is optional; no required fallback",
        },
    },
]


@dataclass
class FallbackResult:
    kind: str
    ok: bool
    detail: str
    path: Optional[str] = None


@dataclass
class IntegrationStatus:
    id: str
    label: str
    mcp_present: bool
    mcp_names: List[str] = field(default_factory=list)
    mcp_source: str = ""  # config | grok-list | none
    fallback: FallbackResult = field(
        default_factory=lambda: FallbackResult(kind="none", ok=False, detail="")
    )
    # ok | warn | off  — never "fail" for MCP absence (K10)
    status: str = "off"
    note: str = ""


@dataclass
class DockReport:
    schema_version: int
    command: str
    module_status: str  # ok | warn | off  (never fail solely for MCP)
    integrations: List[IntegrationStatus]
    mcp_servers_seen: List[str]
    probe_method: str
    offline_ok: bool
    notes: List[str] = field(default_factory=list)


def _root() -> Path:
    env = os.environ.get("GROK_LAB_REPO")
    if env:
        return Path(env).resolve()
    return repo_root()


def _usage() -> str:
    return """lab dock — optional MCP Integration Dock (offline fallbacks)

Usage:
  lab dock status [--json]     show integrations + offline fallback readiness
  lab dock probe  [--json]     light MCP presence probe + fallbacks
  lab dock help

Integrations (offline fallback matrix):
  github     MCP github*        → fallback: gh CLI
  docs       MCP notion/drive*  → fallback: local MEMORY / design docs / AGENTS
  calendar   MCP google_calendar → fallback: skip (optional; always ok offline)

Policy (K10):
  MCP absence is ok|warn|off — never fail core doctor.
  Offline fallbacks are always acceptable for success criteria.

Probes are light: parse ~/.grok/config.toml [mcp_servers.*], optional
`grok mcp list --json` (short timeout). No network calls required for status.
"""


# ---------------------------------------------------------------------------
# Light MCP detection
# ---------------------------------------------------------------------------

_MCP_SECTION_RE = re.compile(
    r"^\s*\[mcp_servers\.([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$"
)


def parse_mcp_server_names_from_toml(text: str) -> List[str]:
    """Extract [mcp_servers.<name>] section headers. Python 3.9-safe, no tomllib."""
    names: List[str] = []
    seen = set()
    for line in text.splitlines():
        m = _MCP_SECTION_RE.match(line)
        if not m:
            continue
        name = m.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def collect_configured_mcp_names(home: Path, repo: Path) -> Tuple[List[str], str]:
    """
    Collect MCP server names from user + project config and common compat files.
    Returns (names, source_summary). No process spawn.
    """
    found: List[str] = []
    sources: List[str] = []
    seen = set()

    def _add(names: Sequence[str], src: str) -> None:
        added = False
        for n in names:
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(n)
            added = True
        if added:
            sources.append(src)

    user_cfg = home / "config.toml"
    if user_cfg.is_file():
        text = _read_text(user_cfg)
        _add(parse_mcp_server_names_from_toml(text), "user-config")

    # Project-scoped .grok/config.toml (repo)
    proj_cfg = repo / ".grok" / "config.toml"
    if proj_cfg.is_file():
        text = _read_text(proj_cfg)
        _add(parse_mcp_server_names_from_toml(text), "project-config")

    # Compat: project .mcp.json (names only; light JSON parse)
    proj_mcp_json = repo / ".mcp.json"
    if proj_mcp_json.is_file():
        _add(_names_from_mcp_json(proj_mcp_json), "mcp-json")

    cursor_user = Path.home() / ".cursor" / "mcp.json"
    if cursor_user.is_file():
        _add(_names_from_mcp_json(cursor_user), "cursor-mcp")

    proj_cursor = repo / ".cursor" / "mcp.json"
    if proj_cursor.is_file():
        _add(_names_from_mcp_json(proj_cursor), "project-cursor-mcp")

    src = "+".join(sources) if sources else "none"
    return found, src


def _names_from_mcp_json(path: Path) -> List[str]:
    try:
        data = json.loads(_read_text(path) or "{}")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    # Common shapes: {"mcpServers": {...}} or {"servers": {...}}
    for key in ("mcpServers", "servers", "mcp_servers"):
        block = data.get(key)
        if isinstance(block, dict):
            return [str(k) for k in block.keys()]
    return []


def grok_mcp_list(timeout_sec: float = 8.0) -> Tuple[List[str], str]:
    """
    Light probe: `grok mcp list --json` if grok is on PATH.
    Returns (names, note). Never raises; empty on any failure.
    """
    grok = shutil.which("grok")
    if not grok:
        return [], "grok not on PATH"

    try:
        proc = subprocess.run(
            [grok, "mcp", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], "grok mcp list failed: %s" % exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:200]
        return [], "grok mcp list exit %s%s" % (
            proc.returncode,
            (": " + err) if err else "",
        )

    raw = (proc.stdout or "").strip()
    if not raw:
        return [], "grok mcp list empty"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Human fallback: parse simple name lines if --json unsupported
        names = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("no mcp"):
                continue
            # e.g. "github  (enabled)" or bare name
            token = line.split()[0].strip("()")
            if re.match(r"^[A-Za-z0-9_.-]+$", token):
                names.append(token)
        return names, "grok-list-text"

    names = _normalize_mcp_list_json(data)
    return names, "grok-list"


def _normalize_mcp_list_json(data: Any) -> List[str]:
    """Accept list of strings, list of objects, or {servers: [...]}."""
    names: List[str] = []

    def from_item(item: Any) -> Optional[str]:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for k in ("name", "id", "server", "server_name"):
                if k in item and item[k]:
                    return str(item[k])
        return None

    if isinstance(data, list):
        for item in data:
            n = from_item(item)
            if n:
                names.append(n)
        return names

    if isinstance(data, dict):
        for key in ("servers", "mcp_servers", "mcpServers", "items"):
            block = data.get(key)
            if isinstance(block, list):
                for item in block:
                    n = from_item(item)
                    if n:
                        names.append(n)
                if names:
                    return names
            if isinstance(block, dict):
                return [str(k) for k in block.keys()]
        # map of name -> config
        if all(isinstance(v, (dict, str, bool, type(None))) for v in data.values()):
            return [str(k) for k in data.keys()]

    return names


def match_mcp(
    aliases: Sequence[str], seen: Sequence[str]
) -> Tuple[bool, List[str]]:
    """Case-insensitive alias match against seen MCP names."""
    alias_set = {a.lower() for a in aliases}
    hits = []
    for name in seen:
        low = name.lower()
        # exact or suffix after grok_com_
        if low in alias_set:
            hits.append(name)
            continue
        # managed gateway style: managed_gateway:github etc.
        bare = low.split(":")[-1]
        if bare in alias_set:
            hits.append(name)
            continue
        # prefix match for namespaced variants
        for a in alias_set:
            if low == a or low.endswith("_" + a) or low.startswith(a + "_"):
                hits.append(name)
                break
    # dedupe preserve order
    out: List[str] = []
    seen_h = set()
    for h in hits:
        if h not in seen_h:
            seen_h.add(h)
            out.append(h)
    return (len(out) > 0, out)


# ---------------------------------------------------------------------------
# Offline fallbacks
# ---------------------------------------------------------------------------


def check_fallback_cli(command: str) -> FallbackResult:
    path = shutil.which(command)
    if path:
        return FallbackResult(
            kind="cli",
            ok=True,
            detail="%s available" % command,
            path=path,
        )
    return FallbackResult(
        kind="cli",
        ok=False,
        detail="%s not on PATH" % command,
        path=None,
    )


def check_fallback_local_docs(repo: Path, home: Path) -> FallbackResult:
    """Local docs stand in for Notion/Drive MCP."""
    candidates = [
        home / "memory" / "MEMORY.md",
        home / "docs",
        repo / "docs" / "GROK-STAR-LAB-DESIGN.md",
        repo / "docs",
        repo / "AGENTS.md",
        repo / "Agents.md",
        Path.home() / "Projects" / "AGENTS.md",
    ]
    present = [str(p) for p in candidates if p.exists()]
    if present:
        return FallbackResult(
            kind="local_docs",
            ok=True,
            detail="%d local doc path(s)" % len(present),
            path=present[0],
        )
    return FallbackResult(
        kind="local_docs",
        ok=False,
        detail="no local MEMORY/design/AGENTS docs found",
        path=None,
    )


def check_fallback_skip(description: str) -> FallbackResult:
    return FallbackResult(kind="skip", ok=True, detail=description, path=None)


def check_fallback(
    spec: Dict[str, Any], repo: Path, home: Path
) -> FallbackResult:
    kind = spec.get("kind") or "none"
    if kind == "cli":
        return check_fallback_cli(str(spec.get("command") or ""))
    if kind == "local_docs":
        return check_fallback_local_docs(repo, home)
    if kind == "skip":
        return check_fallback_skip(
            str(spec.get("description") or "skip offline (optional)")
        )
    return FallbackResult(kind=str(kind), ok=False, detail="unknown fallback kind")


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report(
    command: str,
    *,
    do_probe: bool,
    home: Optional[Path] = None,
    repo: Optional[Path] = None,
) -> DockReport:
    home = home or grok_home()
    repo = repo or _root()

    configured, cfg_src = collect_configured_mcp_names(home, repo)
    seen: List[str] = list(configured)
    notes: List[str] = []
    probe_method = "config-only"
    list_note = ""

    if do_probe:
        probe_method = "config+grok-list"
        listed, list_note = grok_mcp_list()
        if list_note and list_note not in ("grok-list", "grok-list-text"):
            notes.append(list_note)
        # merge listed names
        have = {s.lower() for s in seen}
        for n in listed:
            if n.lower() not in have:
                seen.append(n)
                have.add(n.lower())
        if listed:
            notes.append("grok mcp list: %d server(s)" % len(listed))
        elif list_note in ("grok-list", "grok-list-text"):
            notes.append("grok mcp list: none configured (local)")
    else:
        if cfg_src == "none":
            notes.append("no [mcp_servers.*] in config (optional)")

    integrations: List[IntegrationStatus] = []
    for entry in INTEGRATIONS:
        aliases = entry["mcp_aliases"]
        present, hits = match_mcp(aliases, seen)
        fb = check_fallback(entry["fallback"], repo, home)

        # Status policy: never fail for MCP absence
        if present and fb.ok:
            st = "ok"
            note = "MCP + offline fallback ready"
        elif present and not fb.ok:
            st = "ok"  # MCP alone is fine
            note = "MCP present; fallback weak: %s" % fb.detail
        elif not present and fb.ok:
            # Offline path healthy — preferred offline tier outcome
            if fb.kind == "skip":
                st = "off"
                note = "MCP absent; offline skip (ok)"
            else:
                st = "ok"
                note = "MCP absent; offline fallback ok"
        else:
            st = "warn"
            note = "MCP absent and fallback missing: %s" % fb.detail

        integrations.append(
            IntegrationStatus(
                id=entry["id"],
                label=entry["label"],
                mcp_present=present,
                mcp_names=hits,
                mcp_source=cfg_src if present else "none",
                fallback=fb,
                status=st,
                note=note,
            )
        )

    # Module rollup: never "fail"
    statuses = [i.status for i in integrations]
    if all(s == "ok" for s in statuses):
        module_status = "ok"
    elif any(s == "warn" for s in statuses):
        module_status = "warn"
    elif any(s == "ok" for s in statuses):
        # mix of ok + off → ok (offline core healthy)
        module_status = "ok"
    else:
        module_status = "off"

    # Offline success: every non-skip fallback ok OR skip; MCP optional
    offline_ok = all(
        i.fallback.ok for i in integrations
    )

    if offline_ok:
        notes.append("offline fallbacks: ok (MCP optional)")
    else:
        notes.append("offline fallbacks: incomplete (still never doctor-fail)")

    notes.append("mcp config source: %s" % cfg_src)
    if not do_probe:
        notes.append("tip: lab dock probe for live grok mcp list")

    return DockReport(
        schema_version=1,
        command=command,
        module_status=module_status,
        integrations=integrations,
        mcp_servers_seen=seen,
        probe_method=probe_method,
        offline_ok=offline_ok,
        notes=notes,
    )


def report_to_dict(report: DockReport) -> Dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "command": report.command,
        "module_status": report.module_status,
        "offline_ok": report.offline_ok,
        "probe_method": report.probe_method,
        "mcp_servers_seen": report.mcp_servers_seen,
        "integrations": [
            {
                "id": i.id,
                "label": i.label,
                "status": i.status,
                "mcp_present": i.mcp_present,
                "mcp_names": i.mcp_names,
                "mcp_source": i.mcp_source,
                "fallback": asdict(i.fallback),
                "note": i.note,
            }
            for i in report.integrations
        ],
        "notes": report.notes,
    }


def print_human(report: DockReport) -> None:
    print("Integration Dock  (MCP optional · offline fallbacks always)")
    print(
        "module_status=%s  offline_ok=%s  probe=%s"
        % (report.module_status, str(report.offline_ok).lower(), report.probe_method)
    )
    print("")
    hdr = "%-10s  %-6s  %-12s  %-28s  %s" % (
        "id",
        "status",
        "mcp",
        "fallback",
        "note",
    )
    print(hdr)
    print("-" * len(hdr))
    for i in report.integrations:
        mcp = "present" if i.mcp_present else "absent"
        if i.mcp_names:
            mcp = "present(%s)" % ",".join(i.mcp_names[:3])
        fb = "%s:%s" % (
            i.fallback.kind,
            "ok" if i.fallback.ok else "missing",
        )
        print(
            "%-10s  %-6s  %-12s  %-28s  %s"
            % (i.id, i.status, mcp[:12], fb[:28], i.note)
        )
    print("")
    if report.mcp_servers_seen:
        print("mcp seen: %s" % ", ".join(report.mcp_servers_seen))
    else:
        print("mcp seen: (none in local config/list)")
    for n in report.notes:
        print("note: %s" % n)
    print("")
    print("policy: MCP absence never fails core doctor (K10)")


def cmd_status(args: argparse.Namespace) -> int:
    report = build_report("status", do_probe=False)
    if args.json:
        print(json.dumps(report_to_dict(report), indent=2, sort_keys=False))
    else:
        print_human(report)
    # Exit 0 when offline ok; still 0 on warn (optional MCP) — never doctor-fail.
    # Exit 1 only if offline fallbacks broken AND we want a soft signal — design
    # says offline fallbacks always ok for success; warn paths still exit 0.
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    report = build_report("probe", do_probe=True)
    if args.json:
        print(json.dumps(report_to_dict(report), indent=2, sort_keys=False))
    else:
        print_human(report)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_usage())
        return 0

    parser = argparse.ArgumentParser(
        prog="lab dock",
        description="Integration Dock — optional MCP + offline fallbacks",
        add_help=False,
    )
    parser.add_argument(
        "command",
        choices=["status", "probe", "help"],
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="machine-readable JSON on stdout",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return code

    if args.command == "help":
        sys.stdout.write(_usage())
        return 0
    if args.command == "status":
        return cmd_status(args)
    if args.command == "probe":
        return cmd_probe(args)
    print("error: unknown command: %s" % args.command, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# Observatory — snapshot status for Mission Control (offline core).
# Python 3.9+.
"""lab observatory snapshot|dash|report — writes data/status.json + data-embed.js."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow `python3 modules/observatory/cli.py` without install.
_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO / "lib"))

from lab_paths import lab_data_root, repo_root  # noqa: E402

MODULE_NAMES = [
    "forge",
    "gym",
    "arena",
    "design",
    "ship",
    "imagine",
    "knowledge",
    "observatory",
    "sandbox",
    "dock",
    "showroom",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_doctor_json(root: Path) -> Dict[str, Any]:
    doctor = root / "bin" / "doctor"
    env = os.environ.copy()
    # Match doctor PATH contract.
    path_prefix = "%s/.grok/bin:%s/.local/bin:%s/homebrew/bin:/usr/local/bin" % (
        Path.home(),
        Path.home(),
        Path.home(),
    )
    env["PATH"] = path_prefix + ":" + env.get("PATH", "")
    proc = subprocess.run(
        [str(doctor), "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    text = (proc.stdout or "").strip()
    if not text:
        raise RuntimeError(
            "doctor --json produced no stdout (exit %s): %s"
            % (proc.returncode, (proc.stderr or "")[:400])
        )
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("doctor --json not valid JSON: %s" % exc) from exc
    return doc


def _ollama_models() -> List[str]:
    try:
        proc = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    models: List[str] = []
    for i, line in enumerate((proc.stdout or "").splitlines()):
        if i == 0:
            continue  # header
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def _disk_free_home() -> str:
    try:
        proc = subprocess.run(
            ["df", "-h", str(Path.home())],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = (proc.stdout or "").splitlines()
        if len(lines) >= 2:
            cols = lines[1].split()
            # df -h: Filesystem Size Used Avail Capacity ...
            if len(cols) >= 4:
                return cols[3]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def _skills_version(root: Path) -> str:
    path = root / "packaging" / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _count_dir_entries(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for p in path.iterdir() if not p.name.startswith("."))
    except OSError:
        return 0


def _safety_from_doctor(doctor: Dict[str, Any]) -> Dict[str, bool]:
    hook = False
    deny = False
    for c in doctor.get("checks") or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or ""
        sev = c.get("severity") or ""
        if cid in ("file.safety_hook", "safety.allow", "safety.deny") and sev == "pass":
            hook = True
        if cid == "cfg.deny_rules" and sev == "pass":
            deny = True
        # also match file label style
        if cid.startswith("file.") and "safety" in cid and sev == "pass":
            hook = True
    # Prefer filesystem truth as backup.
    home = Path.home()
    if (home / ".grok" / "hooks" / "safety-guard.json").is_file():
        hook = True
    cfg = home / ".grok" / "config.toml"
    if cfg.is_file():
        try:
            text = cfg.read_text(encoding="utf-8")
            if "[permission]" in text and "deny" in text:
                deny = True
        except OSError:
            pass
    return {"hook": hook, "deny_rules": deny}


def build_status(root: Path, doctor: Dict[str, Any]) -> Dict[str, Any]:
    lab = lab_data_root()
    modules = {name: "off" for name in MODULE_NAMES}
    modules["observatory"] = "ok"
    if (root / "modules" / "showroom" / "regen_index.py").is_file():
        modules["showroom"] = "ok"

    showroom_entries = root / "showroom" / "entries"
    showroom_inbox = lab / "showroom" / "inbox"

    host = socket.gethostname().split(".")[0]
    status: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "host": host,
        "doctor": {
            "pass": int(doctor.get("pass", 0)),
            "warn": int(doctor.get("warn", 0)),
            "fail": int(doctor.get("fail", 0)),
            "operational": bool(doctor.get("operational", doctor.get("fail", 1) == 0)),
            "checks": doctor.get("checks") or [],
        },
        "modules": modules,
        "ollama_models": _ollama_models(),
        "recent_experiments": [],
        "showroom_count": _count_dir_entries(showroom_entries),
        "showroom_inbox_count": _count_dir_entries(showroom_inbox),
        "disk_free_home": _disk_free_home(),
        "safety": _safety_from_doctor(doctor),
        "lab_skills_version": _skills_version(root),
    }
    return status


def write_snapshot(root: Path, status: Dict[str, Any]) -> Dict[str, Path]:
    data_dir = root / "data"
    dash_dir = root / "dashboard"
    data_dir.mkdir(parents=True, exist_ok=True)
    dash_dir.mkdir(parents=True, exist_ok=True)

    status_path = data_dir / "status.json"
    embed_path = dash_dir / "data-embed.js"

    payload = json.dumps(status, indent=2, sort_keys=False)
    status_path.write_text(payload + "\n", encoding="utf-8")

    embed = (
        "// generated by lab observatory snapshot — do not edit\n"
        "window.GROK_LAB_STATUS = %s;\n" % json.dumps(status, sort_keys=False)
    )
    embed_path.write_text(embed, encoding="utf-8")
    return {"status_json": status_path, "data_embed_js": embed_path}


def cmd_snapshot(root: Path, quiet: bool = False) -> int:
    doctor = _run_doctor_json(root)
    status = build_status(root, doctor)
    paths = write_snapshot(root, status)
    if not quiet:
        print(
            "snapshot ok  pass=%s warn=%s fail=%s  %s  %s"
            % (
                status["doctor"]["pass"],
                status["doctor"]["warn"],
                status["doctor"]["fail"],
                paths["status_json"],
                paths["data_embed_js"],
            )
        )
    return 0


def _open_file(path: Path) -> None:
    url = path.resolve().as_uri()
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        # Linux fallback
        try:
            subprocess.run(["xdg-open", str(path)], check=False)
        except OSError:
            print("Open: %s" % url)


def cmd_dash(root: Path) -> int:
    # Always snapshot first so file:// embed is fresh.
    rc = cmd_snapshot(root, quiet=False)
    if rc != 0:
        return rc
    html = root / "dashboard" / "index.html"
    if not html.is_file():
        print("error: dashboard missing: %s" % html, file=sys.stderr)
        return 1
    _open_file(html)
    return 0


def cmd_report(root: Path) -> int:
    status_path = root / "data" / "status.json"
    if not status_path.is_file():
        print("No status.json — run: lab observatory snapshot", file=sys.stderr)
        return 1
    status = json.loads(status_path.read_text(encoding="utf-8"))
    d = status.get("doctor") or {}
    print(
        "generated_at=%s host=%s operational=%s pass=%s warn=%s fail=%s"
        % (
            status.get("generated_at"),
            status.get("host"),
            d.get("operational"),
            d.get("pass"),
            d.get("warn"),
            d.get("fail"),
        )
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lab observatory",
        description="Observatory — Mission Control snapshots",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="snapshot",
        choices=["snapshot", "dash", "report", "help"],
    )
    args = parser.parse_args(argv)

    if args.command == "help":
        parser.print_help()
        return 0

    root = repo_root()
    # Prefer env override when running from worktree.
    env_repo = os.environ.get("GROK_LAB_REPO")
    if env_repo:
        root = Path(env_repo).resolve()
    else:
        # cli.py lives in modules/observatory/ — use that as authority when present
        here_root = Path(__file__).resolve().parent.parent.parent
        if (here_root / "bin" / "doctor").is_file():
            root = here_root

    if args.command == "snapshot":
        return cmd_snapshot(root)
    if args.command == "dash":
        return cmd_dash(root)
    if args.command == "report":
        return cmd_report(root)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

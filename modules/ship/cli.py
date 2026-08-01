#!/usr/bin/env python3
# Grok Star Lab — Ship Bay CLI (PR8 stub)
# lab ship check|run|pr
"""Offline ship gate: local checks, optional showroom inbox capture. No publish."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# lib/ on sys.path when run as modules/ship/cli.py
_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO / "lib"))

from lab_paths import lab_data_root, repo_root  # noqa: E402


def _root() -> Path:
    env = os.environ.get("GROK_LAB_REPO")
    if env:
        return Path(env).resolve()
    return repo_root()


def _shipcheck_path() -> Path:
    return _root() / "modules" / "ship" / "shipcheck.sh"


def run_shipcheck(
    project: Path,
    *,
    no_doctor: bool = False,
) -> int:
    script = _shipcheck_path()
    if not script.is_file():
        print(f"error: missing {script}", file=sys.stderr)
        return 1
    cmd: List[str] = ["bash", str(script), str(project)]
    if no_doctor:
        cmd.append("--no-doctor")
    env = os.environ.copy()
    env["ROOT"] = str(_root())
    proc = subprocess.run(cmd, env=env)
    return int(proc.returncode)


def _auto_capture_enabled() -> bool:
    if os.environ.get("GROK_LAB_NO_CAPTURE", "").strip() in ("1", "true", "yes"):
        return False
    cfg = lab_data_root() / "config.toml"
    if not cfg.is_file():
        return True  # default on (design K7)
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        if key.strip() == "showroom_auto_capture":
            return val.strip().strip('"').lower() in ("true", "1", "yes")
    return True


def _branch_skips_capture(project: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(project), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if out.startswith("wip/") or out.startswith("tmp/"):
        return f"branch {out} matches wip/* or tmp/*"
    return None


def _capture_from_ship(
    project: Path,
    title: Optional[str],
) -> Optional[Path]:
    # Import capture API lazily so shipcheck-only use needs no showroom
    showroom_dir = _root() / "modules" / "showroom"
    if str(showroom_dir) not in sys.path:
        sys.path.insert(0, str(showroom_dir))
    from capture import capture_ship  # type: ignore

    name = title or project.name
    proj = project.name
    return capture_ship(
        title=name,
        project=proj,
        summary=f"Ship check passed for {project}",
        paths=[str(project)],
        proof_commands=[f"lab ship check --project {project}"],
    )


def cmd_check(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    return run_shipcheck(project, no_doctor=args.no_doctor)


def cmd_run(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    code = run_shipcheck(project, no_doctor=args.no_doctor)
    if code != 0:
        print("ship: checks failed — skip capture", file=sys.stderr)
        return code

    if args.no_capture:
        print("ship: capture skipped (--no-capture)")
        return 0
    if not _auto_capture_enabled():
        print("ship: capture skipped (showroom_auto_capture=false or GROK_LAB_NO_CAPTURE)")
        return 0
    reason = _branch_skips_capture(project)
    if reason:
        print(f"ship: capture skipped ({reason})")
        return 0

    try:
        path = _capture_from_ship(project, args.title)
    except Exception as exc:  # noqa: BLE001 — surface cleanly for CLI
        print(f"ship: capture failed: {exc}", file=sys.stderr)
        return 1
    if path:
        print(f"ship: showroom inbox capture → {path}")
    return 0


def cmd_pr(args: argparse.Namespace) -> int:
    """Optional PR helper. Online (gh) not required; offline notes only."""
    project = Path(args.project).resolve()
    code = run_shipcheck(project, no_doctor=args.no_doctor)
    if code != 0:
        return code

    print()
    print("PR path (optional / online):")
    print("  1. Commit on a feature branch (no force-push).")
    print("  2. If gh is authed:  gh pr create")
    print("  3. Capture for later showcase:")
    print(
        f'     lab showroom capture --from-ship --project {project.name} '
        f'--title "<short>"'
    )
    if args.with_gh:
        gh = _which("gh")
        if not gh:
            print("warn: gh not on PATH — printed offline steps only", file=sys.stderr)
            return 0
        # Do not auto-create; just show auth status.
        subprocess.run([gh, "auth", "status"], check=False)
    return 0


def _which(name: str) -> Optional[str]:
    from shutil import which

    return which(name)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab ship",
        description="Ship Bay — local checks and optional showroom capture (inbox only).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--project",
            default=os.getcwd(),
            help="project directory (default: cwd)",
        )
        sp.add_argument(
            "--no-doctor",
            action="store_true",
            help="skip optional doctor probe",
        )

    sp_check = sub.add_parser("check", help="run local shipcheck only")
    add_common(sp_check)
    sp_check.set_defaults(func=cmd_check)

    sp_run = sub.add_parser(
        "run",
        help="shipcheck then capture to showroom inbox (no publish)",
    )
    add_common(sp_run)
    sp_run.add_argument("--title", default=None, help="capture title")
    sp_run.add_argument(
        "--no-capture",
        action="store_true",
        help="skip showroom inbox write",
    )
    sp_run.set_defaults(func=cmd_run)

    sp_pr = sub.add_parser(
        "pr",
        help="shipcheck + print PR notes (gh optional)",
    )
    add_common(sp_pr)
    sp_pr.add_argument(
        "--with-gh",
        action="store_true",
        help="also run gh auth status if available",
    )
    sp_pr.set_defaults(func=cmd_pr)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

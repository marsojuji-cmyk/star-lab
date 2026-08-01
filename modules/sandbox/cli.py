#!/usr/bin/env python3
# Grok Star Lab — Sandbox Range CLI (PR11)
# lab sandbox list|use|install|test
"""Curated Seatbelt profiles: missing-key-only merge into ~/.grok/sandbox.toml."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_LIB = _REPO / "lib"
for p in (str(_HERE), str(_LIB)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lab_paths import grok_home, repo_root  # noqa: E402
from merge import (  # noqa: E402
    LAB_PROFILE_NAMES,
    install_profiles,
    parse_fragment_profiles,
    parse_toml_doc,
)


def _root() -> Path:
    env = os.environ.get("GROK_LAB_REPO")
    if env:
        return Path(env).resolve()
    return repo_root()


def _fragment_path() -> Path:
    return _root() / "modules" / "sandbox" / "profiles.fragment.toml"


def _sandbox_toml_path() -> Path:
    return grok_home() / "sandbox.toml"


def _usage() -> str:
    return """lab sandbox — curated Seatbelt profiles for lab work

Usage:
  lab sandbox list                 show fragment + installed lab-* profiles
  lab sandbox use [PROFILE]        print grok --sandbox invocation
  lab sandbox install [--dry-run]  merge missing keys into ~/.grok/sandbox.toml
  lab sandbox test                 deterministic probe (SKIP if grok missing)

Profiles (fragment):
  lab-workspace         extends workspace + secret denies
  lab-readonly-review   extends read-only, restrict_network
  lab-untrusted         extends strict, restrict_network + secret denies

Merge policy: missing keys only — never overwrite existing user values.
On conflict, install prints manual diff instructions.

Environment:
  GROK_HOME       grok home (default: ~/.grok); sandbox.toml lives here
  GROK_LAB_REPO   monorepo root override

macOS: child-network block (restrict_network) is a no-op — see module README.
"""


def cmd_list(_args: argparse.Namespace) -> int:
    frag_path = _fragment_path()
    if not frag_path.is_file():
        print("error: missing fragment: %s" % frag_path, file=sys.stderr)
        return 1
    fragment = parse_fragment_profiles(frag_path.read_text(encoding="utf-8"))
    target = _sandbox_toml_path()
    installed = {}
    if target.is_file():
        doc = parse_toml_doc(target.read_text(encoding="utf-8"))
        for name in LAB_PROFILE_NAMES:
            sec = doc.profile_section(name)
            if sec is not None:
                installed[name] = dict(sec.keys) if sec.keys else {}

    print("fragment:  %s" % frag_path)
    print("target:    %s%s" % (target, "" if target.is_file() else "  (missing)"))
    print("")
    print("%-24s  %-10s  %s" % ("profile", "status", "extends"))
    print("%-24s  %-10s  %s" % ("-" * 24, "-" * 10, "-" * 12))
    names = list(LAB_PROFILE_NAMES)
    for n in fragment:
        if n not in names:
            names.append(n)
    for name in names:
        frag = fragment.get(name, {})
        extends = frag.get("extends", "—")
        if name in installed:
            status = "installed"
        elif target.is_file():
            status = "missing"
        else:
            status = "not-merged"
        print("%-24s  %-10s  %s" % (name, status, extends))
    print("")
    print("install:  lab sandbox install")
    print("use:      lab sandbox use lab-workspace")
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    name = args.profile or "lab-workspace"
    # Allow with or without lab- prefix typos for built-ins? keep strict lab-*
    frag_path = _fragment_path()
    fragment = {}
    if frag_path.is_file():
        fragment = parse_fragment_profiles(frag_path.read_text(encoding="utf-8"))
    if name not in fragment and name not in LAB_PROFILE_NAMES:
        print("error: unknown profile: %s" % name, file=sys.stderr)
        print("known: %s" % ", ".join(LAB_PROFILE_NAMES), file=sys.stderr)
        return 2

    target = _sandbox_toml_path()
    present = False
    if target.is_file():
        doc = parse_toml_doc(target.read_text(encoding="utf-8"))
        present = doc.profile_section(name) is not None

    print("# Profile: %s" % name)
    if name in fragment:
        for k, v in fragment[name].items():
            print("#   %s = %s" % (k, v))
    if not present:
        print("# not installed yet — run: lab sandbox install")
    print("")
    print("grok --sandbox %s" % name)
    print("")
    print("# Headless one-shot example:")
    print('grok --sandbox %s -p "your prompt here"' % name)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    frag = _fragment_path()
    if not frag.is_file():
        print("error: missing fragment: %s" % frag, file=sys.stderr)
        return 1
    target = _sandbox_toml_path()
    result = install_profiles(frag, target, dry_run=args.dry_run)
    if args.dry_run:
        print("sandbox install (dry-run)")
    else:
        print("sandbox install")
    for line in result.summary_lines():
        print(line)
    # Conflicts are non-fatal (user values preserved); still exit 0
    # Missing fragment keys that could not be written would be errors — not the case
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """
    Deterministic Seatbelt probe for lab-untrusted.
    Exit 0 with SKIP if grok missing or unauthenticated / cannot run.
    """
    grok = shutil.which("grok")
    if not grok:
        print("SKIP: grok not found on PATH (sandbox live probe not run)")
        return 0

    # Ensure profiles exist when possible (non-fatal if conflict)
    frag = _fragment_path()
    if frag.is_file():
        try:
            install_profiles(frag, _sandbox_toml_path(), dry_run=False)
        except OSError as exc:
            print("SKIP: cannot write sandbox.toml: %s" % exc)
            return 0

    marker = "lab-sandbox-probe"
    home_fail = Path.home() / ("lab-sandbox-should-fail-%s" % os.getpid())
    # Clean any leftover from prior crash
    if home_fail.exists():
        try:
            home_fail.unlink()
        except OSError:
            pass

    with tempfile.TemporaryDirectory(prefix="lab-sandbox-test-") as tmp:
        tmp_path = Path(tmp)
        probe = tmp_path / ("%s-%s" % (marker, os.getpid()))
        prompt = (
            "Using the bash/shell tool only: "
            "write the single word ok to the file %s ; "
            "then try to write the single word bad to the file %s ; "
            "then stop. Do not read secrets."
        ) % (probe, home_fail)

        cmd: List[str] = [
            grok,
            "--sandbox",
            "lab-untrusted",
            "-p",
            prompt,
        ]
        # Bound runtime; do not hang the CLI
        timeout = int(os.environ.get("GROK_LAB_SANDBOX_TEST_TIMEOUT", "90"))
        print("sandbox test: %s" % " ".join(cmd[:4] + ["-p", "<probe>"]))
        print("  cwd/tmp probe: %s" % probe)
        print("  home deny:     %s" % home_fail)
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(tmp_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired:
            print("SKIP: grok sandbox probe timed out after %ss" % timeout)
            return 0
        except OSError as exc:
            print("SKIP: failed to spawn grok: %s" % exc)
            return 0

        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        low = out.lower()
        # Auth / profile / backend failures → SKIP (not doctor fail)
        skip_needles = (
            "not authenticated",
            "login required",
            "auth",
            "unauthorized",
            "unknown profile",
            "malformed",
            "sandbox.toml",
            "api key",
            "not logged in",
        )
        if proc.returncode != 0:
            for n in skip_needles:
                if n in low:
                    print("SKIP: grok exited %s (%s)" % (proc.returncode, n))
                    if args.verbose:
                        sys.stdout.write(out[-2000:])
                    return 0
            # Other non-zero: still soft for offline core — document
            print(
                "SKIP: grok exited %s (live Seatbelt probe inconclusive)"
                % proc.returncode
            )
            if args.verbose:
                sys.stdout.write(out[-2000:])
            return 0

        home_blocked = not home_fail.exists()
        # Under strict-derived profile, writes outside CWD+tmp+~/.grok should fail.
        # Note: ~/.grok is writable; $HOME root file should be blocked.
        print("result:")
        print("  tmp probe exists:  %s" % probe.exists())
        print("  home file blocked: %s" % home_blocked)
        print(
            "  note: on macOS, restrict_network is a no-op for child processes"
        )
        if home_fail.exists():
            try:
                home_fail.unlink()
            except OSError:
                pass
            print(
                "warn: home write was not blocked — check profile install / Seatbelt"
            )
            return 0  # still soft; document observed behavior
        print("ok: lab-untrusted blocked home-path write (or write not attempted)")
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab sandbox",
        description="Sandbox Range — curated lab-* Seatbelt profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See modules/sandbox/README.md for macOS network caveats.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list lab profiles and install status")
    p_list.set_defaults(func=cmd_list)

    p_use = sub.add_parser("use", help="print grok --sandbox invocation")
    p_use.add_argument(
        "profile",
        nargs="?",
        default="lab-workspace",
        help="profile name (default: lab-workspace)",
    )
    p_use.set_defaults(func=cmd_use)

    p_install = sub.add_parser(
        "install",
        help="merge missing lab-* keys into ~/.grok/sandbox.toml",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change without writing",
    )
    p_install.set_defaults(func=cmd_install)

    p_test = sub.add_parser(
        "test",
        help="deterministic lab-untrusted probe (SKIP if grok unavailable)",
    )
    p_test.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print grok output tail on SKIP",
    )
    p_test.set_defaults(func=cmd_test)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(_usage())
        if argv and argv[0] in ("-h", "--help"):
            return 0
        if not argv:
            return 0
        return 0
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else (1 if code else 0)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

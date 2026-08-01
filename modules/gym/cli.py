#!/usr/bin/env python3
# lab gym — Model Gym CLI (offline dolphin3 + optional remote Grok)
"""CLI entry: lab gym smoke|eval|list|help

Model policy (K15, K20)
-----------------------
Offline / smoke (default):
  Always uses Ollama model dolphin3:latest (override: GROK_LAB_DEFAULT_MODEL
  or --model). No network or Grok auth required.

Best-work track (`lab gym eval --track best`):
  Prefer remote Grok when environment has XAI_API_KEY or GROK set.
  Remote model id: GROK_LAB_BEST_MODEL (default grok-4) via xAI HTTP API.
  If remote is unavailable or fails → fall back to dolphin3:latest and log
  model_fallback=true. Offline success criteria never require remote Grok.

Ollama down:
  GROK_LAB_SKIP_OLLAMA=1 → exit 0 with SKIP message (CI-friendly).
  otherwise → exit 1 when the run needs Ollama.

Forge:
  When GROK_LAB_RUN_ID is set (under `lab forge run`), logs param model and
  metric pass_rate (plus n_pass, n_total, backend, track).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_MODULES = _HERE.parent
for p in (str(_REPO / "lib"), str(_MODULES)):
    if p not in sys.path:
        sys.path.insert(0, p)

from gym.harness import (  # noqa: E402
    DEFAULT_MODEL,
    exit_code_for,
    format_result,
    load_suite,
    remote_grok_available,
    resolve_model,
    run_suite,
    suites_dir,
)


def _usage() -> str:
    return """lab gym — Model Gym (offline-first eval harness)

Usage:
  lab gym smoke [--verbose]              # run suites/smoke.jsonl on dolphin3
  lab gym eval [SUITE] [--track smoke|best] [--model NAME] [--verbose]
  lab gym list                           # list built-in suites
  lab gym help

Suites:
  SUITE is a name (smoke) resolved under modules/gym/suites/, or a .jsonl path.
  Default suite for eval is smoke.

Model policy:
  smoke / default   → dolphin3:latest via Ollama (localhost:11434)   [K15]
  --track best      → remote Grok if XAI_API_KEY or GROK set; else dolphin3 [K20]
  --model NAME      → always wins

Environment:
  GROK_LAB_DEFAULT_MODEL   offline model (default: dolphin3:latest)
  GROK_LAB_BEST_MODEL      remote model when track=best (default: grok-4)
  XAI_API_KEY              xAI API key for remote Grok
  GROK                     if set (truthy), prefer remote path for --track best
  OLLAMA_HOST              default http://127.0.0.1:11434
  GROK_LAB_SKIP_OLLAMA=1   skip with exit 0 when Ollama is down (CI)
  GROK_LAB_RUN_ID          set by `lab forge run` → log model + pass_rate

Examples:
  lab gym smoke
  GROK_LAB_SKIP_OLLAMA=1 lab gym smoke
  lab gym eval smoke --verbose
  lab gym eval --track best
  lab forge run --exp gym-smoke --tag gym -- lab gym smoke
"""


def cmd_list(_args: argparse.Namespace) -> int:
    d = suites_dir()
    if not d.is_dir():
        print("(no suites dir: %s)" % d)
        return 0
    files = sorted(d.glob("*.jsonl"))
    if not files:
        print("(no suites in %s)" % d)
        return 0
    print("%-16s  %5s  %s" % ("name", "cases", "path"))
    for f in files:
        try:
            n = len(load_suite(f))
        except (OSError, ValueError):
            n = -1
        print("%-16s  %5s  %s" % (f.stem, n if n >= 0 else "?", f))
    # Document policy on list for operators
    model, backend, fb = resolve_model("smoke")
    print("")
    print(
        "default offline: model=%s backend=%s  remote_available=%s"
        % (model, backend, remote_grok_available())
    )
    bm, bb, _ = resolve_model("best")
    print(
        "track best:      model=%s backend=%s fallback_if_no_auth→%s"
        % (bm, bb, DEFAULT_MODEL)
    )
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    """Run smoke suite on offline dolphin3 (K15)."""
    result = run_suite(
        suite="smoke",
        track="smoke",
        model=args.model,
        timeout=args.timeout,
    )
    print(format_result(result, verbose=args.verbose))
    if result.skipped:
        print("gym: CI skip mode (GROK_LAB_SKIP_OLLAMA=1) — exit 0", file=sys.stderr)
    return exit_code_for(result)


def cmd_eval(args: argparse.Namespace) -> int:
    suite = args.suite or "smoke"
    track = args.track or "smoke"
    # Convenience: `lab gym eval smoke` with positional only
    result = run_suite(
        suite=suite,
        track=track,
        model=args.model,
        timeout=args.timeout,
    )
    print(format_result(result, verbose=args.verbose))
    if args.json:
        payload = {
            "suite": result.suite,
            "model": result.model,
            "backend": result.backend,
            "track": result.track,
            "model_fallback": result.model_fallback,
            "n_total": result.n_total,
            "n_pass": result.n_pass,
            "pass_rate": result.pass_rate,
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
            "error": result.error,
            "ok": result.ok,
            "cases": [
                {
                    "id": c.id,
                    "passed": c.passed,
                    "reason": c.reason,
                    "response": c.response if args.verbose else None,
                }
                for c in result.cases
            ],
        }
        print(json.dumps(payload, indent=2))
    if result.skipped:
        print("gym: CI skip mode (GROK_LAB_SKIP_OLLAMA=1) — exit 0", file=sys.stderr)
    return exit_code_for(result)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab gym",
        description="Model Gym — offline Ollama eval + optional remote Grok",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_usage(),
    )
    sub = p.add_subparsers(dest="command")

    ps = sub.add_parser("smoke", help="Run smoke suite on dolphin3 (offline)")
    ps.add_argument("--model", default=None, help="Override model (default dolphin3:latest)")
    ps.add_argument("--timeout", type=float, default=120.0)
    ps.add_argument("--verbose", "-v", action="store_true")
    ps.set_defaults(func=cmd_smoke)

    pe = sub.add_parser("eval", help="Evaluate a suite (default: smoke)")
    pe.add_argument(
        "suite",
        nargs="?",
        default="smoke",
        help="Suite name or path (default: smoke)",
    )
    pe.add_argument(
        "--track",
        choices=("smoke", "best"),
        default="smoke",
        help="smoke=offline dolphin3; best=remote Grok when available",
    )
    pe.add_argument("--model", default=None, help="Explicit model (wins over track)")
    pe.add_argument("--timeout", type=float, default=120.0)
    pe.add_argument("--verbose", "-v", action="store_true")
    pe.add_argument("--json", action="store_true", help="Also emit JSON summary")
    pe.set_defaults(func=cmd_eval)

    pl = sub.add_parser("list", help="List built-in suites")
    pl.set_defaults(func=cmd_list)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        print(_usage())
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

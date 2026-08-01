#!/usr/bin/env python3
# Doctor JSON schema helpers (schema_version 1). Python 3.9+.
"""Emit and parse lab doctor --json documents."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_document(
    pass_n: int,
    warn_n: int,
    fail_n: int,
    checks: List[Dict[str, str]],
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a versioned doctor JSON object."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or _utc_now_iso(),
        "pass": int(pass_n),
        "warn": int(warn_n),
        "fail": int(fail_n),
        "operational": int(fail_n) == 0,
        "checks": checks,
    }


def checks_from_tsv(path: str) -> List[Dict[str, str]]:
    """Load checks from TSV: id \\t severity \\t label \\t detail."""
    checks: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            while len(parts) < 4:
                parts.append("")
            cid, severity, label, detail = parts[0], parts[1], parts[2], parts[3]
            checks.append(
                {
                    "id": cid,
                    "severity": severity,
                    "label": label,
                    "detail": detail,
                }
            )
    return checks


def emit_from_tsv(
    pass_n: int,
    warn_n: int,
    fail_n: int,
    tsv_path: str,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    return build_document(
        pass_n, warn_n, fail_n, checks_from_tsv(tsv_path), generated_at=generated_at
    )


def loads(text: str) -> Dict[str, Any]:
    return json.loads(text)


def validate_minimal(doc: Dict[str, Any]) -> None:
    """Raise ValueError if required keys missing or wrong types."""
    if not isinstance(doc, dict):
        raise ValueError("doctor json must be an object")
    for key in ("schema_version", "pass", "warn", "fail", "operational", "checks"):
        if key not in doc:
            raise ValueError("missing key: %s" % key)
    if not isinstance(doc["checks"], list):
        raise ValueError("checks must be a list")
    if int(doc["schema_version"]) < 1:
        raise ValueError("unsupported schema_version")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Doctor JSON emit/validate")
    sub = parser.add_subparsers(dest="cmd", required=True)

    em = sub.add_parser("emit", help="Emit JSON from counters + TSV checks file")
    em.add_argument("--pass", dest="pass_n", type=int, required=True)
    em.add_argument("--warn", dest="warn_n", type=int, required=True)
    em.add_argument("--fail", dest="fail_n", type=int, required=True)
    em.add_argument("--tsv", required=True, help="Path to checks TSV")
    em.add_argument("--generated-at", default=None)

    val = sub.add_parser("validate", help="Validate doctor JSON on stdin")
    val.add_argument("--file", default=None, help="File path (default stdin)")

    args = parser.parse_args(argv)

    if args.cmd == "emit":
        doc = emit_from_tsv(
            args.pass_n,
            args.warn_n,
            args.fail_n,
            args.tsv,
            generated_at=args.generated_at,
        )
        json.dump(doc, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
        # Emit always exits 0 on successful write; doctor owns fail-exit policy.
        return 0

    if args.cmd == "validate":
        if args.file:
            with open(args.file, "r", encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = sys.stdin.read()
        doc = loads(text)
        validate_minimal(doc)
        print("ok schema_version=%s checks=%d" % (doc["schema_version"], len(doc["checks"])))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""lab weights — safetensors interchange standard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "modules"))

from weights.layout import LAYOUT_DOC
from weights.validate import validate_path, publish_check, validate_safetensors_file
from weights.convert import convert_torch_to_safetensors


def cmd_layout(_args: argparse.Namespace) -> int:
    print(LAYOUT_DOC)
    print()
    print("Rule: train anywhere → publish safetensors → load via thin adapters.")
    print("Doc:  docs/SAFETENSORS-STANDARD.md")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    r = validate_path(Path(args.path))
    if args.json:
        # trim huge tensor lists unless verbose
        out = dict(r)
        if not args.verbose and "tensors" in out and isinstance(out["tensors"], list):
            out["tensors"] = out["tensors"][:5]
            out["tensors_truncated"] = True
        if not args.verbose and "reports" in out:
            for rep in out.get("reports") or []:
                if isinstance(rep, dict) and "tensors" in rep:
                    rep["n_tensors"] = rep.get("n_tensors") or len(rep.get("tensors") or [])
                    rep.pop("tensors", None)
        print(json.dumps(out, indent=2))
    else:
        ok = r.get("ok")
        print(f"weights: validate ok={ok} path={r.get('path') or args.path}")
        if r.get("error"):
            print(f"  error: {r['error']}")
        if r.get("issues"):
            for i in r["issues"]:
                print(f"  issue: {i}")
        if r.get("warnings"):
            for w in r["warnings"]:
                print(f"  warn: {w}")
        if r.get("n_tensors") is not None:
            print(f"  tensors: {r.get('n_tensors')}")
        if r.get("suggestion"):
            print(f"  next: {r['suggestion']}")
    return 0 if r.get("ok") else 1


def cmd_publish_check(args: argparse.Namespace) -> int:
    r = publish_check(Path(args.path), strict=args.strict)
    if args.json:
        out = dict(r)
        out.pop("reports", None)
        print(json.dumps(out, indent=2))
    else:
        print(f"weights: publish-check ok={r.get('ok')} strict={r.get('strict')}")
        print(f"  path: {r.get('path')}")
        print(f"  config: {r.get('has_config')} tokenizer: {r.get('has_tokenizer')}")
        for i in r.get("issues") or []:
            print(f"  issue: {i}")
        for w in r.get("warnings") or []:
            print(f"  warn: {w}")
        if r.get("pickle_files"):
            print(f"  pickle: {r['pickle_files']}")
    return 0 if r.get("ok") else 1


def cmd_convert(args: argparse.Namespace) -> int:
    try:
        r = convert_torch_to_safetensors(
            Path(args.input),
            Path(args.output),
            metadata={"source": str(args.input)},
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"weights: converted {r['input']} → {r['output']} (n={r['n_tensors']})")
        if r.get("skipped_keys"):
            print(f"  skipped non-tensors: {r['skipped_keys'][:10]}")
    # always validate output
    vr = validate_safetensors_file(Path(args.output))
    if not vr.get("ok"):
        print(f"error: output failed validate: {vr}", file=sys.stderr)
        return 1
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    r = validate_safetensors_file(Path(args.path))
    if not r.get("ok"):
        print(json.dumps(r, indent=2))
        return 1
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"file: {r['path']}  tensors={r['n_tensors']}  bytes={r['file_bytes']}")
        if r.get("metadata"):
            print(f"metadata: {r['metadata']}")
        for t in (r.get("tensors") or [])[: args.limit]:
            print(f"  {t['name']}: dtype={t.get('dtype')} shape={t.get('shape')}")
        if r.get("n_tensors", 0) > args.limit:
            print(f"  … {r['n_tensors'] - args.limit} more")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="lab weights",
        description="Safetensors-first weight interchange (Star Lab standard)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("layout", help="Print canonical package layout")
    l.set_defaults(func=cmd_layout)

    v = sub.add_parser("validate", help="Validate .safetensors file or package dir")
    v.add_argument("path")
    v.add_argument("--json", action="store_true")
    v.add_argument("--verbose", action="store_true")
    v.set_defaults(func=cmd_validate)

    pc = sub.add_parser("publish-check", help="Package readiness for lab publish")
    pc.add_argument("path", help="Model package directory")
    pc.add_argument("--strict", action="store_true", help="Fail on any pickle/torch ckpt")
    pc.add_argument("--json", action="store_true")
    pc.set_defaults(func=cmd_publish_check)

    c = sub.add_parser("convert", help="Convert PyTorch .pt/.pth → .safetensors")
    c.add_argument("--input", "-i", required=True)
    c.add_argument("--output", "-o", required=True)
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_convert)

    m = sub.add_parser("metadata", help="List tensor names/shapes from header")
    m.add_argument("path")
    m.add_argument("--limit", type=int, default=50)
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_metadata)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

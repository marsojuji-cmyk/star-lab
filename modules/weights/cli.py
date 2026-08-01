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
from weights.manifest import (
    SCHEMA_VERSION,
    SCHEMA_PATH,
    init_manifest,
    seal_manifest,
    load_manifest,
    validate_manifest,
    bump_semver,
    version_bump_note,
    save_manifest,
)


def cmd_layout(_args: argparse.Namespace) -> int:
    print(LAYOUT_DOC)
    print()
    print("Rule: train anywhere → publish safetensors + manifest.json → load via adapters.")
    print(f"Manifest schema_version: {SCHEMA_VERSION}")
    print(f"Schema file: {SCHEMA_PATH}")
    print("Doc:  docs/SAFETENSORS-STANDARD.md  docs/MODEL-MANIFEST.md")
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


def cmd_manifest(args: argparse.Namespace) -> int:
    sub = args.manifest_cmd
    if sub == "schema":
        print(SCHEMA_PATH.read_text(encoding="utf-8"))
        return 0
    if sub == "init":
        m = init_manifest(
            Path(args.path),
            model_id=args.model_id,
            version=args.version,
            arch=args.arch,
            framework=args.framework,
            parent_version=args.parent_version,
            body_id=args.body_id,
            seal=args.seal,
        )
        if args.json:
            print(json.dumps(m, indent=2))
        else:
            print(f"weights: wrote {Path(args.path) / 'manifest.json'}")
            print(
                f"  model_id={m['model_id']} version={m['version']} "
                f"schema={m['schema_version']}"
            )
            print(f"  weights_uri={m['weights_uri']} sha256={m['weights_sha256'][:16]}…")
            if m["weights_sha256"] == "0" * 64:
                print("  next: lab weights manifest seal " + args.path)
        return 0
    if sub == "seal":
        try:
            m = seal_manifest(Path(args.path))
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(
            json.dumps(m, indent=2)
            if args.json
            else f"weights: sealed sha256={m['weights_sha256']}"
        )
        return 0
    if sub == "validate":
        path = Path(args.path)
        try:
            m = load_manifest(path)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        pkg = path if path.is_dir() else path.parent
        r = validate_manifest(m, package_dir=pkg, check_hash=not args.no_hash)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(
                f"weights: manifest ok={r['ok']} engine={r['schema_engine']} "
                f"hash_ok={r['hash_ok']}"
            )
            for i in r.get("issues") or []:
                print(f"  issue: {i}")
        return 0 if r.get("ok") else 1
    if sub == "bump":
        path = Path(args.path)
        m = load_manifest(path)
        old = m["version"]
        m["parent_version"] = old
        m["version"] = bump_semver(old, args.part)
        note = version_bump_note(args.part)
        if args.notes:
            m["notes"] = args.notes
        elif note:
            m["notes"] = f"bump {args.part}: {note}"
        pkg = path if path.is_dir() else path.parent
        save_manifest(pkg, m)
        print(
            json.dumps({"old": old, "new": m["version"], "part": args.part}, indent=2)
            if args.json
            else f"weights: version {old} → {m['version']} ({args.part}: {note})"
        )
        return 0
    if sub == "show":
        m = load_manifest(Path(args.path))
        print(json.dumps(m, indent=2))
        return 0
    print("error: manifest init|seal|validate|bump|show|schema", file=sys.stderr)
    return 2


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

    mf = sub.add_parser("manifest", help="Model versioning manifest (JSON Schema)")
    mf_sub = mf.add_subparsers(dest="manifest_cmd", required=True)

    mf_i = mf_sub.add_parser("init", help="Create manifest.json")
    mf_i.add_argument("path", help="Package directory")
    mf_i.add_argument("--model-id", required=True)
    mf_i.add_argument("--version", default="0.1.0")
    mf_i.add_argument("--arch", default="unknown")
    mf_i.add_argument(
        "--framework",
        default="other",
        choices=["pytorch", "mlx", "jax", "numpy", "other"],
    )
    mf_i.add_argument("--parent-version", default=None)
    mf_i.add_argument("--body-id", default=None)
    mf_i.add_argument("--seal", action="store_true", help="Hash weights immediately")
    mf_i.add_argument("--json", action="store_true")
    mf_i.set_defaults(func=cmd_manifest, manifest_cmd="init")

    mf_s = mf_sub.add_parser("seal", help="Recompute weights_sha256")
    mf_s.add_argument("path")
    mf_s.add_argument("--json", action="store_true")
    mf_s.set_defaults(func=cmd_manifest, manifest_cmd="seal")

    mf_v = mf_sub.add_parser("validate", help="Validate manifest (+ hash if package)")
    mf_v.add_argument("path", help="Package dir or manifest.json")
    mf_v.add_argument("--no-hash", action="store_true")
    mf_v.add_argument("--json", action="store_true")
    mf_v.set_defaults(func=cmd_manifest, manifest_cmd="validate")

    mf_b = mf_sub.add_parser("bump", help="Semver bump (sets parent_version)")
    mf_b.add_argument("path")
    mf_b.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    mf_b.add_argument("--notes", default="")
    mf_b.add_argument("--json", action="store_true")
    mf_b.set_defaults(func=cmd_manifest, manifest_cmd="bump")

    mf_sh = mf_sub.add_parser("show", help="Print manifest.json")
    mf_sh.add_argument("path")
    mf_sh.set_defaults(func=cmd_manifest, manifest_cmd="show")

    mf_sc = mf_sub.add_parser("schema", help="Print JSON Schema")
    mf_sc.set_defaults(func=cmd_manifest, manifest_cmd="schema")

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

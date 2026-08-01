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
from weights.tokenizer_manifest import (
    SCHEMA_VERSION as TOK_SCHEMA_VERSION,
    SCHEMA_PATH as TOK_SCHEMA_PATH,
    init_tokenizer_manifest,
    seal_tokenizer_manifest,
    load_tokenizer_manifest,
    validate_tokenizer_manifest,
    freeze_tokenizer,
    bump_tokenizer,
    bind_tokenizer_to_model_manifest,
    assert_tokenizer_compatible,
)
from weights.embedding_drift import (
    load_slice_file,
    run_drift_eval,
    write_example_slices,
    DriftGateConfig,
)


def cmd_layout(_args: argparse.Namespace) -> int:
    print(LAYOUT_DOC)
    print()
    print("Rule: train anywhere → publish safetensors + manifest.json → load via adapters.")
    print(f"Manifest schema_version: {SCHEMA_VERSION}")
    print(f"Schema file: {SCHEMA_PATH}")
    print(
        "Doc:  docs/SAFETENSORS-STANDARD.md  docs/MODEL-MANIFEST.md  "
        "docs/TOKENIZER-VERSIONING.md  docs/EMBEDDING-DRIFT.md"
    )
    print(f"Tokenizer manifest schema: {TOK_SCHEMA_VERSION}")
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


def cmd_drift(args: argparse.Namespace) -> int:
    sub = args.drift_cmd
    if sub == "example":
        p = write_example_slices(Path(args.path))
        print(f"weights: wrote example slices → {p}")
        return 0
    if sub == "eval":
        items = load_slice_file(Path(args.path))
        cfg = DriftGateConfig()
        if args.config:
            raw = json.loads(Path(args.config).read_text(encoding="utf-8"))
            for k, v in raw.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        report = run_drift_eval(items, cfg=cfg, nn_k=args.nn_k)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            g = report.get("gate") or {}
            print("═══ Embedding expansion drift ═══")
            print(f"items: {report.get('n_items')}  slices: {report.get('slice_counts')}")
            cos = (report.get("cosine_shift") or {}).get("by_slice") or {}
            for sl in ("legacy", "new_token", "mixed"):
                a = cos.get(sl)
                if a:
                    print(
                        f"  cosine_shift[{sl}]: mean={a.get('mean_cosine_shift'):.4f} "
                        f"max={a.get('max_cosine_shift'):.4f} n={a.get('n')}"
                    )
            nn = report.get("nn_stability") or {}
            if nn.get("mean_jaccard") is not None:
                print(f"  nn_jaccard: {nn['mean_jaccard']:.3f} (k={nn.get('k')})")
            tasks = report.get("task_metrics") or {}
            leg = tasks.get("legacy") or {}
            if leg.get("acc_delta") is not None:
                print(
                    f"  task legacy: acc_base={leg.get('acc_baseline')} "
                    f"acc_exp={leg.get('acc_expanded')} delta={leg.get('acc_delta')}"
                )
            print(f"verdict: {g.get('verdict')}")
            for r in g.get("reasons") or []:
                print(f"  - {r}")
            print("Doc: docs/EMBEDDING-DRIFT.md")
        v = (report.get("gate") or {}).get("verdict")
        return {"expected": 0, "warning": 1, "harmful": 2, "insufficient_data": 3}.get(
            v, 3
        )
    print("error: drift example|eval", file=sys.stderr)
    return 2


def cmd_tokenizer(args: argparse.Namespace) -> int:
    sub = args.tokenizer_cmd
    if sub == "schema":
        print(TOK_SCHEMA_PATH.read_text(encoding="utf-8"))
        return 0
    if sub == "init":
        m = init_tokenizer_manifest(
            Path(args.path),
            tokenizer_id=args.tokenizer_id,
            version=args.version,
            tokenizer_mode=args.mode,
            parent_version=args.parent_version,
            seal=args.seal,
            base_vocab_size=args.vocab_size,
        )
        if args.json:
            print(json.dumps(m, indent=2))
        else:
            print(f"weights: tokenizer manifest → {Path(args.path) / 'tokenizer_manifest.json'}")
            print(
                f"  id={m['tokenizer_id']} version={m['version']} mode={m['tokenizer_mode']} "
                f"hash={m['tokenizer_hash'][:16]}…"
            )
            if m["tokenizer_hash"] == "0" * 64:
                print("  next: lab weights tokenizer seal " + args.path)
        return 0
    if sub == "seal":
        try:
            m = seal_tokenizer_manifest(Path(args.path))
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(
            json.dumps(m, indent=2)
            if args.json
            else f"weights: tokenizer sealed hash={m['tokenizer_hash']}"
        )
        return 0
    if sub == "validate":
        path = Path(args.path)
        try:
            m = load_tokenizer_manifest(path)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        pkg = path if path.is_dir() else path.parent
        r = validate_tokenizer_manifest(
            m, package_dir=pkg, check_hash=True, allow_dynamic=args.allow_dynamic
        )
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"weights: tokenizer ok={r['ok']} mode={r.get('tokenizer_mode')} hash_ok={r.get('hash_ok')}")
            for i in r.get("issues") or []:
                print(f"  issue: {i}")
        return 0 if r.get("ok") else 1
    if sub == "bump":
        try:
            m = bump_tokenizer(
                Path(args.path),
                args.part,
                force=args.force,
                notes=args.notes or "",
            )
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(
            json.dumps(m, indent=2)
            if args.json
            else f"weights: tokenizer version → {m['version']} (parent={m.get('parent_version')})"
        )
        return 0
    if sub == "freeze":
        m = freeze_tokenizer(Path(args.path))
        print(json.dumps(m, indent=2) if args.json else f"weights: tokenizer mode=frozen id={m['tokenizer_id']}")
        return 0
    if sub == "show":
        print(json.dumps(load_tokenizer_manifest(Path(args.path)), indent=2))
        return 0
    print("error: tokenizer init|seal|validate|bump|freeze|show|schema", file=sys.stderr)
    return 2


def cmd_manifest(args: argparse.Namespace) -> int:
    sub = args.manifest_cmd
    if sub == "schema":
        print(SCHEMA_PATH.read_text(encoding="utf-8"))
        return 0
    if sub == "bind-tokenizer":
        model_dir = Path(args.path)
        tok_dir = Path(args.tokenizer)
        try:
            mm = load_manifest(model_dir)
            tm = load_tokenizer_manifest(tok_dir)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        tv = validate_tokenizer_manifest(tm, package_dir=tok_dir, check_hash=True)
        if not tv.get("ok"):
            print("error: tokenizer package invalid:", file=sys.stderr)
            for i in tv.get("issues") or []:
                print(f"  {i}", file=sys.stderr)
            return 1
        mm = bind_tokenizer_to_model_manifest(
            mm,
            tm,
            tokenizer_uri=args.uri,
            embedding_remap=args.embedding_remap,
        )
        save_manifest(model_dir, mm)
        comp = assert_tokenizer_compatible(mm, tm)
        if args.json:
            print(json.dumps({"manifest": mm, "compatible": comp}, indent=2))
        else:
            print(
                f"weights: bound tokenizer {tm['tokenizer_id']}@{tm['version']} "
                f"hash={tm['tokenizer_hash'][:16]}… remap={args.embedding_remap}"
            )
            if not comp.get("ok"):
                for i in comp.get("issues") or []:
                    print(f"  issue: {i}")
                return 1
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

    # bind tokenizer into model manifest
    mf_b2 = mf_sub.add_parser(
        "bind-tokenizer",
        help="Copy sealed tokenizer id/version/hash into model manifest",
    )
    mf_b2.add_argument("path", help="Model package directory")
    mf_b2.add_argument(
        "--tokenizer",
        required=True,
        help="Tokenizer package directory (with tokenizer_manifest.json)",
    )
    mf_b2.add_argument("--uri", default="tokenizer", help="tokenizer_uri inside model package")
    mf_b2.add_argument(
        "--embedding-remap",
        default="none",
        choices=["none", "retrained", "required_unmet"],
    )
    mf_b2.add_argument("--json", action="store_true")
    mf_b2.set_defaults(func=cmd_manifest, manifest_cmd="bind-tokenizer")

    tk = sub.add_parser("tokenizer", help="Tokenizer artifact versioning (tokenizer-major rule)")
    tk_sub = tk.add_subparsers(dest="tokenizer_cmd", required=True)

    tk_i = tk_sub.add_parser("init", help="Create tokenizer_manifest.json (default mode=frozen)")
    tk_i.add_argument("path", help="Tokenizer package directory")
    tk_i.add_argument("--tokenizer-id", required=True)
    tk_i.add_argument("--version", default="1.0.0")
    tk_i.add_argument(
        "--mode",
        default="frozen",
        choices=["frozen", "append_only", "dynamic"],
    )
    tk_i.add_argument("--parent-version", default=None)
    tk_i.add_argument("--vocab-size", type=int, default=None)
    tk_i.add_argument("--seal", action="store_true")
    tk_i.add_argument("--json", action="store_true")
    tk_i.set_defaults(func=cmd_tokenizer, tokenizer_cmd="init")

    tk_s = tk_sub.add_parser("seal", help="Recompute tokenizer_hash")
    tk_s.add_argument("path")
    tk_s.add_argument("--json", action="store_true")
    tk_s.set_defaults(func=cmd_tokenizer, tokenizer_cmd="seal")

    tk_v = tk_sub.add_parser("validate", help="Validate tokenizer package")
    tk_v.add_argument("path")
    tk_v.add_argument("--allow-dynamic", action="store_true")
    tk_v.add_argument("--json", action="store_true")
    tk_v.set_defaults(func=cmd_tokenizer, tokenizer_cmd="validate")

    tk_b = tk_sub.add_parser("bump", help="Semver bump (content change → major)")
    tk_b.add_argument("path")
    tk_b.add_argument("--part", choices=["major", "minor", "patch"], default="major")
    tk_b.add_argument("--force", action="store_true")
    tk_b.add_argument("--notes", default="")
    tk_b.add_argument("--json", action="store_true")
    tk_b.set_defaults(func=cmd_tokenizer, tokenizer_cmd="bump")

    tk_f = tk_sub.add_parser("freeze", help="Set tokenizer_mode=frozen")
    tk_f.add_argument("path")
    tk_f.add_argument("--json", action="store_true")
    tk_f.set_defaults(func=cmd_tokenizer, tokenizer_cmd="freeze")

    tk_sh = tk_sub.add_parser("show", help="Print tokenizer_manifest.json")
    tk_sh.add_argument("path")
    tk_sh.set_defaults(func=cmd_tokenizer, tokenizer_cmd="show")

    tk_sc = tk_sub.add_parser("schema", help="Print tokenizer JSON Schema")
    tk_sc.set_defaults(func=cmd_tokenizer, tokenizer_cmd="schema")

    dr = sub.add_parser("drift", help="Embedding expansion before/after drift eval")
    dr_sub = dr.add_subparsers(dest="drift_cmd", required=True)
    dr_e = dr_sub.add_parser("example", help="Write synthetic three-slice JSONL")
    dr_e.add_argument("path", help="Output JSONL path")
    dr_e.set_defaults(func=cmd_drift, drift_cmd="example")
    dr_v = dr_sub.add_parser("eval", help="Run drift eval on slice file")
    dr_v.add_argument("path", help="JSONL/JSON with emb_baseline + emb_expanded")
    dr_v.add_argument("--config", help="JSON gate thresholds override")
    dr_v.add_argument("--nn-k", type=int, default=3)
    dr_v.add_argument("--json", action="store_true")
    dr_v.set_defaults(func=cmd_drift, drift_cmd="eval")

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

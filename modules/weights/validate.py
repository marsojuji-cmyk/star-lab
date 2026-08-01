"""Validate safetensors files and model packages without requiring full framework loads."""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

from .layout import (
    INDEX_NAME,
    is_pickle_checkpoint,
    is_safetensors_file,
    list_pickle_files,
    package_paths,
)


def _read_safetensors_header(path: Path) -> Dict[str, Any]:
    """
    Read safetensors header (JSON) without loading tensors.
    Format: 8-byte little-endian header length + UTF-8 JSON header.
    """
    with open(path, "rb") as f:
        raw = f.read(8)
        if len(raw) < 8:
            raise ValueError("file too short for safetensors header")
        (hlen,) = struct.unpack("<Q", raw)
        if hlen > 100 * 1024 * 1024:  # 100MB sanity
            raise ValueError(f"implausible header length: {hlen}")
        header_bytes = f.read(hlen)
        if len(header_bytes) < hlen:
            raise ValueError("truncated safetensors header")
    header = json.loads(header_bytes.decode("utf-8"))
    return header


def validate_safetensors_file(path: Path) -> Dict[str, Any]:
    path = Path(path)
    issues: List[str] = []
    tensors: List[Dict[str, Any]] = []
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "not a file", "tensors": []}
    if not is_safetensors_file(path):
        return {
            "ok": False,
            "path": str(path),
            "error": f"not .safetensors (got {path.suffix})",
            "tensors": [],
        }
    try:
        header = _read_safetensors_header(path)
    except Exception as e:
        return {"ok": False, "path": str(path), "error": str(e), "tensors": []}

    meta = header.pop("__metadata__", None) if isinstance(header, dict) else None
    for name, info in header.items():
        if not isinstance(info, dict):
            issues.append(f"tensor {name}: invalid header entry")
            continue
        dtype = info.get("dtype")
        shape = info.get("shape")
        data_offsets = info.get("data_offsets")
        tensors.append(
            {
                "name": name,
                "dtype": dtype,
                "shape": shape,
                "data_offsets": data_offsets,
            }
        )
        if shape is None or dtype is None:
            issues.append(f"tensor {name}: missing dtype/shape")
        if data_offsets is None or len(data_offsets) != 2:
            issues.append(f"tensor {name}: missing data_offsets")

    size = path.stat().st_size
    return {
        "ok": len(issues) == 0,
        "path": str(path),
        "n_tensors": len(tensors),
        "tensors": tensors,
        "metadata": meta,
        "file_bytes": size,
        "issues": issues,
    }


def validate_index(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "error": "index not found", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"ok": False, "error": str(e), "path": str(path)}
    weight_map = data.get("weight_map") or data.get("weightMap") or {}
    if not isinstance(weight_map, dict) or not weight_map:
        return {"ok": False, "error": "missing weight_map", "path": str(path)}
    root = path.parent
    missing = []
    shards = set()
    for tname, shard in weight_map.items():
        sp = root / shard
        shards.add(shard)
        if not sp.is_file():
            missing.append(str(sp))
    return {
        "ok": len(missing) == 0,
        "path": str(path),
        "n_tensors": len(weight_map),
        "n_shards": len(shards),
        "missing_shards": missing,
        "metadata": data.get("metadata"),
    }


def validate_path(path: Path) -> Dict[str, Any]:
    """Validate a single .safetensors file or a package directory."""
    path = Path(path)
    if path.is_file():
        if is_pickle_checkpoint(path):
            return {
                "ok": False,
                "kind": "pickle",
                "path": str(path),
                "error": "pickle/torch checkpoint rejected for production interchange",
                "suggestion": "lab weights convert --input … --output model.safetensors",
            }
        return {"kind": "file", **validate_safetensors_file(path)}

    if path.is_dir():
        return {"kind": "package", **publish_check(path, strict=False)}

    return {"ok": False, "error": f"path not found: {path}"}


def publish_check(package_dir: Path, *, strict: Optional[bool] = None) -> Dict[str, Any]:
    """
    Check a model package for lab publish readiness.
    strict: env GROK_WEIGHTS_STRICT=1 or explicit True → fail on any pickle.
    """
    if strict is None:
        strict = os.environ.get("GROK_WEIGHTS_STRICT", "0") == "1"

    package_dir = Path(package_dir)
    issues: List[str] = []
    warnings: List[str] = []
    paths = package_paths(package_dir)

    if not package_dir.is_dir():
        return {"ok": False, "error": "not a directory", "path": str(package_dir)}

    pickles = list_pickle_files(package_dir)
    if pickles:
        msg = f"pickle/torch checkpoints present: {[str(p) for p in pickles[:5]]}"
        if strict:
            issues.append(msg)
        else:
            warnings.append(msg + " (set GROK_WEIGHTS_STRICT=1 to fail)")

    config = paths.get("config")
    if not config or not Path(config).is_file():
        warnings.append("missing config.json")

    manifest_path = paths.get("manifest")
    manifest_report: Optional[Dict[str, Any]] = None
    if not manifest_path or not Path(manifest_path).is_file():
        msg = "missing manifest.json (lab weights manifest init …)"
        if strict:
            issues.append(msg)
        else:
            warnings.append(msg)
    else:
        from .manifest import load_manifest, validate_manifest

        try:
            man = load_manifest(package_dir)
            manifest_report = validate_manifest(
                man, package_dir=package_dir, check_hash=True
            )
            if not manifest_report.get("ok"):
                for i in manifest_report.get("issues") or []:
                    issues.append(f"manifest: {i}")
        except Exception as e:
            issues.append(f"manifest unreadable: {e}")

    tok_ok = bool(paths.get("tokenizer_dir") or paths.get("tokenizer_json"))
    if not tok_ok:
        warnings.append("no tokenizer/ or tokenizer.json (ok for pure weight packs)")

    weight_ok = False
    weight_reports: List[Dict[str, Any]] = []

    index = paths.get("index")
    if index and Path(index).is_file():
        ir = validate_index(Path(index))
        weight_reports.append(ir)
        if not ir.get("ok"):
            issues.append(f"index invalid: {ir.get('error') or ir.get('missing_shards')}")
        else:
            # validate each shard header lightly
            root = package_dir
            data = json.loads(Path(index).read_text(encoding="utf-8"))
            weight_map = data.get("weight_map") or {}
            for shard in sorted(set(weight_map.values())):
                sr = validate_safetensors_file(root / shard)
                weight_reports.append(sr)
                if not sr.get("ok"):
                    issues.append(f"shard {shard}: {sr.get('error') or sr.get('issues')}")
            weight_ok = ir.get("ok") and all(
                r.get("ok") for r in weight_reports if r.get("path", "").endswith(".safetensors")
            )
    else:
        single = paths.get("single")
        shards = paths.get("shards") or []
        if single and Path(single).is_file():
            sr = validate_safetensors_file(Path(single))
            weight_reports.append(sr)
            weight_ok = bool(sr.get("ok"))
            if not weight_ok:
                issues.append(sr.get("error") or str(sr.get("issues")))
        elif shards:
            for sp in shards:
                sr = validate_safetensors_file(Path(sp))
                weight_reports.append(sr)
                if not sr.get("ok"):
                    issues.append(f"{sp}: {sr.get('error')}")
            weight_ok = all(r.get("ok") for r in weight_reports)
            if len(shards) > 1:
                warnings.append(
                    f"multiple .safetensors without {INDEX_NAME}; add index for sharded layouts"
                )
        else:
            issues.append("no model.safetensors or sharded weights found")

    ok = weight_ok and not issues
    return {
        "ok": ok,
        "path": str(package_dir),
        "weight_ok": weight_ok,
        "issues": issues,
        "warnings": warnings,
        "strict": strict,
        "has_config": bool(config and Path(config).is_file()),
        "has_tokenizer": tok_ok,
        "has_manifest": bool(manifest_path and Path(manifest_path).is_file()),
        "manifest": manifest_report,
        "pickle_files": [str(p) for p in pickles],
        "reports": weight_reports,
    }

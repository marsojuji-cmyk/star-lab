"""
Model package manifest: versioning metadata separate from weight tensors.

Schema versioned independently of model version (schema_version vs version).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "1.0.0"
MANIFEST_NAME = "manifest.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "model_manifest.schema.json"

SEMVER_RE = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)(?:[+-][0-9A-Za-z.-]+)?$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

REQUIRED_FIELDS = [
    "schema_version",
    "model_id",
    "version",
    "arch",
    "framework",
    "weights_uri",
    "weights_format",
    "weights_sha256",
    "created_at",
]

FRAMEWORKS = {"pytorch", "mlx", "jax", "numpy", "other"}
WEIGHT_FORMATS = {"safetensors", "safetensors_sharded"}


def load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def parse_semver(v: str) -> Optional[Tuple[int, int, int]]:
    m = SEMVER_RE.match(v or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_semver(v: str, part: str = "patch") -> str:
    p = parse_semver(v)
    if not p:
        raise ValueError(f"invalid semver: {v}")
    major, minor, patch = p
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError("part must be major|minor|patch")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_weights(package_dir: Path, weights_uri: str) -> str:
    """
    Hash policy:
    - single file: sha256 of that file
    - index.json: sha256 of sorted "shard_path:file_sha256" lines joined
    """
    package_dir = Path(package_dir)
    target = package_dir / weights_uri
    if not target.is_file():
        raise FileNotFoundError(f"weights_uri not found: {target}")
    if target.name.endswith(".index.json") or target.suffix == ".json" and "index" in target.name:
        data = json.loads(target.read_text(encoding="utf-8"))
        weight_map = data.get("weight_map") or {}
        shards = sorted(set(weight_map.values()))
        lines = []
        for shard in shards:
            sp = package_dir / shard
            if not sp.is_file():
                raise FileNotFoundError(f"shard missing: {sp}")
            lines.append(f"{shard}:{sha256_file(sp)}")
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return sha256_file(target)


def git_commit(repo: Optional[Path] = None) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo) if repo else None,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_manifest(
    *,
    model_id: str,
    version: str = "0.1.0",
    arch: str = "unknown",
    framework: str = "other",
    weights_uri: str = "model.safetensors",
    weights_format: str = "safetensors",
    weights_sha256: str = "0" * 64,
    **extra: Any,
) -> Dict[str, Any]:
    m: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model_id": model_id,
        "version": version,
        "parent_version": extra.pop("parent_version", None),
        "arch": arch,
        "framework": framework,
        "framework_version": extra.pop("framework_version", None),
        "weights_uri": weights_uri,
        "weights_format": weights_format,
        "weights_sha256": weights_sha256,
        "tokenizer_id": extra.pop("tokenizer_id", None),
        "tokenizer_version": extra.pop("tokenizer_version", None),
        "tokenizer_uri": extra.pop("tokenizer_uri", None),
        "data_version": extra.pop("data_version", None),
        "code_commit": extra.pop("code_commit", None),
        "env_hash": extra.pop("env_hash", None),
        "body_id": extra.pop("body_id", None),
        "metrics": extra.pop("metrics", {}),
        "license": extra.pop("license", None),
        "compatibility": extra.pop(
            "compatibility",
            {
                "min_lab_version": None,
                "runtimes": [],
                "quantization": "none",
                "target_device": None,
                "memory_mb_min": None,
                "notes": None,
            },
        ),
        "created_at": extra.pop("created_at", now_iso()),
        "notes": extra.pop("notes", None),
    }
    # drop Nones optional? keep for schema nullables
    return m


def _validate_builtin(manifest: Dict[str, Any]) -> List[str]:
    """Lightweight validation without jsonschema dependency."""
    issues: List[str] = []
    for f in REQUIRED_FIELDS:
        if f not in manifest or manifest[f] in ("", None):
            # weights_sha256 of zeros allowed only before seal
            if f == "weights_sha256" and manifest.get(f) == "0" * 64:
                continue
            if f not in manifest:
                issues.append(f"missing required field: {f}")
                continue
            if manifest[f] in ("", None) and f != "weights_sha256":
                issues.append(f"empty required field: {f}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            f"schema_version must be {SCHEMA_VERSION}, got {manifest.get('schema_version')}"
        )

    v = manifest.get("version")
    if v and not parse_semver(str(v)):
        issues.append(f"invalid model version semver: {v}")
    pv = manifest.get("parent_version")
    if pv is not None and pv != "" and not parse_semver(str(pv)):
        issues.append(f"invalid parent_version semver: {pv}")

    fw = manifest.get("framework")
    if fw is not None and fw not in FRAMEWORKS:
        issues.append(f"framework must be one of {sorted(FRAMEWORKS)}")

    wf = manifest.get("weights_format")
    if wf is not None and wf not in WEIGHT_FORMATS:
        issues.append(f"weights_format must be one of {sorted(WEIGHT_FORMATS)}")

    sha = manifest.get("weights_sha256")
    if sha is not None and not SHA256_RE.match(str(sha)):
        issues.append("weights_sha256 must be 64 lowercase hex chars")

    # major bump signal: if parent major differs from version major, ok; no check required
    return issues


def validate_manifest(
    manifest: Dict[str, Any],
    *,
    package_dir: Optional[Path] = None,
    check_hash: bool = True,
    use_jsonschema: bool = True,
) -> Dict[str, Any]:
    """
    Validate manifest against schema + optional package hash verification.
    """
    issues = _validate_builtin(manifest)
    schema_ok = None

    if use_jsonschema:
        try:
            import jsonschema  # type: ignore

            schema = load_schema()
            # allow draft without format checker for created_at flexibility
            validator = jsonschema.Draft202012Validator(schema)
            for err in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path)):
                issues.append(f"schema: {err.message} @ {list(err.path)}")
            schema_ok = True
        except ImportError:
            schema_ok = False  # builtin only
        except Exception as e:
            issues.append(f"schema validation error: {e}")
            schema_ok = False

    hash_ok = None
    if package_dir and check_hash and manifest.get("weights_uri") and manifest.get("weights_sha256"):
        try:
            actual = sha256_weights(Path(package_dir), str(manifest["weights_uri"]))
            expected = str(manifest["weights_sha256"])
            if expected == "0" * 64:
                issues.append("weights_sha256 is placeholder; run lab weights manifest seal")
                hash_ok = False
            elif actual != expected:
                issues.append(f"weights_sha256 mismatch: manifest={expected[:12]}… actual={actual[:12]}…")
                hash_ok = False
            else:
                hash_ok = True
        except FileNotFoundError as e:
            issues.append(str(e))
            hash_ok = False

    # tokenizer pair consistency: if one of id/version set, warn only via issues optional
    tid, tver = manifest.get("tokenizer_id"), manifest.get("tokenizer_version")
    if (tid and not tver) or (tver and not tid):
        issues.append("tokenizer_id and tokenizer_version should be set together")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "schema_engine": "jsonschema" if schema_ok else "builtin",
        "hash_ok": hash_ok,
        "schema_version": SCHEMA_VERSION,
        "model_id": manifest.get("model_id"),
        "version": manifest.get("version"),
    }


def load_manifest(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(package_dir: Path, manifest: Dict[str, Any]) -> Path:
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    path = package_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def init_manifest(
    package_dir: Path,
    *,
    model_id: str,
    version: str = "0.1.0",
    arch: str = "unknown",
    framework: str = "other",
    parent_version: Optional[str] = None,
    body_id: Optional[str] = None,
    seal: bool = False,
) -> Dict[str, Any]:
    """Create manifest.json; optionally hash existing weights."""
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    weights_uri = "model.safetensors"
    weights_format = "safetensors"
    if (package_dir / "model.safetensors.index.json").is_file():
        weights_uri = "model.safetensors.index.json"
        weights_format = "safetensors_sharded"
    elif not (package_dir / "model.safetensors").is_file():
        # pick first .safetensors if any
        shards = sorted(package_dir.glob("*.safetensors"))
        if shards:
            weights_uri = shards[0].name

    sha = "0" * 64
    if seal or (package_dir / weights_uri).is_file() or weights_format == "safetensors_sharded":
        try:
            if seal:
                sha = sha256_weights(package_dir, weights_uri)
        except FileNotFoundError:
            pass

    commit = git_commit()
    m = default_manifest(
        model_id=model_id,
        version=version,
        arch=arch,
        framework=framework,
        weights_uri=weights_uri,
        weights_format=weights_format,
        weights_sha256=sha,
        parent_version=parent_version,
        body_id=body_id,
        code_commit=commit,
    )
    if seal and sha == "0" * 64:
        # try again if weights exist
        try:
            m["weights_sha256"] = sha256_weights(package_dir, weights_uri)
        except FileNotFoundError:
            pass
    save_manifest(package_dir, m)
    return m


def seal_manifest(package_dir: Path) -> Dict[str, Any]:
    """Recompute weights_sha256 and write back."""
    package_dir = Path(package_dir)
    m = load_manifest(package_dir)
    uri = m.get("weights_uri") or "model.safetensors"
    m["weights_sha256"] = sha256_weights(package_dir, uri)
    if not m.get("code_commit"):
        m["code_commit"] = git_commit()
    save_manifest(package_dir, m)
    return m


def version_bump_note(part: str) -> str:
    return {
        "major": "breaking schema or architecture change",
        "minor": "backward-compatible capability/weight additions",
        "patch": "metadata-only or non-breaking tweaks",
    }.get(part, "")

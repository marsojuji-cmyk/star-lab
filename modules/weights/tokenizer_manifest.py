"""
Tokenizer package versioning: tokenizer-major / model tracks compatibility.

Freeze by default. Vocab/merge/special changes → new major artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .manifest import (
    SEMVER_RE,
    SHA256_RE,
    bump_semver,
    git_commit,
    parse_semver,
    sha256_file,
    version_bump_note,
)

SCHEMA_VERSION = "1.0.0"
TOKENIZER_MANIFEST_NAME = "tokenizer_manifest.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "tokenizer_manifest.schema.json"

MODES = {"frozen", "append_only", "dynamic"}

# Files hashed into tokenizer_hash when present (order sorted by name)
CONTENT_CANDIDATES = (
    "tokenizer.json",
    "vocab.json",
    "vocab.txt",
    "merges.txt",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "added_tokens.json",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def discover_content_files(package_dir: Path) -> List[str]:
    package_dir = Path(package_dir)
    found = []
    for name in CONTENT_CANDIDATES:
        if (package_dir / name).is_file():
            found.append(name)
    # also hash provenance if present
    if (package_dir / "provenance.jsonl").is_file():
        found.append("provenance.jsonl")
    return found


def hash_tokenizer_content(package_dir: Path, content_files: Optional[Sequence[str]] = None) -> str:
    """SHA-256 of sorted lines `relpath:sha256(file)`."""
    package_dir = Path(package_dir)
    files = list(content_files) if content_files is not None else discover_content_files(package_dir)
    if not files:
        # empty package still gets a defined hash of empty set
        return hashlib.sha256(b"").hexdigest()
    lines = []
    for rel in sorted(files):
        p = package_dir / rel
        if not p.is_file():
            raise FileNotFoundError(f"tokenizer content missing: {p}")
        lines.append(f"{rel}:{sha256_file(p)}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def merge_file_hash(package_dir: Path) -> Optional[str]:
    p = Path(package_dir) / "merges.txt"
    if p.is_file():
        return sha256_file(p)
    return None


def guess_vocab_size(package_dir: Path) -> int:
    package_dir = Path(package_dir)
    tj = package_dir / "tokenizer.json"
    if tj.is_file():
        try:
            data = json.loads(tj.read_text(encoding="utf-8"))
            model = data.get("model") or {}
            vocab = model.get("vocab")
            if isinstance(vocab, dict):
                return len(vocab)
            added = data.get("added_tokens") or []
            if isinstance(added, list) and vocab is None:
                return len(added)
        except (json.JSONDecodeError, OSError):
            pass
    vj = package_dir / "vocab.json"
    if vj.is_file():
        try:
            return len(json.loads(vj.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    return 0


def load_special_tokens(package_dir: Path) -> Any:
    package_dir = Path(package_dir)
    stm = package_dir / "special_tokens_map.json"
    if stm.is_file():
        try:
            return json.loads(stm.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    tj = package_dir / "tokenizer.json"
    if tj.is_file():
        try:
            data = json.loads(tj.read_text(encoding="utf-8"))
            return data.get("added_tokens") or []
        except (json.JSONDecodeError, OSError):
            pass
    return []


def default_tokenizer_manifest(
    *,
    tokenizer_id: str,
    version: str = "1.0.0",
    tokenizer_mode: str = "frozen",
    **extra: Any,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "tokenizer_id": tokenizer_id,
        "version": version,
        "parent_version": extra.pop("parent_version", None),
        "tokenizer_hash": extra.pop("tokenizer_hash", "0" * 64),
        "base_vocab_size": int(extra.pop("base_vocab_size", 0)),
        "special_tokens": extra.pop("special_tokens", []),
        "merge_file_hash": extra.pop("merge_file_hash", None),
        "vocab_file_hash": extra.pop("vocab_file_hash", None),
        "added_tokens": list(extra.pop("added_tokens", [])),
        "added_merges": list(extra.pop("added_merges", [])),
        "tokenizer_mode": tokenizer_mode,
        "compatibility_with_model": list(extra.pop("compatibility_with_model", [])),
        "content_files": list(extra.pop("content_files", [])),
        "code_commit": extra.pop("code_commit", None),
        "notes": extra.pop("notes", None),
        "created_at": extra.pop("created_at", now_iso()),
    }


def _validate_builtin(m: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for f in (
        "schema_version",
        "tokenizer_id",
        "version",
        "tokenizer_hash",
        "base_vocab_size",
        "tokenizer_mode",
        "created_at",
    ):
        if f not in m or m[f] in ("", None):
            issues.append(f"missing required field: {f}")
    if m.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION}")
    if m.get("version") and not parse_semver(str(m["version"])):
        issues.append(f"invalid version semver: {m.get('version')}")
    pv = m.get("parent_version")
    if pv not in (None, "") and not parse_semver(str(pv)):
        issues.append(f"invalid parent_version: {pv}")
    th = m.get("tokenizer_hash")
    if th is not None and not SHA256_RE.match(str(th)):
        issues.append("tokenizer_hash must be 64 lowercase hex chars")
    mode = m.get("tokenizer_mode")
    if mode is not None and mode not in MODES:
        issues.append(f"tokenizer_mode must be one of {sorted(MODES)}")
    if mode == "dynamic":
        issues.append(
            "tokenizer_mode=dynamic is discouraged; prefer frozen or append_only"
        )
    if mode == "frozen" and (m.get("added_tokens") or m.get("added_merges")):
        # allow non-empty if they are snapshot of history, but warn as issue for strict freeze purity
        pass
    if mode == "append_only" and not (m.get("added_tokens") or m.get("added_merges") or m.get("parent_version")):
        issues.append(
            "append_only should record added_tokens/added_merges and/or parent_version for provenance"
        )
    return issues


def validate_tokenizer_manifest(
    m: Dict[str, Any],
    *,
    package_dir: Optional[Path] = None,
    check_hash: bool = True,
    allow_dynamic: bool = False,
) -> Dict[str, Any]:
    issues = _validate_builtin(m)
    if m.get("tokenizer_mode") == "dynamic" and allow_dynamic:
        issues = [i for i in issues if "discouraged" not in i]

    hash_ok = None
    if package_dir and check_hash and m.get("tokenizer_hash"):
        try:
            files = m.get("content_files") or discover_content_files(Path(package_dir))
            actual = hash_tokenizer_content(Path(package_dir), files)
            expected = str(m["tokenizer_hash"])
            if expected == "0" * 64:
                issues.append("tokenizer_hash is placeholder; run lab weights tokenizer seal")
                hash_ok = False
            elif actual != expected:
                issues.append(
                    f"tokenizer_hash mismatch: manifest={expected[:12]}… actual={actual[:12]}…"
                )
                hash_ok = False
            else:
                hash_ok = True
        except FileNotFoundError as e:
            issues.append(str(e))
            hash_ok = False

    # dynamic without allow is soft warning already in issues
    ok = not any(
        "mismatch" in i or "missing required" in i or "must be" in i or "placeholder" in i
        or "invalid" in i or "append_only should" in i
        for i in issues
    )
    # still fail ok if only "discouraged" and allow_dynamic false — treat discouraged as warning for validate unless strict
    hard = [i for i in issues if "discouraged" not in i]
    return {
        "ok": len(hard) == 0,
        "issues": issues,
        "hash_ok": hash_ok,
        "tokenizer_id": m.get("tokenizer_id"),
        "version": m.get("version"),
        "tokenizer_mode": m.get("tokenizer_mode"),
    }


def load_tokenizer_manifest(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / TOKENIZER_MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def save_tokenizer_manifest(package_dir: Path, m: Dict[str, Any]) -> Path:
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    path = package_dir / TOKENIZER_MANIFEST_NAME
    path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
    return path


def init_tokenizer_manifest(
    package_dir: Path,
    *,
    tokenizer_id: str,
    version: str = "1.0.0",
    tokenizer_mode: str = "frozen",
    parent_version: Optional[str] = None,
    seal: bool = False,
    base_vocab_size: Optional[int] = None,
) -> Dict[str, Any]:
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    content_files = discover_content_files(package_dir)
    th = "0" * 64
    if seal:
        th = hash_tokenizer_content(package_dir, content_files)
    m = default_tokenizer_manifest(
        tokenizer_id=tokenizer_id,
        version=version,
        tokenizer_mode=tokenizer_mode,
        parent_version=parent_version,
        tokenizer_hash=th,
        base_vocab_size=base_vocab_size if base_vocab_size is not None else guess_vocab_size(package_dir),
        special_tokens=load_special_tokens(package_dir),
        merge_file_hash=merge_file_hash(package_dir),
        content_files=content_files,
        code_commit=git_commit(),
    )
    if seal and m["tokenizer_hash"] == "0" * 64 and content_files:
        m["tokenizer_hash"] = hash_tokenizer_content(package_dir, content_files)
    save_tokenizer_manifest(package_dir, m)
    return m


def seal_tokenizer_manifest(package_dir: Path) -> Dict[str, Any]:
    package_dir = Path(package_dir)
    m = load_tokenizer_manifest(package_dir)
    files = discover_content_files(package_dir)
    m["content_files"] = files
    m["tokenizer_hash"] = hash_tokenizer_content(package_dir, files)
    m["merge_file_hash"] = merge_file_hash(package_dir)
    if m.get("base_vocab_size") in (None, 0):
        m["base_vocab_size"] = guess_vocab_size(package_dir)
    if not m.get("special_tokens"):
        m["special_tokens"] = load_special_tokens(package_dir)
    if not m.get("code_commit"):
        m["code_commit"] = git_commit()
    save_tokenizer_manifest(package_dir, m)
    return m


def freeze_tokenizer(package_dir: Path) -> Dict[str, Any]:
    """Set mode frozen; forbids further in-place vocab edits without new major."""
    m = load_tokenizer_manifest(package_dir)
    m["tokenizer_mode"] = "frozen"
    m["notes"] = ((m.get("notes") or "") + " | frozen").strip(" |")
    save_tokenizer_manifest(package_dir, m)
    return m


def bump_tokenizer(
    package_dir: Path,
    part: str,
    *,
    force: bool = False,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Semver bump. Breaking vocab/merge/special changes must use major
    (CLI warns if part != major for content changes — force allows patch/minor).
    """
    package_dir = Path(package_dir)
    m = load_tokenizer_manifest(package_dir)
    old = m["version"]
    if part != "major" and not force:
        # soft policy: re-seal and if hash would change vs stored, require major
        try:
            files = discover_content_files(package_dir)
            actual = hash_tokenizer_content(package_dir, files)
            if m.get("tokenizer_hash") and m["tokenizer_hash"] != "0" * 64 and actual != m["tokenizer_hash"]:
                raise ValueError(
                    "tokenizer content changed vs sealed hash — use --part major "
                    "(or --force for append_only minor with provenance)"
                )
        except FileNotFoundError:
            pass
    if part == "minor" and m.get("tokenizer_mode") == "frozen" and not force:
        raise ValueError(
            "frozen tokenizer: minor bump only with --force after append_only mode + provenance"
        )
    m["parent_version"] = old
    m["version"] = bump_semver(old, part)
    note = version_bump_note(part)
    m["notes"] = notes or f"bump {part}: {note}"
    # re-seal after bump
    save_tokenizer_manifest(package_dir, m)
    return seal_tokenizer_manifest(package_dir)


def assert_tokenizer_compatible(
    model_manifest: Dict[str, Any],
    tokenizer_manifest: Dict[str, Any],
    *,
    allow_dynamic: bool = False,
) -> Dict[str, Any]:
    """
    Loader gate: call before load_weights.
    Returns {ok, issues}.
    """
    issues: List[str] = []
    mid = model_manifest.get("tokenizer_id")
    mver = model_manifest.get("tokenizer_version")
    mhash = model_manifest.get("tokenizer_hash")
    tid = tokenizer_manifest.get("tokenizer_id")
    tver = tokenizer_manifest.get("tokenizer_version") or tokenizer_manifest.get("version")
    thash = tokenizer_manifest.get("tokenizer_hash")

    if mid and tid and mid != tid:
        issues.append(f"tokenizer_id mismatch: model={mid} package={tid}")
    if mver and tver and mver != tver:
        issues.append(f"tokenizer_version mismatch: model={mver} package={tver}")
    if mhash and thash and mhash != thash:
        issues.append("tokenizer_hash mismatch between model manifest and tokenizer package")
    if mid and not mhash:
        issues.append("model manifest missing tokenizer_hash (required when tokenizer_id set)")
    if mid and not mver:
        issues.append("model manifest missing tokenizer_version")

    mode = tokenizer_manifest.get("tokenizer_mode")
    if mode == "dynamic" and not allow_dynamic:
        issues.append("refusing dynamic tokenizer without allow_dynamic=True")

    remap = model_manifest.get("embedding_remap") or "none"
    if remap == "required_unmet":
        issues.append(
            "embedding_remap=required_unmet: retrain or retrofit embeddings before load"
        )

    # if tokenizer major > what model was built with — can't know without parent; hash is source of truth
    return {"ok": len(issues) == 0, "issues": issues}


def bind_tokenizer_to_model_manifest(
    model_manifest: Dict[str, Any],
    tokenizer_manifest: Dict[str, Any],
    *,
    tokenizer_uri: str = "tokenizer",
    embedding_remap: str = "none",
) -> Dict[str, Any]:
    """Copy exact tokenizer revision fields onto model manifest."""
    model_manifest = dict(model_manifest)
    model_manifest["tokenizer_id"] = tokenizer_manifest.get("tokenizer_id")
    model_manifest["tokenizer_version"] = tokenizer_manifest.get("version")
    model_manifest["tokenizer_hash"] = tokenizer_manifest.get("tokenizer_hash")
    model_manifest["tokenizer_uri"] = tokenizer_uri
    model_manifest["tokenizer_mode"] = tokenizer_manifest.get("tokenizer_mode")
    model_manifest["embedding_remap"] = embedding_remap
    return model_manifest

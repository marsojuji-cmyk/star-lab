#!/usr/bin/env python3
# Grok Star Lab — Showroom secrets gate (publish refuse)
"""Scan text and file contents for private-key / credential markers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# Patterns that must never land in curated showroom entries.
SECRET_PATTERNS: Sequence[Tuple[str, re.Pattern]] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "private_key_pem",
        re.compile(
            r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
        ),
    ),
    ("api_key_assign", re.compile(r"(?i)api[_-]?key\s*=")),
    ("api_key_env", re.compile(r"(?i)\bAPI_KEY\s*=")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
)

# Path globs that are refuse-to-publish (by name).
SECRET_PATH_MARKERS = (
    ".env",
    ".pem",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "secret",
)


def scan_text(text: str, *, label: str = "body") -> List[str]:
    """Return human-readable hit messages for secrets found in text."""
    hits: List[str] = []
    if not text:
        return hits
    for name, pat in SECRET_PATTERNS:
        if pat.search(text):
            hits.append("%s: matched %s" % (label, name))
    return hits


def path_looks_secret(path: str) -> Optional[str]:
    """Return reason if path basename/suffix suggests secrets material."""
    p = path.replace("\\", "/").lower()
    base = p.rsplit("/", 1)[-1]
    if base == ".env" or base.startswith(".env."):
        return "path looks like .env: %s" % path
    for marker in SECRET_PATH_MARKERS:
        if marker in base:
            return "path name contains %r: %s" % (marker, path)
    return None


def scan_paths(
    paths: Iterable[str],
    *,
    max_bytes: int = 256_000,
) -> List[str]:
    """
    Scan attached paths for secret-like names and small-file content.
    Missing paths are skipped (not a secrets hit).
    """
    hits: List[str] = []
    for raw in paths or []:
        reason = path_looks_secret(str(raw))
        if reason:
            hits.append(reason)
            continue
        try:
            p = Path(str(raw)).expanduser()
            if not p.is_file():
                continue
            # Skip large / binary-ish files by size only; read as text best-effort.
            if p.stat().st_size > max_bytes:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits.extend(scan_text(text, label="file:%s" % p.name))
        except OSError:
            continue
    return hits


def scan_payload(
    *,
    title: str = "",
    summary: str = "",
    body: str = "",
    paths: Optional[Iterable[str]] = None,
    proof_commands: Optional[Iterable[str]] = None,
    extra_text: str = "",
) -> List[str]:
    """Full publish secrets gate. Empty list = clean."""
    hits: List[str] = []
    blob_parts = [title or "", summary or "", body or "", extra_text or ""]
    if proof_commands:
        blob_parts.extend(str(c) for c in proof_commands)
    hits.extend(scan_text("\n".join(blob_parts), label="payload"))
    hits.extend(scan_paths(paths or []))
    # Dedupe while preserving order
    seen = set()
    out: List[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out

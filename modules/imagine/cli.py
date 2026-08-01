#!/usr/bin/env python3
# Grok Star Lab — Imagine Atelier CLI (PR10: offline verify only)
"""lab imagine verify — local image checks (size, MIME, dimensions). No generation."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import struct
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# lib/ on sys.path when run as modules/imagine/cli.py
_REPO = Path(__file__).resolve().parent.parent.parent
_LIB = _REPO / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lab_paths import ensure_lab_dirs, lab_data_root, repo_root  # noqa: E402

# Paths that must never be read for verify (credential / secret globs).
_REFUSE_NAME_PATTERNS = (
    re.compile(r"^\.env$", re.I),
    re.compile(r"^\.env\..+", re.I),
    re.compile(r".*\.pem$", re.I),
    re.compile(r".*\.key$", re.I),
    re.compile(r".*\.p12$", re.I),
    re.compile(r".*\.pfx$", re.I),
    re.compile(r"^id_rsa$", re.I),
    re.compile(r"^id_ed25519$", re.I),
    re.compile(r".*credentials.*", re.I),
    re.compile(r".*secret.*", re.I),
)


def _root() -> Path:
    env = os.environ.get("GROK_LAB_REPO")
    if env:
        return Path(env).resolve()
    return repo_root()


def runs_dir() -> Path:
    """~/.grok/lab/imagine/runs (ensured)."""
    ensure_lab_dirs()
    path = lab_data_root() / "imagine" / "runs"
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _is_refused_path(path: Path) -> Optional[str]:
    """Return reason if path looks like credentials/secrets; else None."""
    parts = path.parts
    for part in parts:
        for pat in _REFUSE_NAME_PATTERNS:
            if pat.match(part):
                return f"refused path component matching credential pattern: {part}"
    name = path.name
    for pat in _REFUSE_NAME_PATTERNS:
        if pat.match(name):
            return f"refused filename matching credential pattern: {name}"
    return None


def _mime_from_magic(data: bytes) -> Optional[str]:
    if not data:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Parse SOF markers for width/height. Returns (width, height)."""
    i = 2  # skip SOI
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            return None
        # skip fill bytes
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            return None
        marker = data[i]
        i += 1
        # standalone markers
        if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
            continue
        if i + 1 >= n:
            return None
        seg_len = struct.unpack(">H", data[i : i + 2])[0]
        if seg_len < 2:
            return None
        # SOF0–SOF3, SOF5–SOF7, SOF9–SOF11, SOF13–SOF15 (not DHT/DAC)
        if marker in (
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        ):
            if i + 7 >= n:
                return None
            height, width = struct.unpack(">HH", data[i + 3 : i + 7])
            if width > 0 and height > 0:
                return (width, height)
            return None
        i += seg_len
    return None


def _png_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    # IHDR: length(4) type(4) then width/height
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if width > 0 and height > 0:
        return (width, height)
    return None


def _gif_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    if width > 0 and height > 0:
        return (width, height)
    return None


def _dimensions_from_bytes(data: bytes, mime: Optional[str]) -> Optional[Tuple[int, int]]:
    mime = mime or _mime_from_magic(data) or ""
    if mime == "image/jpeg" or data[:3] == b"\xff\xd8\xff":
        return _jpeg_dimensions(data)
    if mime == "image/png" or data[:8] == b"\x89PNG\r\n\x1a\n":
        return _png_dimensions(data)
    if mime == "image/gif" or data[:6] in (b"GIF87a", b"GIF89a"):
        return _gif_dimensions(data)
    return None


def _sips_available() -> bool:
    from shutil import which

    return which("sips") is not None


def _dimensions_via_sips(path: Path) -> Optional[Tuple[int, int]]:
    """Optional macOS sips probe. Returns (width, height) or None."""
    if not _sips_available():
        return None
    try:
        proc = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    width = height = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "pixelWidth:" in line:
            try:
                width = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif "pixelHeight:" in line:
            try:
                height = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    if width and height and width > 0 and height > 0:
        return (width, height)
    return None


def verify_image(path: Path) -> Dict[str, Any]:
    """
    Offline verify one image path.

    Checks: exists, non-empty, not credential path, content MIME (magic bytes
    only — extension guess is never a pass), filesize, dimensions (pure parse;
    sips optional cross-check).
    """
    result: Dict[str, Any] = {
        "path": str(path),
        "ok": False,
        "size_bytes": None,
        "mime": None,
        "mime_guess": None,
        "width": None,
        "height": None,
        "dimensions_source": None,
        "checks": {},
        "errors": [],
        "warnings": [],
    }
    checks: Dict[str, str] = {}

    refuse = _is_refused_path(path)
    if refuse:
        checks["credentials"] = "fail"
        result["errors"].append(refuse)
        result["checks"] = checks
        return result
    checks["credentials"] = "ok"

    if not path.exists():
        checks["exists"] = "fail"
        result["errors"].append(f"path does not exist: {path}")
        result["checks"] = checks
        return result
    checks["exists"] = "ok"

    if not path.is_file():
        checks["is_file"] = "fail"
        result["errors"].append(f"not a regular file: {path}")
        result["checks"] = checks
        return result
    checks["is_file"] = "ok"

    try:
        size = path.stat().st_size
    except OSError as exc:
        checks["readable"] = "fail"
        result["errors"].append(f"stat failed: {exc}")
        result["checks"] = checks
        return result

    result["size_bytes"] = size
    if size <= 0:
        checks["non_empty"] = "fail"
        result["errors"].append("file is empty (0 bytes)")
        result["checks"] = checks
        return result
    checks["non_empty"] = "ok"
    checks["filesize"] = "ok"

    try:
        # Read enough for magic + common headers (JPEG SOF can be deeper)
        with path.open("rb") as fh:
            head = fh.read(65536)
            if size > 65536 and len(head) == 65536:
                # JPEG SOF may sit later; read full file if small enough
                if size <= 8 * 1024 * 1024:
                    fh.seek(0)
                    head = fh.read()
    except OSError as exc:
        checks["readable"] = "fail"
        result["errors"].append(f"read failed: {exc}")
        result["checks"] = checks
        return result
    checks["readable"] = "ok"

    # Content MIME only: never promote extension guess to a pass (Issue 1).
    magic_mime = _mime_from_magic(head)
    guess_mime, _ = mimetypes.guess_type(str(path))
    result["mime_guess"] = guess_mime
    result["mime"] = magic_mime

    if not magic_mime or not magic_mime.startswith("image/"):
        checks["mime"] = "fail"
        detail = f"magic={magic_mime!r}"
        if guess_mime:
            detail += f", extension_guess={guess_mime!r} (ignored for pass)"
        result["errors"].append(
            f"not a recognized image by content ({detail}); "
            "expected image/jpeg, image/png, …"
        )
        result["checks"] = checks
        return result
    checks["mime"] = "ok"
    if guess_mime and guess_mime != magic_mime:
        result["warnings"].append(
            f"extension guess {guess_mime!r} differs from content MIME {magic_mime!r}"
        )

    mime = magic_mime
    dims = _dimensions_from_bytes(head, mime)
    dim_src = "parser" if dims else None
    sips_present = _sips_available()
    sips_dims = _dimensions_via_sips(path) if sips_present else None
    if sips_dims:
        if dims and dims != sips_dims:
            result["warnings"].append(
                f"dimension mismatch: parser={dims[0]}x{dims[1]} "
                f"sips={sips_dims[0]}x{sips_dims[1]} (using sips)"
            )
            dims = sips_dims
            dim_src = "sips"
        elif not dims:
            dims = sips_dims
            dim_src = "sips"
    elif not dims:
        if sips_present:
            result["warnings"].append(
                "could not determine dimensions (parser failed; sips returned no size)"
            )
        else:
            result["warnings"].append(
                "could not determine dimensions (parser failed; sips not on PATH)"
            )

    if dims:
        result["width"], result["height"] = dims
        result["dimensions_source"] = dim_src
        checks["dimensions"] = "ok"
    else:
        # Missing dimensions is a hard verify failure (status matches exit/errors).
        checks["dimensions"] = "fail"
        result["errors"].append("unable to read image dimensions")

    result["checks"] = checks
    result["ok"] = len(result["errors"]) == 0
    return result


def _write_run_record(payload: Dict[str, Any]) -> Path:
    """Write verification JSON under ~/.grok/lab/imagine/runs/."""
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    stem = Path(payload.get("path") or "image").stem
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem)[:40] or "image"
    run_id = f"{ts}-{stem}-{short}"
    record = {
        "run_id": run_id,
        "created_at": created,
        "command": "verify",
        **payload,
    }
    out = runs_dir() / f"{run_id}.json"
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    return out


def cmd_verify(args: argparse.Namespace) -> int:
    if args.path:
        path = Path(args.path).expanduser()
        if not path.is_absolute():
            # Prefer cwd-relative; fall back to repo-relative for assets/hero.jpg
            cwd_candidate = (Path.cwd() / path).resolve()
            repo_candidate = (_root() / path).resolve()
            if cwd_candidate.is_file():
                path = cwd_candidate
            elif repo_candidate.is_file():
                path = repo_candidate
            else:
                path = cwd_candidate
        else:
            path = path.resolve()
    else:
        # Default: monorepo hero asset (PR10 proof target)
        path = (_root() / "assets" / "hero.jpg").resolve()

    result = verify_image(path)
    run_path = _write_run_record(result)
    # Expose record path for tooling without polluting --json body.
    result_with_record = dict(result)
    result_with_record["record"] = str(run_path)

    if args.json:
        # Pure machine output on stdout (human lines on stderr when --json).
        for w in result.get("warnings") or []:
            print(f"warn: {w}", file=sys.stderr)
        for e in result.get("errors") or []:
            print(f"error: {e}", file=sys.stderr)
        print(json.dumps(result_with_record, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    # Human-readable summary
    status = "ok" if result["ok"] else "FAIL"
    size = result.get("size_bytes")
    size_s = f"{size} bytes" if size is not None else "—"
    dims = "—"
    if result.get("width") and result.get("height"):
        dims = f"{result['width']}x{result['height']}"
        if result.get("dimensions_source"):
            dims += f" ({result['dimensions_source']})"
    mime = result.get("mime") or "—"

    print(f"imagine verify: {status}")
    print(f"  path:       {result['path']}")
    print(f"  size:       {size_s}")
    print(f"  mime:       {mime}")
    print(f"  dimensions: {dims}")
    print(f"  record:     {run_path}")

    for w in result.get("warnings") or []:
        print(f"  warn: {w}", file=sys.stderr)
    for e in result.get("errors") or []:
        print(f"  error: {e}", file=sys.stderr)

    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lab imagine",
        description=(
            "Imagine Atelier — offline image verification "
            "(generation is optional online / not in this CLI)."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser(
        "verify",
        help="verify image file (non-empty, MIME, size, dimensions)",
    )
    sp.add_argument(
        "path",
        nargs="?",
        default=None,
        help="image path (default: assets/hero.jpg in lab repo)",
    )
    sp.add_argument(
        "--json",
        action="store_true",
        help="also print machine-readable result JSON to stdout",
    )
    sp.set_defaults(func=cmd_verify)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

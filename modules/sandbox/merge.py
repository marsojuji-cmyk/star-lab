# Python 3.9+ — missing-key-only merge of lab sandbox profiles into sandbox.toml
"""
Parse a small TOML subset used by Grok sandbox profiles and merge fragment
profiles into an existing sandbox.toml without overwriting user keys.

Supported value types: string, bool, array-of-strings.
Tables: [profiles.<name>] only (other tables preserved as raw text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Canonical lab profile section names (without "profiles." prefix).
LAB_PROFILE_NAMES: Tuple[str, ...] = (
    "lab-workspace",
    "lab-readonly-review",
    "lab-untrusted",
)

_HEADER_RE = re.compile(r"^\[([^\]]+)\]\s*(?:#.*)?$")
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")


def _strip_comment(line: str) -> str:
    """Strip unquoted # comments (profiles use simple values only)."""
    in_str = False
    quote = ""
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_str:
            escaped = True
            continue
        if ch in ('"', "'") and not in_str:
            in_str = True
            quote = ch
            continue
        if in_str and ch == quote:
            in_str = False
            quote = ""
            continue
        if ch == "#" and not in_str:
            return line[:i].rstrip()
    return line.rstrip()


def _parse_string(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        inner = token[1:-1]
        # Minimal escapes
        return (
            inner.replace("\\\\", "\\")
            .replace('\\"', '"')
            .replace("\\'", "'")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )
    # bare string (not standard TOML, but tolerate identifiers)
    return token


def _parse_value(raw: str) -> Any:
    raw = _strip_comment(raw).strip()
    if not raw:
        raise ValueError("empty value")
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if raw.startswith("["):
        # array of strings (possibly multi-line collapsed by caller)
        if not raw.endswith("]"):
            raise ValueError("unclosed array: %s" % raw)
        body = raw[1:-1].strip()
        if not body:
            return []
        items: List[str] = []
        buf = ""
        in_str = False
        quote = ""
        escaped = False
        for ch in body:
            if escaped:
                buf += ch
                escaped = False
                continue
            if ch == "\\" and in_str:
                buf += ch
                escaped = True
                continue
            if ch in ('"', "'") and not in_str:
                in_str = True
                quote = ch
                buf += ch
                continue
            if in_str and ch == quote:
                in_str = False
                quote = ""
                buf += ch
                continue
            if ch == "," and not in_str:
                part = buf.strip()
                if part:
                    items.append(_parse_string(part))
                buf = ""
                continue
            buf += ch
        part = buf.strip()
        if part:
            items.append(_parse_string(part))
        return items
    return _parse_string(raw)


def _format_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, list):
        parts = []
        for item in val:
            s = str(item).replace("\\", "\\\\").replace('"', '\\"')
            parts.append('"%s"' % s)
        return "[" + ", ".join(parts) + "]"
    s = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % s


def _values_equal(a: Any, b: Any) -> bool:
    if type(a) != type(b) and not (isinstance(a, (str, type(None))) and isinstance(b, (str, type(None)))):
        # bool vs int etc.
        if isinstance(a, bool) or isinstance(b, bool):
            return a is b
    if isinstance(a, list) and isinstance(b, list):
        return [str(x) for x in a] == [str(x) for x in b]
    return a == b


@dataclass
class TableSection:
    """One [header] table and its key/value pairs (in file order)."""

    header: str  # e.g. profiles.lab-workspace
    keys: Dict[str, Any] = field(default_factory=dict)
    key_order: List[str] = field(default_factory=list)
    # Full raw body lines after header (for non-profile tables we keep verbatim).
    raw_body_lines: List[str] = field(default_factory=list)
    managed: bool = False  # True when we may edit keys (lab profiles from fragment)

    def set_key(self, key: str, value: Any) -> None:
        if key not in self.keys:
            self.key_order.append(key)
        self.keys[key] = value

    def render(self) -> str:
        lines = ["[%s]" % self.header]
        if self.managed:
            for k in self.key_order:
                lines.append("%s = %s" % (k, _format_value(self.keys[k])))
            lines.append("")
            return "\n".join(lines)
        # Preserve original body (may include comments / unknown shapes)
        body = list(self.raw_body_lines)
        # Drop trailing blank lines for stable join; re-add one
        while body and body[-1].strip() == "":
            body.pop()
        lines.extend(body)
        lines.append("")
        return "\n".join(lines)


@dataclass
class TomlDoc:
    """Document as preamble text + ordered table sections."""

    preamble: str = ""
    sections: List[TableSection] = field(default_factory=list)

    def profile_section(self, name: str) -> Optional[TableSection]:
        header = "profiles.%s" % name
        for sec in self.sections:
            if sec.header == header:
                return sec
        return None

    def render(self) -> str:
        parts: List[str] = []
        if self.preamble:
            p = self.preamble
            if not p.endswith("\n"):
                p += "\n"
            parts.append(p)
            if not p.endswith("\n\n") and self.sections:
                # single blank between preamble and first table if needed
                if not p.endswith("\n"):
                    parts.append("\n")
        for sec in self.sections:
            parts.append(sec.render())
        text = "".join(parts)
        if text and not text.endswith("\n"):
            text += "\n"
        return text


def parse_toml_doc(text: str) -> TomlDoc:
    """Parse sandbox.toml-shaped documents into TomlDoc."""
    if text is None:
        text = ""
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    # Keep trailing content structure; drop final empty from split if file ends \n
    if lines and lines[-1] == "":
        lines = lines[:-1]

    doc = TomlDoc()
    preamble_lines: List[str] = []
    current: Optional[TableSection] = None
    array_key: Optional[str] = None
    array_buf: List[str] = []

    def flush_array() -> None:
        nonlocal array_key, array_buf, current
        if current is None or array_key is None:
            array_key = None
            array_buf = []
            return
        joined = " ".join(array_buf)
        val = _parse_value(joined)
        current.set_key(array_key, val)
        if not current.managed:
            # also keep in raw — already pushed as we went; for managed we rebuild
            pass
        array_key = None
        array_buf = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Multi-line array continuation
        if array_key is not None and current is not None:
            array_buf.append(stripped if stripped else line)
            if not current.managed:
                current.raw_body_lines.append(line)
            if "]" in stripped:
                flush_array()
            i += 1
            continue

        m = _HEADER_RE.match(stripped)
        if m and not stripped.startswith("#"):
            # new section
            header = m.group(1).strip()
            current = TableSection(header=header)
            # Manage only profiles.* tables for key parsing
            if header.startswith("profiles."):
                current.managed = True
            doc.sections.append(current)
            i += 1
            continue

        if current is None:
            preamble_lines.append(line)
            i += 1
            continue

        # Inside a section
        if not current.managed:
            current.raw_body_lines.append(line)
            i += 1
            continue

        # Managed profile table: parse keys
        if stripped == "" or stripped.startswith("#"):
            # skip blanks/comments inside managed sections (we re-render)
            i += 1
            continue

        km = _KEY_RE.match(stripped)
        if not km:
            # unknown line — keep as raw by flipping? preserve via raw fallback
            current.raw_body_lines.append(line)
            i += 1
            continue

        key, raw_val = km.group(1), km.group(2).strip()
        if raw_val.startswith("[") and "]" not in raw_val:
            array_key = key
            array_buf = [raw_val]
            i += 1
            continue
        try:
            val = _parse_value(raw_val)
        except ValueError:
            current.raw_body_lines.append(line)
            i += 1
            continue
        current.set_key(key, val)
        i += 1

    if array_key is not None:
        flush_array()

    doc.preamble = "\n".join(preamble_lines)
    if preamble_lines:
        doc.preamble += "\n"
    return doc


def parse_fragment_profiles(text: str) -> Dict[str, Dict[str, Any]]:
    """Return {profile_short_name: {key: value}} for [profiles.*] in fragment."""
    doc = parse_toml_doc(text)
    out: Dict[str, Dict[str, Any]] = {}
    for sec in doc.sections:
        if not sec.header.startswith("profiles."):
            continue
        name = sec.header[len("profiles.") :]
        out[name] = {k: sec.keys[k] for k in sec.key_order}
    return out


@dataclass
class MergeResult:
    """Outcome of a missing-key-only merge."""

    path: Path
    created_file: bool = False
    added_profiles: List[str] = field(default_factory=list)
    added_keys: List[str] = field(default_factory=list)  # "profile.key"
    skipped_same: List[str] = field(default_factory=list)  # already present identical
    conflicts: List[str] = field(default_factory=list)  # "profile.key: existing != fragment"
    unchanged: bool = True

    def summary_lines(self) -> List[str]:
        lines: List[str] = []
        lines.append("sandbox: %s" % self.path)
        if self.created_file:
            lines.append("  created new sandbox.toml")
        if self.added_profiles:
            lines.append("  added profiles: %s" % ", ".join(self.added_profiles))
        if self.added_keys:
            lines.append("  added keys: %s" % ", ".join(self.added_keys))
        if self.skipped_same:
            lines.append(
                "  already present: %s" % ", ".join(self.skipped_same)
            )
        if self.conflicts:
            lines.append("  conflicts (not overwritten):")
            for c in self.conflicts:
                lines.append("    - %s" % c)
            lines.append(
                "  resolve manually: diff fragment vs %s then edit keys you want"
                % self.path
            )
            lines.append(
                "  fragment: modules/sandbox/profiles.fragment.toml"
            )
        if self.unchanged and not self.created_file:
            lines.append("  no changes (all lab keys already present or conflicted)")
        return lines


def _render_profile_section(name: str, keys: Dict[str, Any], key_order: Optional[List[str]] = None) -> str:
    order = key_order or list(keys.keys())
    lines = ["[profiles.%s]" % name]
    for k in order:
        if k in keys:
            lines.append("%s = %s" % (k, _format_value(keys[k])))
    lines.append("")
    return "\n".join(lines)


def _section_span(lines: List[str], header: str) -> Optional[Tuple[int, int]]:
    """Return [start, end) line indices for [header] section (end = next header or len)."""
    start = None
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line.strip())
        if not m:
            continue
        if m.group(1).strip() == header:
            start = i
            continue
        if start is not None:
            return start, i
    if start is not None:
        return start, len(lines)
    return None


def merge_sandbox_toml(
    fragment_text: str,
    existing_text: str,
    *,
    lab_names: Optional[Sequence[str]] = None,
) -> Tuple[str, MergeResult]:
    """
    Merge fragment lab profiles into existing sandbox.toml text.

    - Missing profile section → append full section from fragment.
    - Existing profile, missing key → insert key lines only (preserve comments).
    - Existing key same value → skip.
    - Existing key different value → conflict (keep user value).
    Never removes or rewrites unrelated user content.
    """
    names = list(lab_names) if lab_names is not None else list(LAB_PROFILE_NAMES)
    fragment = parse_fragment_profiles(fragment_text)
    wanted = [n for n in names if n in fragment]
    for n in fragment:
        if n.startswith("lab-") and n not in wanted:
            wanted.append(n)

    result = MergeResult(path=Path("."))
    existing_text = existing_text or ""
    # Normalize to lines without forcing a trailing empty element
    text = existing_text.replace("\r\n", "\n").replace("\r", "\n")
    if text == "":
        lines: List[str] = []
    else:
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

    doc = parse_toml_doc(existing_text)
    append_blocks: List[str] = []
    # Map header -> list of key lines to insert after the header line
    inserts: Dict[str, List[str]] = {}

    for name in wanted:
        frag_keys = fragment[name]
        header = "profiles.%s" % name
        sec = doc.profile_section(name)
        if sec is None:
            append_blocks.append(_render_profile_section(name, frag_keys, list(frag_keys.keys())))
            result.added_profiles.append(name)
            result.unchanged = False
            continue

        if not sec.keys and sec.raw_body_lines:
            raw_blob = "[%s]\n%s" % (header, "\n".join(sec.raw_body_lines))
            recovered = parse_toml_doc(raw_blob)
            rsec = recovered.profile_section(name)
            if rsec:
                sec.keys = dict(rsec.keys)
                sec.key_order = list(rsec.key_order)

        missing_lines: List[str] = []
        for k, v in frag_keys.items():
            if k not in sec.keys:
                missing_lines.append("%s = %s" % (k, _format_value(v)))
                result.added_keys.append("%s.%s" % (name, k))
                result.unchanged = False
            elif _values_equal(sec.keys[k], v):
                result.skipped_same.append("%s.%s" % (name, k))
            else:
                result.conflicts.append(
                    "%s.%s: existing=%s fragment=%s"
                    % (name, k, _format_value(sec.keys[k]), _format_value(v))
                )
        if missing_lines:
            inserts[header] = missing_lines

    # Apply inserts (from bottom to top so indices stay valid)
    if inserts:
        # Build list of (start, header) sorted by start descending
        spans = []
        for header in inserts:
            span = _section_span(lines, header)
            if span is not None:
                spans.append((span[0], header))
        spans.sort(key=lambda x: x[0], reverse=True)
        for start, header in spans:
            # Insert immediately after the header line
            for j, kl in enumerate(inserts[header]):
                lines.insert(start + 1 + j, kl)

    out = "\n".join(lines)
    if out and not out.endswith("\n"):
        out += "\n"
    if append_blocks:
        if out and not out.endswith("\n\n"):
            if out.endswith("\n"):
                out += "\n"
            else:
                out += "\n\n"
        out += "\n".join(append_blocks)
        if not out.endswith("\n"):
            out += "\n"

    return out, result


def load_fragment(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def install_profiles(
    fragment_path: Path,
    target_path: Path,
    *,
    dry_run: bool = False,
    lab_names: Optional[Sequence[str]] = None,
) -> MergeResult:
    """
    Merge fragment into target_path (create parent dirs as needed).
    Missing-key-only. Returns MergeResult with path set.
    """
    fragment_text = load_fragment(fragment_path)
    created = not target_path.is_file()
    existing = target_path.read_text(encoding="utf-8") if not created else ""

    new_text, result = merge_sandbox_toml(
        fragment_text, existing, lab_names=lab_names
    )
    result.path = target_path
    result.created_file = created

    should_write = bool(result.added_profiles or result.added_keys or created)
    if created and not (result.added_profiles or result.added_keys):
        # Empty target + empty fragment edge case: still no write needed
        should_write = bool(parse_fragment_profiles(fragment_text))

    if dry_run:
        if should_write:
            result.unchanged = False
        return result

    if should_write:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_text, encoding="utf-8")
        try:
            target_path.chmod(0o600)
        except OSError:
            pass
        result.unchanged = False
        result.created_file = created
    else:
        result.created_file = False
    return result

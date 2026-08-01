#!/usr/bin/env python3
# Grok Star Lab — Showroom index regenerator
"""Rebuild showroom/index.html from showroom/entries/*/meta.json (date desc)."""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_LIB = _REPO / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lab_paths import repo_root  # noqa: E402


def showroom_dir(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "showroom"


def entries_dir(root: Optional[Path] = None) -> Path:
    return showroom_dir(root) / "entries"


def load_entries(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all entry meta.json files. Deterministic sort: published_at/created_at desc, then id."""
    base = entries_dir(root)
    if not base.is_dir():
        return []
    items: List[Dict[str, Any]] = []
    for meta_path in sorted(base.glob("*/meta.json")):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        entry_id = data.get("entry_id") or meta_path.parent.name
        data = dict(data)
        data["entry_id"] = entry_id
        data["_dir"] = meta_path.parent.name
        items.append(data)

    def sort_key(m: Dict[str, Any]) -> tuple:
        # Newest first; missing dates sort last among peers via empty string inverted
        date = m.get("published_at") or m.get("created_at") or ""
        eid = m.get("entry_id") or ""
        return (date, eid)

    items.sort(key=sort_key, reverse=True)
    return items


def _esc(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def _kind_class(kind: str) -> str:
    k = (kind or "manual").lower()
    if k in ("demo", "design", "ship", "asset", "experiment", "manual"):
        return k
    return "manual"


def render_index_html(entries: List[Dict[str, Any]]) -> str:
    """Return full HTML document for the showroom gallery."""
    cards: List[str] = []
    for e in entries:
        eid = _esc(e.get("entry_id"))
        title = _esc(e.get("title") or e.get("entry_id"))
        kind = _esc(e.get("kind") or "manual")
        kind_cls = _kind_class(str(e.get("kind") or "manual"))
        summary = _esc(e.get("summary") or "")
        project = e.get("project")
        date = _esc(e.get("published_at") or e.get("created_at") or "")
        proj_html = (
            '<span class="project">%s</span>' % _esc(project) if project else ""
        )
        proof = e.get("proof_commands") or []
        proof_html = ""
        if proof:
            lines = "".join(
                "<code>%s</code>" % _esc(c) for c in proof[:4]
            )
            proof_html = '<div class="proof">%s</div>' % lines
        body_link = "entries/%s/body.md" % _esc(e.get("_dir") or e.get("entry_id"))
        cards.append(
            """
      <article class="card kind-{kind_cls}">
        <div class="meta">
          <span class="kind">{kind}</span>
          {proj}
          <time>{date}</time>
        </div>
        <h2><a href="{body}">{title}</a></h2>
        <p class="summary">{summary}</p>
        {proof}
        <p class="id"><code>{eid}</code></p>
      </article>""".format(
                kind_cls=kind_cls,
                kind=kind,
                proj=proj_html,
                date=date,
                body=body_link,
                title=title,
                summary=summary,
                proof=proof_html,
                eid=eid,
            )
        )

    count = len(entries)
    generated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    cards_html = "\n".join(cards) if cards else (
        '      <p class="empty">No curated entries yet. '
        "Capture with <code>lab showroom capture</code>, "
        "then <code>lab showroom publish</code>.</p>"
    )

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Grok Star Lab · Showroom</title>
  <style>
    :root {{
      --bg: #0a0e17;
      --panel: #111827;
      --line: #1e293b;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --cyan: #22d3ee;
      --magenta: #e879f9;
      --green: #34d399;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(1000px 500px at 10% -10%, rgba(232,121,249,.16), transparent 55%),
        radial-gradient(800px 400px at 90% 0%, rgba(34,211,238,.12), transparent 50%),
        var(--bg);
      min-height: 100vh;
    }}
    .wrap {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }}
    header {{ margin-bottom: 28px; }}
    .eyebrow {{
      color: var(--cyan);
      letter-spacing: .14em;
      text-transform: uppercase;
      font-size: 12px;
      font-weight: 700;
      margin: 0 0 10px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1.05;
      background: linear-gradient(90deg, #fff, var(--cyan) 55%, var(--magenta));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }}
    .sub {{ color: var(--muted); margin: 0; line-height: 1.5; }}
    .nav {{ margin-top: 14px; display: flex; flex-wrap: wrap; gap: 10px; }}
    .nav a {{
      color: var(--cyan);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 13px;
      background: #0b1220;
    }}
    .nav a:hover {{ border-color: var(--cyan); }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }}
    .card {{
      background: rgba(17,24,39,.9);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px;
    }}
    .card h2 {{ margin: 8px 0 8px; font-size: 1.15rem; }}
    .card h2 a {{ color: var(--text); text-decoration: none; }}
    .card h2 a:hover {{ color: var(--cyan); }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      font-size: 12px;
      color: var(--muted);
    }}
    .kind {{
      text-transform: uppercase;
      letter-spacing: .08em;
      font-weight: 700;
      color: var(--cyan);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
    }}
    .project {{ color: var(--magenta); }}
    .summary {{ color: var(--muted); margin: 0 0 8px; line-height: 1.45; }}
    .proof code {{
      display: block;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      background: #020617;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      color: #a5f3fc;
      margin: 4px 0;
      overflow-x: auto;
    }}
    .id {{ margin: 10px 0 0; font-size: 12px; color: var(--muted); }}
    .empty {{ color: var(--muted); }}
    footer {{
      margin-top: 28px;
      color: var(--muted);
      font-size: 13px;
    }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <p class="eyebrow">Star Lab · Portfolio</p>
      <h1>Showroom</h1>
      <p class="sub">
        Curated best work — inbox capture is private; publish is explicit.
        {count} entr{plural} on disk.
      </p>
      <div class="nav">
        <a href="../dashboard/index.html">Mission Control</a>
        <a href="../docs/COMPARE-WITH-CLAUDE.md">Claude compare</a>
        <a href="../docs/PROOF.txt">Proof</a>
      </div>
    </header>
    <section class="grid">
{cards}
    </section>
    <footer>
      Regenerated {generated} · <code>lab showroom list</code> ·
      <code>lab showroom publish</code> · no auto-publish
    </footer>
  </div>
</body>
</html>
""".format(
        count=count,
        plural="y" if count == 1 else "ies",
        cards=cards_html,
        generated=generated,
    )


def regenerate(root: Optional[Path] = None) -> Path:
    """Load entries, write showroom/index.html, return path written."""
    r = root or repo_root()
    sdir = showroom_dir(r)
    sdir.mkdir(parents=True, exist_ok=True)
    entries = load_entries(r)
    out = sdir / "index.html"
    out.write_text(render_index_html(entries), encoding="utf-8")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    root = repo_root()
    if argv and len(argv) > 0:
        root = Path(argv[0]).resolve()
    path = regenerate(root)
    n = len(load_entries(root))
    print("showroom: regenerated %s (%d entries)" % (path, n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

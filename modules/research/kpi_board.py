"""Write KPI JSON + HTML fragment for the local portal."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def write_kpi_board(kpi: Optional[Dict[str, Any]] = None) -> Path:
    if kpi is None:
        from research.logstore import ResearchLog

        kpi = ResearchLog().kpi()

    data_dir = _lab_data()
    data_dir.mkdir(parents=True, exist_ok=True)
    json_path = data_dir / "research_kpi.json"
    json_path.write_text(json.dumps(kpi, indent=2) + "\n", encoding="utf-8")

    # Also copy into portal for static server
    portal = _repo_root() / "portal"
    portal.mkdir(parents=True, exist_ok=True)
    (portal / "kpi.json").write_text(json.dumps(kpi, indent=2) + "\n", encoding="utf-8")

    def fmt(x: Any) -> str:
        if x is None:
            return "n/a"
        if isinstance(x, float):
            return f"{x:.3f}"
        return str(x)

    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(kpi.get("generated_at") or time.time()))
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Research KPI Board · Loop 4</title>
<style>
  body {{ margin:0; font-family: system-ui, sans-serif; background:#0b1020; color:#e8eefc; padding:28px; }}
  h1 {{ margin:0 0 6px; }}
  .sub {{ color:#9aa8c7; margin-bottom:22px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }}
  .card {{ background:#121a2f; border:1px solid #243049; border-radius:12px; padding:14px; }}
  .k {{ color:#9aa8c7; font-size:0.75rem; text-transform:uppercase; letter-spacing:.06em; }}
  .v {{ font-size:1.4rem; margin-top:6px; font-variant-numeric:tabular-nums; }}
  a {{ color:#7aa2ff; }}
  pre {{ background:#0a0f1c; padding:12px; border-radius:10px; overflow:auto; font-size:0.8rem; }}
</style>
</head>
<body>
  <h1>Research KPI Board</h1>
  <p class="sub">Loop 4 · measure / compare / redeploy · {ts} · <a href="index.html">portal</a></p>
  <div class="grid">
    <div class="card"><div class="k">Completed logs</div><div class="v">{fmt(kpi.get("n_completed_logs"))}</div></div>
    <div class="card"><div class="k">Accepted patch rate</div><div class="v">{fmt(kpi.get("accepted_patch_rate"))}</div></div>
    <div class="card"><div class="k">Test pass rate</div><div class="v">{fmt(kpi.get("test_pass_rate"))}</div></div>
    <div class="card"><div class="k">Avg tokens / success</div><div class="v">{fmt(kpi.get("average_tokens_per_success"))}</div></div>
    <div class="card"><div class="k">Recovery rate</div><div class="v">{fmt(kpi.get("recovery_rate_after_failure"))}</div></div>
    <div class="card"><div class="k">Latency / task (s)</div><div class="v">{fmt(kpi.get("latency_per_completed_task_s"))}</div></div>
    <div class="card"><div class="k">Human interrupts avg</div><div class="v">{fmt(kpi.get("human_interruptions_avg"))}</div></div>
    <div class="card"><div class="k">SQC task pass rate</div><div class="v">{fmt(kpi.get("sqc_pass_rate"))}</div></div>
    <div class="card"><div class="k">SQC loop accept rate</div><div class="v">{fmt(kpi.get("sqc_loop_accept_rate"))}</div></div>
    <div class="card"><div class="k">Token audits n</div><div class="v">{fmt((kpi.get("token_audit_stats") or {}).get("n"))}</div></div>
    <div class="card"><div class="k">Token horizon MAE</div><div class="v">{fmt((kpi.get("token_audit_stats") or {}).get("mae"))}</div></div>
    <div class="card"><div class="k">Last SQC decision</div><div class="v" style="font-size:1rem">{fmt(kpi.get("last_sqc_decision"))}</div></div>
  </div>
  <h2 style="margin-top:28px;font-size:1rem;color:#9aa8c7">Raw JSON</h2>
  <pre>{json.dumps(kpi, indent=2)}</pre>
</body>
</html>
"""
    board = portal / "kpi.html"
    board.write_text(html, encoding="utf-8")

    # Patch portal index link if present
    index = portal / "index.html"
    if index.exists():
        text = index.read_text(encoding="utf-8")
        if "kpi.html" not in text:
            text = text.replace(
                '<li><a href="../README.md">README</a></li>',
                '<li><a href="../README.md">README</a></li>\n'
                '          <li><a href="kpi.html"><strong>Research KPI board</strong></a></li>',
            )
            index.write_text(text, encoding="utf-8")
    return board

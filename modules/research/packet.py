"""
Context packets for disciplined Grok escalation (paper Loop 1).

Structured packets replace free-form prompt stuffing: goal, route, budget,
top files, validation requirements, risk — high signal, bounded size.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def packets_dir() -> Path:
    d = _lab_data() / "packets"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(d), 0o700)
    except OSError:
        pass
    return d


def create_packet(
    task_goal: str,
    *,
    repo: str = "",
    files: Optional[Sequence[str]] = None,
    route: Optional[Dict[str, Any]] = None,
    failing_tests: Optional[str] = None,
    validation_requirements: Optional[Sequence[str]] = None,
    risk_score: Optional[float] = None,
    user_priority: str = "normal",
    notes: str = "",
    max_files: int = 12,
) -> Dict[str, Any]:
    """Build and persist a context packet; return the packet dict."""
    route = route or {}
    packing = route.get("packing") or {}
    files_list = [str(f) for f in (files or [])][:max_files]
    # Prefer absolute paths when possible
    norm_files = []
    for f in files_list:
        p = Path(f).expanduser()
        try:
            norm_files.append(str(p.resolve()) if p.exists() else str(p))
        except OSError:
            norm_files.append(str(p))

    pid = uuid.uuid4().hex[:12]
    packet = {
        "schema_version": 1,
        "id": pid,
        "ts": time.time(),
        "task_goal": task_goal.strip(),
        "repo": repo,
        "mode": route.get("mode"),
        "token_budget": route.get("budget_tokens") or packing.get("max_context_tokens"),
        "predicted_horizon": route.get("predicted_horizon"),
        "route_ev": route.get("expected_value"),
        "token_audit_id": route.get("audit_id"),
        "risk_score": risk_score,
        "user_priority": user_priority,
        "files": norm_files,
        "failing_tests": failing_tests or "",
        "validation_requirements": list(validation_requirements or ["tests", "no-regression"]),
        "packing": packing,
        "route": {
            k: route.get(k)
            for k in (
                "mode",
                "budget_tokens",
                "predicted_horizon",
                "expected_value",
                "local_expected_value",
                "escalate",
                "confidence",
                "reasons",
            )
            if k in route
        },
        "notes": notes,
    }
    path = packets_dir() / f"{pid}.json"
    path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    md_path = packets_dir() / f"{pid}.md"
    md_path.write_text(render_markdown(packet), encoding="utf-8")
    packet["path"] = str(path)
    packet["md_path"] = str(md_path)
    return packet


def load_packet(id_or_path: str) -> Dict[str, Any]:
    p = Path(id_or_path).expanduser()
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    # bare id
    cand = packets_dir() / f"{id_or_path}.json"
    if cand.is_file():
        return json.loads(cand.read_text(encoding="utf-8"))
    # prefix match
    matches = list(packets_dir().glob(f"{id_or_path}*.json"))
    if len(matches) == 1:
        return json.loads(matches[0].read_text(encoding="utf-8"))
    if len(matches) > 1:
        raise FileNotFoundError(f"ambiguous packet id: {id_or_path}")
    raise FileNotFoundError(f"packet not found: {id_or_path}")


def render_markdown(packet: Dict[str, Any]) -> str:
    files = packet.get("files") or []
    file_lines = "\n".join(f"- `{f}`" for f in files) or "- (none)"
    reqs = packet.get("validation_requirements") or []
    req_lines = "\n".join(f"- {r}" for r in reqs) or "- (none)"
    route = packet.get("route") or {}
    return f"""# Context packet `{packet.get('id')}`

## Goal
{packet.get('task_goal')}

## Repo
`{packet.get('repo') or '—'}`

## Route / budget
- mode: `{packet.get('mode')}`
- token_budget: `{packet.get('token_budget')}`
- predicted_horizon: `{packet.get('predicted_horizon')}`
- escalate: `{route.get('escalate')}`
- EV: `{packet.get('route_ev')}` (local EV `{route.get('local_expected_value')}`)
- risk_score: `{packet.get('risk_score')}`
- priority: `{packet.get('user_priority')}`

## Top files
{file_lines}

## Failing tests / last validation
```
{packet.get('failing_tests') or '(none captured)'}
```

## Validation requirements
{req_lines}

## Notes
{packet.get('notes') or '—'}

---
_Use this packet when escalating to Grok Build. Do not paste the whole repo._
"""


def collect_test_output(cmd: Sequence[str], cwd: Optional[str] = None, timeout: float = 60.0) -> str:
    import subprocess

    try:
        r = subprocess.run(
            list(cmd),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return f"exit={r.returncode}\n{out[-4000:]}"
    except Exception as e:
        return f"error running tests: {e}"

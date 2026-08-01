"""
LEAD-style short-horizon recovery (paper Loop 2).

On failure: log recovery, optionally re-run validation once, attach a scope-cut
plan if still failing. Does not invent patches — keeps the control plane honest.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from .logstore import ResearchLog


@dataclass
class RecoveryResult:
    task_id: str
    retried: bool
    retry_ok: Optional[bool]
    recovery_triggered: bool
    plan: List[str]
    notes: str
    cmd: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT_PLAN = [
    "Cut scope: fix one failing unit / one file first",
    "Re-run the same validation command after the minimal fix",
    "If still red: capture failing output into a context packet and escalate with budget",
    "Avoid expanding refactor radius until the atomic unit is green",
]


def recover(
    task_id: str,
    *,
    cmd: Optional[Sequence[str]] = None,
    cmd_str: Optional[str] = None,
    cwd: Optional[str] = None,
    timeout: float = 120.0,
    log: Optional[ResearchLog] = None,
) -> RecoveryResult:
    """
    Mark recovery on an open research task and optionally re-run validation once.
    """
    log = log or ResearchLog()
    payload = log._load(task_id)  # intentional: need open payload
    if payload.get("status") not in ("open",):
        # still allow recovery notes on recently failed completes? plan says open — soft allow
        pass

    # resolve command
    argv: List[str] = []
    if cmd:
        argv = list(cmd)
    elif cmd_str:
        argv = shlex.split(cmd_str)
    else:
        # try last validate action notes or default unittest
        for act in reversed(payload.get("actions") or []):
            if act.get("type") == "validate" and act.get("name"):
                # default re-run pattern
                break
        argv = ["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]

    cmd_display = " ".join(shlex.quote(a) for a in argv)
    log.action(
        task_id,
        type="other",
        name="recovery_start",
        ok=True,
        notes=f"LEAD recovery; will retry: {cmd_display}",
    )

    retry_ok: Optional[bool] = None
    retried = False
    notes = ""
    if argv:
        retried = True
        try:
            r = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            retry_ok = r.returncode == 0
            tail = ((r.stdout or "") + (r.stderr or ""))[-1500:]
            notes = f"retry exit={r.returncode}\n{tail}"
            log.action(
                task_id,
                type="validate",
                name="recovery_retry",
                ok=bool(retry_ok),
                notes=notes[:2000],
            )
        except Exception as e:
            retry_ok = False
            notes = f"retry error: {e}"
            log.action(task_id, type="validate", name="recovery_retry", ok=False, notes=notes)

    plan = list(DEFAULT_PLAN)
    if retry_ok is True:
        plan = [
            "Recovery retry passed — complete the research task as success if goals met",
            "Record actual tokens and mark recovery.triggered for KPI credit",
        ]
        notes = (notes or "") + "\nrecovery_retry=ok"
    elif retry_ok is False:
        plan = DEFAULT_PLAN + [
            f"Last retry still failing for: {cmd_display}",
            "Create/update a context packet with failing_tests before Grok escalate",
        ]

    # persist recovery on payload without completing
    p = log._load(task_id)
    p.setdefault("recovery", {})
    p["recovery"]["triggered"] = True
    p["recovery"]["notes"] = (p["recovery"].get("notes") or "") + (
        f"\n[{time.time()}] {notes[:500]}"
    )
    p["recovery"]["plan"] = plan
    p["recovery"]["last_cmd"] = cmd_display
    p["recovery"]["retry_ok"] = retry_ok
    log._save(p)

    return RecoveryResult(
        task_id=task_id,
        retried=retried,
        retry_ok=retry_ok,
        recovery_triggered=True,
        plan=plan,
        notes=notes[:2000],
        cmd=cmd_display,
    )

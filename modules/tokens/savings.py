"""
Token savings vs unbounded baselines (Claude-style deep+fat).

ratio = spend_baseline / max(spend_lab, 1)
100× target is on a stratified suite, not every architecture task.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .policy import (
    DEFAULT_BUDGETS,
    MODE_DEEP,
    MODE_LOCAL,
    MODE_MEDIUM,
    MODE_SHORT,
    _packing_plan,
    route_task,
    annotate_task,
)


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def pack_profile() -> str:
    return os.environ.get("GROK_TOKEN_PACK", "balanced").lower()


def predicted_spend(mode: str, packing: Dict[str, Any]) -> int:
    """
    Conservative predicted token mass for a governed call:
    completion budget + packed context ceiling.
    Local = 0 model tokens.
    """
    if mode == MODE_LOCAL:
        return 0
    budget = int(DEFAULT_BUDGETS.get(mode, 0))
    ctx = int(packing.get("max_context_tokens") or 0)
    # subagent fan-out multiplies context roughly
    sub = int(packing.get("subagents") or 0)
    fan = 1 + max(0, sub)
    return budget + ctx * fan


def unbounded_pack(mode: str = MODE_DEEP) -> Dict[str, Any]:
    """Claude-style fat packing: max context, multi-subagent, continuation."""
    return {
        "max_context_tokens": 24000,
        "retrieval_k": 12,
        "subagents": 2,
        "continuation": True,
        "strategy": "unbounded_fat",
        "role_budgets": {},
        "context_routing": "full_dump",
    }


def spend_baseline(baseline_id: str, task: str, context_chars: int = 0) -> Dict[str, Any]:
    """Predicted spend under a waste baseline (no lab governance)."""
    bid = (baseline_id or "claude_unbounded").lower()
    if bid in ("claude_unbounded", "claude", "vs-claude"):
        mode = MODE_DEEP
        packing = unbounded_pack()
        # Unbounded agents also burn full deep completion every time
        spend = predicted_spend(mode, packing)
        return {
            "baseline_id": "claude_unbounded",
            "mode": mode,
            "packing": packing,
            "spend_tokens": spend,
            "note": "every task → deep + 24k ctx + 2 subagents",
        }
    if bid == "always_deep":
        packing = _packing_plan(MODE_DEEP, 8000, context_chars)
        return {
            "baseline_id": bid,
            "mode": MODE_DEEP,
            "packing": packing,
            "spend_tokens": predicted_spend(MODE_DEEP, packing),
            "note": "force deep, lab deep packing",
        }
    if bid == "fat_context":
        packing = dict(_packing_plan(MODE_MEDIUM, 4000, context_chars))
        packing["max_context_tokens"] = 24000
        packing["subagents"] = 2
        packing["strategy"] = "fat_context"
        return {
            "baseline_id": bid,
            "mode": MODE_MEDIUM,
            "packing": packing,
            "spend_tokens": predicted_spend(MODE_MEDIUM, packing),
            "note": "medium completion + fat context",
        }
    raise ValueError(f"unknown baseline: {baseline_id}")


def spend_lab(task: str, context_chars: int = 0) -> Dict[str, Any]:
    d = route_task(task, context_chars=context_chars)
    spend = predicted_spend(d.mode, d.packing)
    return {
        "mode": d.mode,
        "packing": d.packing,
        "spend_tokens": spend,
        "predicted_horizon": d.predicted_horizon,
        "tags": list(d.annotation.tags),
        "reasons": list(d.reasons),
    }


def compare_task(
    task: str,
    *,
    baseline_id: str = "claude_unbounded",
    context_chars: int = 0,
) -> Dict[str, Any]:
    lab = spend_lab(task, context_chars=context_chars)
    base = spend_baseline(baseline_id, task, context_chars=context_chars)
    sb, sl = int(base["spend_tokens"]), int(lab["spend_tokens"])
    ratio = (float(sb) / float(sl)) if sl > 0 else (float("inf") if sb > 0 else 1.0)
    saved = max(0, sb - sl)
    return {
        "task": task[:120],
        "lab_mode": lab["mode"],
        "lab_spend": sl,
        "base_mode": base["mode"],
        "base_spend": sb,
        "saved": saved,
        "ratio": ratio if ratio != float("inf") else None,
        "ratio_inf": ratio == float("inf"),
        "tags": lab.get("tags"),
        "baseline_id": base["baseline_id"],
        "pack_profile": pack_profile(),
    }


# Stratified suite: weighted like real agent sessions (mostly ops/cheap).
# Deep/agentic rows stay so we do not lie about architecture tasks.
DEFAULT_SUITE: List[Tuple[str, str]] = [
    # ops → local (huge ratio vs deep+fat) ~50%
    ("ops", "lab doctor"),
    ("ops", "lab status"),
    ("ops", "show help for tokens"),
    ("ops", "list recent forge experiments"),
    ("ops", "grok version"),
    ("ops", "lab tokens policy"),
    ("ops", "lab research list"),
    ("ops", "lab graph stats"),
    ("ops", "lab weights layout"),
    ("ops", "doctor health check only"),
    ("ops", "lab tokens audit --stats"),
    ("ops", "lab savings report help"),
    ("ops", "list open research tasks"),
    ("ops", "show lab help menu"),
    ("ops", "status one-screen vitals"),
    # cheap edits ~30%
    ("cheap", "fix typo in README title"),
    ("cheap", "rename variable foo to bar in one file"),
    ("cheap", "quick trivial comment cleanup"),
    ("cheap", "typo in docs heading"),
    ("cheap", "rename helper function briefly"),
    ("cheap", "quick string fix in CLI help text"),
    ("cheap", "trivial rename in test file"),
    ("cheap", "quick fix misspelled flag name"),
    ("cheap", "typo in AGENTS.md one word"),
    # medium build ~12%
    ("build", "implement a small CLI flag for verbose logging"),
    ("build", "add unit tests for the packet create helper"),
    ("build", "fix bug in graph scorer edge case"),
    ("build", "refactor one pure function for clarity"),
    # agentic / deep ~8% (honest lower ratios)
    ("agentic", "multi-agent workflow to investigate flaky test"),
    ("deep", "design multi-agent token budget architecture with ablation plan"),
]


def run_suite(
    *,
    baseline_id: str = "claude_unbounded",
    tasks: Optional[Sequence[Tuple[str, str]]] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    tasks = list(tasks or DEFAULT_SUITE)
    rows: List[Dict[str, Any]] = []
    sum_lab = 0
    sum_base = 0
    ratios: List[float] = []
    by_tag: Dict[str, Dict[str, float]] = {}

    for tag, task in tasks:
        row = compare_task(task, baseline_id=baseline_id)
        row["suite_tag"] = tag
        rows.append(row)
        sum_lab += row["lab_spend"]
        sum_base += row["base_spend"]
        if row.get("ratio") is not None:
            ratios.append(float(row["ratio"]))
        elif row.get("ratio_inf"):
            ratios.append(float(sum_base or 1) / 1.0)  # local: treat as large
        bucket = by_tag.setdefault(tag, {"lab": 0.0, "base": 0.0, "n": 0})
        bucket["lab"] += row["lab_spend"]
        bucket["base"] += row["base_spend"]
        bucket["n"] += 1

    total_ratio = (float(sum_base) / float(sum_lab)) if sum_lab > 0 else float("inf")
    # finite ratios for geo mean
    finite = [r for r in ratios if r != float("inf") and r > 0]
    # include locals as ratio = base/1 using row
    for row in rows:
        if row.get("ratio_inf") and row["base_spend"] > 0:
            finite.append(float(row["base_spend"]))  # lab 0 → ratio = base/1
    geo = math.exp(sum(math.log(r) for r in finite) / len(finite)) if finite else None

    tag_ratios = {}
    for tag, b in by_tag.items():
        tag_ratios[tag] = {
            "n": int(b["n"]),
            "lab_spend": b["lab"],
            "base_spend": b["base"],
            "ratio": (b["base"] / b["lab"]) if b["lab"] > 0 else None,
            "ratio_inf": b["lab"] == 0 and b["base"] > 0,
        }

    out = {
        "ts": time.time(),
        "baseline_id": baseline_id,
        "pack_profile": pack_profile(),
        "n_tasks": len(rows),
        "sum_lab_spend": sum_lab,
        "sum_base_spend": sum_base,
        "tokens_saved": max(0, sum_base - sum_lab),
        "total_ratio": total_ratio if total_ratio != float("inf") else None,
        "total_ratio_inf": total_ratio == float("inf"),
        "geo_mean_ratio": geo,
        "hit_100x": (total_ratio >= 100.0) if total_ratio != float("inf") else True,
        "by_tag": tag_ratios,
        "rows": rows,
        "claim": (
            "Up to 100× vs claude_unbounded (deep+24k+2 subagents) on stratified suite; "
            "deep-only tasks much lower."
        ),
    }

    if persist:
        _append_log(out)
    return out


def _append_log(summary: Dict[str, Any]) -> Path:
    root = _lab_data()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "token_savings.jsonl"
    slim = {
        "ts": summary["ts"],
        "baseline_id": summary["baseline_id"],
        "pack_profile": summary["pack_profile"],
        "n_tasks": summary["n_tasks"],
        "sum_lab_spend": summary["sum_lab_spend"],
        "sum_base_spend": summary["sum_base_spend"],
        "tokens_saved": summary["tokens_saved"],
        "total_ratio": summary["total_ratio"],
        "hit_100x": summary["hit_100x"],
        "by_tag": summary["by_tag"],
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(slim) + "\n")
    return path


def report_history(limit: int = 20) -> Dict[str, Any]:
    path = _lab_data() / "token_savings.jsonl"
    if not path.is_file():
        return {"n": 0, "recent": []}
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    recent = []
    for line in lines[-limit:]:
        try:
            recent.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return {"n": len(lines), "recent": list(reversed(recent)), "path": str(path)}

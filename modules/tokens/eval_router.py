"""
Frozen golden suite vs live drift for L1 mode routing.

Separation:
  - frozen: checked-in goldens/router_v1.jsonl (immutable baseline)
  - drift:  last-N shadow/audit agreement vs frozen labels when tasks match
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .policy import route_task

_HERE = Path(__file__).resolve().parent
DEFAULT_SUITE = _HERE / "goldens" / "router_v1.jsonl"


def load_suite(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path or DEFAULT_SUITE
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _adjacent(a: str, b: str) -> bool:
    order = ["local", "short", "medium", "deep"]
    if a not in order or b not in order:
        return False
    return abs(order.index(a) - order.index(b)) == 1


def eval_frozen(
    *,
    suite_path: Optional[Path] = None,
    policy_id: str = "heuristic_v1",
) -> Dict[str, Any]:
    """Score current route_task against frozen expected modes."""
    suite = load_suite(suite_path)
    if not suite:
        return {
            "n": 0,
            "agreement": None,
            "adjacent_agreement": None,
            "error": f"suite missing: {suite_path or DEFAULT_SUITE}",
            "policy_id": policy_id,
            "suite": "frozen",
        }
    exact = 0
    adjacent = 0
    rows_out = []
    for item in suite:
        task = item.get("task") or ""
        expected = item.get("expected_mode") or item.get("mode")
        d = route_task(task)
        got = d.mode
        ok = got == expected
        adj = ok or _adjacent(got, expected)
        if ok:
            exact += 1
        if adj:
            adjacent += 1
        rows_out.append(
            {
                "id": item.get("id"),
                "expected": expected,
                "got": got,
                "exact": ok,
                "adjacent": adj,
                "must_not_deep": item.get("must_not_deep"),
                "deep_violation": bool(item.get("must_not_deep") and got == "deep"),
            }
        )
    n = len(suite)
    deep_viol = sum(1 for r in rows_out if r.get("deep_violation"))
    return {
        "n": n,
        "agreement": exact / n if n else None,
        "adjacent_agreement": adjacent / n if n else None,
        "deep_violations": deep_viol,
        "policy_id": policy_id,
        "suite": "frozen",
        "suite_path": str(suite_path or DEFAULT_SUITE),
        "items": rows_out,
    }


def eval_drift(
    frozen: Optional[Dict[str, Any]] = None,
    *,
    window: int = 50,
) -> Dict[str, Any]:
    """
    Compare live shadow mode distribution / MAE to frozen agreement baseline.

    Drift flags (heuristic):
      - frozen agreement drop if re-eval differs from stored baseline file
      - mode mix shift on recent shadows
    """
    frozen = frozen or eval_frozen()
    from .shadow import ShadowStore
    from .audit import AuditStore

    shadows = ShadowStore().recent(limit=window)
    by_mode: Dict[str, int] = {}
    for s in shadows:
        m = s.get("served_mode") or "?"
        by_mode[m] = by_mode.get(m, 0) + 1
    mae = AuditStore().error_stats().get("mae")

    # baseline snapshot path
    base_path = Path(
        os_path_lab() / "frozen_eval_baseline.json"
    )
    prev = None
    if base_path.is_file():
        try:
            prev = json.loads(base_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = None

    flags = []
    agr = frozen.get("agreement")
    if prev and agr is not None and prev.get("agreement") is not None:
        delta = agr - float(prev["agreement"])
        if delta < -0.05:
            flags.append(f"frozen_agreement_drop delta={delta:.3f}")
    if mae is not None and prev and prev.get("horizon_mae") is not None:
        if mae > float(prev["horizon_mae"]) * 1.5 + 100:
            flags.append(f"horizon_mae_spike {prev['horizon_mae']}→{mae}")

    return {
        "suite": "drift",
        "window": window,
        "n_shadow": len(shadows),
        "mode_mix": by_mode,
        "horizon_mae": mae,
        "frozen_agreement": agr,
        "frozen_adjacent": frozen.get("adjacent_agreement"),
        "flags": flags,
        "drift_detected": bool(flags),
        "baseline_path": str(base_path),
        "has_baseline": prev is not None,
    }


def os_path_lab() -> Path:
    import os

    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def freeze_baseline(frozen: Optional[Dict[str, Any]] = None) -> Path:
    """Persist current frozen eval as drift baseline (explicit human action)."""
    frozen = frozen or eval_frozen()
    from .audit import AuditStore

    payload = {
        "agreement": frozen.get("agreement"),
        "adjacent_agreement": frozen.get("adjacent_agreement"),
        "n": frozen.get("n"),
        "horizon_mae": AuditStore().error_stats().get("mae"),
        "policy_id": frozen.get("policy_id"),
    }
    root = os_path_lab()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "frozen_eval_baseline.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path

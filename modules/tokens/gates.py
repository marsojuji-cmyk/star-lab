"""
Graduation gates: shadow → golden/drift → canary → online learning.

Observation precedes influence. Do not train heavy heads or serve bandit
policies until the declared data bar is met.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


# Declared data bar for graduating shadow → online λ / light bandit.
# Override via ~/.grok/lab/graduation_bar.json or env GROK_* where noted.
DEFAULT_DATA_BAR: Dict[str, Any] = {
    "min_shadow_n": 50,
    "min_join_rate": 0.50,  # fraction of routes with completed audit
    "min_mode_agree_frac": 0.85,  # when shadow ≠ mirror policy
    "min_golden_agreement": 0.80,  # frozen suite exact mode match
    "max_horizon_mae": 2500.0,  # tokens; None to skip
    "require_sqc_accept": True,
    "max_fallback_chaos_fail_rate": 0.15,  # failure budget for recover chaos
    "min_canary_window_hours": 24,
    "canary_max_traffic_frac": 0.10,  # never auto-serve above this without promote
}


def load_data_bar() -> Dict[str, Any]:
    bar = dict(DEFAULT_DATA_BAR)
    path = _lab_data() / "graduation_bar.json"
    if path.is_file():
        try:
            bar.update(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    # env overrides
    if os.environ.get("GROK_GATE_MIN_SHADOW_N"):
        bar["min_shadow_n"] = int(os.environ["GROK_GATE_MIN_SHADOW_N"])
    if os.environ.get("GROK_GATE_MIN_JOIN"):
        bar["min_join_rate"] = float(os.environ["GROK_GATE_MIN_JOIN"])
    return bar


@dataclass
class GateCheck:
    name: str
    ok: bool
    observed: Any
    threshold: Any
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraduationReport:
    ready_for_online: bool
    ready_for_canary: bool
    checks: List[GateCheck] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    bar: Dict[str, Any] = field(default_factory=dict)
    drop_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready_for_online": self.ready_for_online,
            "ready_for_canary": self.ready_for_canary,
            "checks": [c.to_dict() for c in self.checks],
            "metrics": self.metrics,
            "bar": self.bar,
            "drop_rules": self.drop_rules,
            "order": [
                "0_packets_lead",
                "1_shadow_dual_log",
                "2_frozen_golden_drift",
                "3_canary_guarded_promotion",
                "4_online_lambda_bandit",
                "5_memory_skill",
                "6_cache_telemetry",
                "7_ablation",
            ],
        }


def _audit_join_rate() -> Dict[str, Any]:
    from .audit import AuditStore
    from .shadow import ShadowStore

    audits = AuditStore().recent(limit=500)
    shadows = ShadowStore().recent(limit=500)
    n_shadow = len(shadows)
    # join: shadow.audit_id present in completed audits (actual_tokens not null)
    completed = {
        r["id"]: r
        for r in audits
        if r.get("actual_tokens") is not None or r.get("success") is not None
    }
    joined = 0
    for s in shadows:
        aid = s.get("audit_id")
        if aid and aid in completed:
            joined += 1
    join_rate = (joined / n_shadow) if n_shadow else 0.0
    # mode agree among shadows
    agree = 0
    for s in shadows:
        if s.get("served_mode") == s.get("shadow_mode"):
            agree += 1
    agree_frac = (agree / n_shadow) if n_shadow else None
    return {
        "n_shadow": n_shadow,
        "n_audits": len(audits),
        "n_completed_audits": len(completed),
        "join_rate": join_rate,
        "mode_agree_frac": agree_frac,
    }


def _horizon_mae() -> Optional[float]:
    """Gate uses winsorized MAE on live (non-retro/seed) audits when available."""
    from .audit import AuditStore

    stats = AuditStore().error_stats(for_gate=True)
    # Prefer winsorized so a few 20k design outliers don't block forever
    if stats.get("mae_winsor") is not None:
        return float(stats["mae_winsor"])
    return stats.get("mae")


def _sqc_ok() -> Dict[str, Any]:
    try:
        from .distill import last_sqc_loop

        loop = last_sqc_loop()
        if not loop:
            return {"present": False, "quality_sufficient": False}
        return {
            "present": True,
            "quality_sufficient": bool(
                loop.get("quality_sufficient") or loop.get("decision") == "accept_batch"
            ),
            "decision": loop.get("decision"),
        }
    except Exception:
        return {"present": False, "quality_sufficient": False}


def _fallback_chaos_rate() -> Optional[float]:
    """Fraction of recovery retries that failed (failure budget)."""
    try:
        from research.logstore import ResearchLog

        log = ResearchLog()
        # Include aborted (failed task after recover) — they still have retry_ok.
        rows = log.list(limit=150)
        recovered = []
        for r in rows:
            rec = r.get("recovery") or {}
            if rec.get("triggered") or "retry_ok" in rec:
                recovered.append(r)
        if not recovered:
            return None  # no data → skip check
        fails = 0
        n = 0
        for r in recovered:
            rec = r.get("recovery") or {}
            if "retry_ok" in rec:
                n += 1
                if rec.get("retry_ok") is False:
                    fails += 1
        if n == 0:
            return None
        return fails / n
    except Exception:
        return None


def evaluate_graduation(
    *,
    golden_agreement: Optional[float] = None,
    bar: Optional[Dict[str, Any]] = None,
) -> GraduationReport:
    bar = bar or load_data_bar()
    metrics = _audit_join_rate()
    mae = _horizon_mae()
    metrics["horizon_mae"] = mae
    sqc = _sqc_ok()
    metrics["sqc"] = sqc
    chaos = _fallback_chaos_rate()
    metrics["fallback_chaos_fail_rate"] = chaos
    if golden_agreement is not None:
        metrics["golden_agreement"] = golden_agreement

    checks: List[GateCheck] = []

    def add(name: str, ok: bool, observed: Any, threshold: Any, detail: str = "") -> None:
        checks.append(GateCheck(name, ok, observed, threshold, detail))

    add(
        "shadow_volume",
        metrics["n_shadow"] >= int(bar["min_shadow_n"]),
        metrics["n_shadow"],
        bar["min_shadow_n"],
        "min shadow dual-log rows",
    )
    add(
        "join_rate",
        metrics["join_rate"] >= float(bar["min_join_rate"]),
        round(metrics["join_rate"], 4),
        bar["min_join_rate"],
        "shadow rows joined to completed audits",
    )
    # mode agree: only strict when alternate shadow policies exist;
    # mirror always ~1.0 — still record
    agree = metrics.get("mode_agree_frac")
    if agree is None:
        add("mode_agree", False, None, bar["min_mode_agree_frac"], "no shadow data")
    else:
        add(
            "mode_agree",
            agree >= float(bar["min_mode_agree_frac"]),
            round(agree, 4),
            bar["min_mode_agree_frac"],
            "served vs shadow mode (mirror should be ~1.0)",
        )

    if golden_agreement is not None:
        add(
            "golden_agreement",
            golden_agreement >= float(bar["min_golden_agreement"]),
            round(golden_agreement, 4),
            bar["min_golden_agreement"],
            "frozen router_v1 exact mode match",
        )
    else:
        add(
            "golden_agreement",
            False,
            None,
            bar["min_golden_agreement"],
            "run lab tokens eval --suite router_v1 first",
        )

    if bar.get("max_horizon_mae") is not None:
        thr = float(bar["max_horizon_mae"])
        if mae is None:
            add("horizon_mae", False, None, thr, "no completed audits with actuals")
        else:
            add("horizon_mae", mae <= thr, round(mae, 2), thr, "calibration under shift")

    if bar.get("require_sqc_accept"):
        add(
            "sqc_accept",
            bool(sqc.get("quality_sufficient")),
            sqc.get("decision") or sqc,
            "quality_sufficient",
            "Loop 3 before online learning",
        )

    if chaos is not None:
        thr = float(bar["max_fallback_chaos_fail_rate"])
        add(
            "fallback_chaos_budget",
            chaos <= thr,
            round(chaos, 4),
            thr,
            "LEAD recover failure budget",
        )
    else:
        add(
            "fallback_chaos_budget",
            True,
            None,
            bar["max_fallback_chaos_fail_rate"],
            "no recover samples yet — skipped (run chaos sample)",
        )

    # Canary readiness: shadow+join+golden (if present) without requiring online
    canary_names = {"shadow_volume", "join_rate", "golden_agreement"}
    canary_ok = all(
        c.ok for c in checks if c.name in canary_names and c.observed is not None
    )
    # if golden missing, not canary ready
    gold = next((c for c in checks if c.name == "golden_agreement"), None)
    if gold and gold.observed is None:
        canary_ok = False

    # Online readiness: all hard checks
    skip_if_none = {"fallback_chaos_budget"}  # already ok when skipped
    online_ok = all(c.ok for c in checks)

    drop = [
        "Do NOT train heavy local heads until ready_for_online",
        "Do NOT serve bandit / alternate policy without canary + rollback plan",
        "Do NOT treat single-price λ as a blind rule — calibrate under session locks + budgets",
        "Observation precedes influence (shadow-first)",
    ]

    return GraduationReport(
        ready_for_online=online_ok,
        ready_for_canary=canary_ok,
        checks=checks,
        metrics=metrics,
        bar=bar,
        drop_rules=drop,
    )


# --- Canary registry (guarded promotion) ---

def canary_path() -> Path:
    return _lab_data() / "canary_state.json"


def load_canary() -> Dict[str, Any]:
    p = canary_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "status": "none",  # none | proposed | canary | promoted | rolled_back
        "policy_id": None,
        "baseline_policy_id": "heuristic_v1",
        "traffic_frac": 0.0,
        "started_ts": None,
        "metrics_at_start": {},
        "notes": "",
    }


def save_canary(state: Dict[str, Any]) -> Path:
    root = _lab_data()
    root.mkdir(parents=True, exist_ok=True)
    p = canary_path()
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return p


def canary_propose(policy_id: str, *, notes: str = "") -> Dict[str, Any]:
    st = load_canary()
    st.update(
        {
            "status": "proposed",
            "policy_id": policy_id,
            "traffic_frac": 0.0,
            "started_ts": None,
            "notes": notes,
            "updated_ts": time.time(),
        }
    )
    save_canary(st)
    return st


def canary_start(
    *,
    traffic_frac: float = 0.05,
    force: bool = False,
    golden_agreement: Optional[float] = None,
) -> Dict[str, Any]:
    """Start canary only if graduation ready_for_canary (unless force)."""
    bar = load_data_bar()
    max_frac = float(bar.get("canary_max_traffic_frac", 0.10))
    traffic_frac = min(max(0.0, traffic_frac), max_frac)
    report = evaluate_graduation(golden_agreement=golden_agreement, bar=bar)
    if not force and not report.ready_for_canary:
        return {
            "ok": False,
            "error": "not ready_for_canary — see checks",
            "report": report.to_dict(),
        }
    st = load_canary()
    if not st.get("policy_id"):
        return {"ok": False, "error": "no policy proposed — canary propose first"}
    st.update(
        {
            "status": "canary",
            "traffic_frac": traffic_frac,
            "started_ts": time.time(),
            "metrics_at_start": report.metrics,
            "updated_ts": time.time(),
            "serve_enabled": False,  # lab default: log-only until explicit promote+serve
            "note_serve": "traffic_frac is advisory; set serve_enabled only after promote",
        }
    )
    save_canary(st)
    return {"ok": True, "state": st, "report": report.to_dict()}


def canary_rollback(*, reason: str = "") -> Dict[str, Any]:
    st = load_canary()
    st.update(
        {
            "status": "rolled_back",
            "traffic_frac": 0.0,
            "serve_enabled": False,
            "rollback_reason": reason,
            "rollback_ts": time.time(),
            "updated_ts": time.time(),
        }
    )
    save_canary(st)
    return st


def canary_promote(*, force: bool = False) -> Dict[str, Any]:
    """Promote candidate to baseline only after online-ready or force."""
    report = evaluate_graduation()
    if not force and not report.ready_for_online:
        return {
            "ok": False,
            "error": "not ready_for_online — keep canary or rollback",
            "report": report.to_dict(),
        }
    st = load_canary()
    if st.get("status") not in ("canary", "proposed"):
        return {"ok": False, "error": f"bad status {st.get('status')}"}
    st.update(
        {
            "status": "promoted",
            "baseline_policy_id": st.get("policy_id"),
            "traffic_frac": 1.0,
            "serve_enabled": False,  # still no auto-serve bandit without explicit flag
            "promoted_ts": time.time(),
            "updated_ts": time.time(),
        }
    )
    save_canary(st)
    return {"ok": True, "state": st, "report": report.to_dict()}

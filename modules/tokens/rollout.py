"""
Four-stage progressive delivery for routing policies:

  shadow → canary (1–5%) → percentage ramp (10/25/50) → full

Canary only after shadow similarity + frozen eval gates.
Promotion requires a full window pack, not a snapshot.
One-switch rollback + drill.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .eval_router import eval_frozen
from .gates import evaluate_graduation, load_data_bar
from .shadow import ShadowStore


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


DEFAULT_ROLLOUT_BAR: Dict[str, Any] = {
    "canary_start_frac": 0.01,
    "canary_max_frac": 0.05,
    "ramp_steps": [0.10, 0.25, 0.50],
    "window_hours_canary": 24.0,
    "window_hours_ramp_step": 12.0,
    "window_hours_full": 48.0,
    # For local lab: allow shorter windows when GROK_ROLLOUT_FAST=1
    "fast_window_hours": 0.001,  # ~3.6s — tests only
    "p95_latency_max_ratio": 1.15,
    "cost_per_success_max_ratio": 1.0,
    "task_success_min_delta": -0.02,
    "human_interrupt_max_delta": 0.02,
    "hard_safety_max": 0,
    "require_frozen_eval": True,
    "require_shadow_similarity": True,
    "shadow_mode_agree_min": 0.85,
    "min_window_samples": 3,  # lab-scale; prod would be higher
}


def load_rollout_bar() -> Dict[str, Any]:
    bar = dict(DEFAULT_ROLLOUT_BAR)
    path = _lab_data() / "rollout_bar.json"
    if path.is_file():
        try:
            bar.update(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    if os.environ.get("GROK_ROLLOUT_FAST") == "1":
        bar["window_hours_canary"] = bar["fast_window_hours"]
        bar["window_hours_ramp_step"] = bar["fast_window_hours"]
        bar["window_hours_full"] = bar["fast_window_hours"]
        bar["min_window_samples"] = 1
    return bar


def rollout_path() -> Path:
    return _lab_data() / "rollout_state.json"


def default_state() -> Dict[str, Any]:
    return {
        "stage": "none",  # none|proposed|shadow_ok|canary|ramp|full|rolled_back
        "policy_id": None,
        "baseline_policy_id": "heuristic_v1",
        "traffic_frac": 0.0,
        "ramp_index": -1,  # index into ramp_steps when stage=ramp
        "serve_enabled": False,
        "auto_rollback_armed": False,
        "stage_entered_ts": None,
        "window_started_ts": None,
        "history": [],
        "last_check": None,
        "notes": "",
        "sticky_salt": "lab",
    }


def load_state() -> Dict[str, Any]:
    p = rollout_path()
    if p.is_file():
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
            base = default_state()
            base.update(st)
            return base
        except (json.JSONDecodeError, OSError):
            pass
    return default_state()


def save_state(st: Dict[str, Any]) -> Path:
    root = _lab_data()
    root.mkdir(parents=True, exist_ok=True)
    st["updated_ts"] = time.time()
    path = rollout_path()
    path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    # keep canary_state.json in sync for older CLI
    try:
        from .gates import save_canary

        save_canary(
            {
                "status": st.get("stage"),
                "policy_id": st.get("policy_id"),
                "baseline_policy_id": st.get("baseline_policy_id"),
                "traffic_frac": st.get("traffic_frac"),
                "started_ts": st.get("stage_entered_ts"),
                "serve_enabled": st.get("serve_enabled"),
                "notes": st.get("notes") or "",
                "updated_ts": st.get("updated_ts"),
            }
        )
    except Exception:
        pass
    return path


def _hist(st: Dict[str, Any], event: str, **kw: Any) -> None:
    h = list(st.get("history") or [])
    h.append({"ts": time.time(), "event": event, **kw})
    st["history"] = h[-100:]


def sticky_in_cohort(
    key: str,
    traffic_frac: float,
    *,
    salt: str = "lab",
) -> bool:
    """Sticky cohort: same key always same side for a given frac/salt."""
    if traffic_frac <= 0:
        return False
    if traffic_frac >= 1.0:
        return True
    digest = hashlib.sha256(f"{salt}:{key}".encode("utf-8")).hexdigest()
    # first 8 hex → 0..1
    u = int(digest[:8], 16) / 0xFFFFFFFF
    return u < traffic_frac


def cohort_key(
    session_id: str = "",
    tenant: str = "",
    task: str = "",
) -> str:
    session_id = session_id or os.environ.get("GROK_SESSION_ID", "")
    tenant = tenant or os.environ.get("GROK_TENANT", "local")
    if session_id:
        return f"{tenant}:{session_id}"
    # fallback: hash task prefix for stickiness within similar goals
    return f"{tenant}:{(task or '')[:80]}"


def shadow_compare(limit: int = 100) -> Dict[str, Any]:
    """Stage-1 similarity: candidate (shadow) vs baseline (served)."""
    rows = ShadowStore().recent(limit=limit)
    n = len(rows)
    if not n:
        return {
            "n": 0,
            "mode_agree_frac": None,
            "similar_enough": False,
            "detail": "no shadow rows",
        }
    agree = sum(1 for r in rows if r.get("served_mode") == r.get("shadow_mode"))
    # budget delta when both present
    budget_deltas = []
    for r in rows:
        sb = r.get("served_budget")
        sh = r.get("shadow_budget")
        if sb is not None and sh is not None:
            budget_deltas.append(abs(float(sb) - float(sh)))
    avg_budget_delta = (
        sum(budget_deltas) / len(budget_deltas) if budget_deltas else None
    )
    agree_frac = agree / n
    bar = load_rollout_bar()
    thr = float(bar["shadow_mode_agree_min"])
    similar = agree_frac >= thr
    return {
        "n": n,
        "mode_agree_frac": agree_frac,
        "avg_abs_budget_delta": avg_budget_delta,
        "threshold_mode_agree": thr,
        "similar_enough": similar,
        "detail": "route decision agreement on dual-log",
    }


def _window_hours_for_stage(stage: str, bar: Dict[str, Any]) -> float:
    if stage == "canary":
        return float(bar["window_hours_canary"])
    if stage == "ramp":
        return float(bar["window_hours_ramp_step"])
    if stage == "full":
        return float(bar["window_hours_full"])
    return 0.0


def collect_window_metrics() -> Dict[str, Any]:
    """Lab proxies for promotion pack from research KPI + audits."""
    metrics: Dict[str, Any] = {
        "task_success_rate": None,
        "human_interrupt_avg": None,
        "p95_latency_s": None,
        "cost_per_success": None,  # tokens per success
        "hard_safety_violations": 0,
        "n_samples": 0,
        "validate_fail_rate": None,
    }
    try:
        from research.logstore import ResearchLog

        log = ResearchLog()
        kpi = log.kpi()
        metrics["task_success_rate"] = kpi.get("accepted_patch_rate")
        metrics["human_interrupt_avg"] = kpi.get("human_interruptions_avg")
        metrics["cost_per_success"] = kpi.get("average_tokens_per_success")
        lat = kpi.get("latency_per_completed_task_s")
        # use mean as stand-in when p95 unavailable
        metrics["p95_latency_s"] = lat
        metrics["n_samples"] = int(kpi.get("n_completed_logs") or 0)
        rows = log.list(limit=50, status="completed")
        val_fails = 0
        val_n = 0
        for r in rows:
            v = r.get("validation") or {}
            if v.get("tests_passed") is not None:
                val_n += 1
                if not v.get("tests_passed"):
                    val_fails += 1
            # safety: notes containing policy violation markers
            notes = str((r.get("outcome") or {}).get("notes") or "")
            if "POLICY_VIOLATION" in notes or "SAFETY_VIOLATION" in notes:
                metrics["hard_safety_violations"] = (
                    metrics["hard_safety_violations"] or 0
                ) + 1
        if val_n:
            metrics["validate_fail_rate"] = val_fails / val_n
    except Exception as e:
        metrics["error"] = str(e)
    return metrics


def _baseline_snapshot(st: Dict[str, Any]) -> Dict[str, Any]:
    return st.get("baseline_metrics") or {}


def evaluate_window_pack(
    st: Optional[Dict[str, Any]] = None,
    *,
    bar: Optional[Dict[str, Any]] = None,
    force_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full window promotion pack. Returns ok + hard_stops + checks.
    Hard stop → should rollback.
    """
    st = st or load_state()
    bar = bar or load_rollout_bar()
    cur = force_metrics or collect_window_metrics()
    base = _baseline_snapshot(st)
    # if no baseline yet, use current as baseline (first check after start)
    if not base:
        base = dict(cur)
        # don't persist here; start/advance will

    checks: List[Dict[str, Any]] = []
    hard_stops: List[str] = []

    def chk(name: str, ok: bool, observed: Any, threshold: Any, hard: bool = False) -> None:
        checks.append(
            {"name": name, "ok": ok, "observed": observed, "threshold": threshold, "hard": hard}
        )
        if hard and not ok:
            hard_stops.append(name)

    # hard safety
    viol = int(cur.get("hard_safety_violations") or 0)
    chk(
        "hard_safety",
        viol <= int(bar["hard_safety_max"]),
        viol,
        bar["hard_safety_max"],
        hard=True,
    )

    # task success
    ts = cur.get("task_success_rate")
    ts_b = base.get("task_success_rate")
    if ts is not None and ts_b is not None:
        thr = float(ts_b) + float(bar["task_success_min_delta"])
        chk("task_success", ts >= thr, ts, thr, hard=True)
    else:
        chk("task_success", True, ts, "n/a baseline", hard=False)

    # human interrupt
    hi = cur.get("human_interrupt_avg")
    hi_b = base.get("human_interrupt_avg")
    if hi is not None and hi_b is not None:
        thr = float(hi_b) + float(bar["human_interrupt_max_delta"])
        chk("human_interrupt", hi <= thr, hi, thr, hard=True)
    else:
        chk("human_interrupt", True, hi, "n/a", hard=False)

    # latency p95 proxy
    lat = cur.get("p95_latency_s")
    lat_b = base.get("p95_latency_s")
    if lat is not None and lat_b is not None and float(lat_b) > 0:
        thr = float(lat_b) * float(bar["p95_latency_max_ratio"])
        chk("p95_latency", float(lat) <= thr, lat, thr, hard=True)
    else:
        chk("p95_latency", True, lat, "n/a", hard=False)

    # cost per success (tokens) — not worse
    cps = cur.get("cost_per_success")
    cps_b = base.get("cost_per_success")
    if cps is not None and cps_b is not None and float(cps_b) > 0:
        thr = float(cps_b) * float(bar["cost_per_success_max_ratio"])
        chk("cost_per_success", float(cps) <= thr * 1.0001, cps, thr, hard=True)
    else:
        chk("cost_per_success", True, cps, "n/a", hard=False)

    # tool/validate regression
    vf = cur.get("validate_fail_rate")
    vf_b = base.get("validate_fail_rate")
    if vf is not None and vf_b is not None:
        thr = float(vf_b) + 0.05
        chk("validate_fail_rate", vf <= thr, vf, thr, hard=True)
    else:
        chk("validate_fail_rate", True, vf, "n/a", hard=False)

    # frozen eval still healthy
    frozen = eval_frozen()
    if bar.get("require_frozen_eval"):
        agr = frozen.get("agreement")
        deep_v = int(frozen.get("deep_violations") or 0)
        chk(
            "frozen_eval",
            agr is not None and agr >= 0.7 and deep_v == 0,
            {"agreement": agr, "deep_violations": deep_v},
            "agreement>=0.7 & deep_violations==0",
            hard=True,
        )

    # window time + samples
    stage = st.get("stage") or "none"
    need_h = _window_hours_for_stage(stage, bar)
    entered = st.get("window_started_ts") or st.get("stage_entered_ts")
    elapsed_h = 0.0
    if entered:
        elapsed_h = (time.time() - float(entered)) / 3600.0
    window_time_ok = elapsed_h >= need_h if stage in ("canary", "ramp", "full") else True
    samples = int(cur.get("n_samples") or 0)
    min_s = int(bar["min_window_samples"])
    samples_ok = samples >= min_s if stage in ("canary", "ramp", "full") else True
    chk("window_duration", window_time_ok, round(elapsed_h, 4), need_h, hard=False)
    chk("window_samples", samples_ok, samples, min_s, hard=False)

    pack_ok = all(c["ok"] for c in checks if c.get("hard")) and window_time_ok and samples_ok
    # soft checks that are hard for advance
    advance_ok = pack_ok and all(
        c["ok"] for c in checks if c["name"] in ("window_duration", "window_samples")
    )

    return {
        "ok": advance_ok,
        "hard_stops": hard_stops,
        "should_rollback": bool(hard_stops),
        "checks": checks,
        "metrics": cur,
        "baseline_metrics": base,
        "stage": stage,
        "elapsed_hours": elapsed_h,
        "required_hours": need_h,
    }


def propose(policy_id: str, *, notes: str = "") -> Dict[str, Any]:
    st = load_state()
    st["stage"] = "proposed"
    st["policy_id"] = policy_id
    st["traffic_frac"] = 0.0
    st["serve_enabled"] = False
    st["notes"] = notes
    st["ramp_index"] = -1
    st["auto_rollback_armed"] = False
    _hist(st, "propose", policy_id=policy_id)
    save_state(st)
    return st


def mark_shadow_ok(*, force: bool = False) -> Dict[str, Any]:
    """Transition proposed → shadow_ok after similarity + gates."""
    st = load_state()
    bar = load_rollout_bar()
    sim = shadow_compare()
    frozen = eval_frozen()
    grad = evaluate_graduation(golden_agreement=frozen.get("agreement"))
    reasons = []
    if bar.get("require_shadow_similarity") and not sim.get("similar_enough"):
        reasons.append(f"shadow not similar: {sim}")
    if bar.get("require_frozen_eval"):
        agr = frozen.get("agreement")
        if agr is None or agr < float(load_data_bar().get("min_golden_agreement", 0.8)):
            reasons.append(f"frozen eval weak agreement={agr}")
    # soft: graduation ready_for_canary preferred
    if not force and not grad.ready_for_canary and not reasons:
        # still allow shadow_ok if similarity+frozen ok even if volume low? Plan says canary needs both.
        # mark shadow_ok only on similarity+frozen; canary start still needs gates
        pass
    if reasons and not force:
        return {"ok": False, "error": "shadow_ok blocked", "reasons": reasons, "sim": sim}
    st["stage"] = "shadow_ok"
    st["shadow_compare"] = sim
    st["stage_entered_ts"] = time.time()
    _hist(st, "shadow_ok", sim=sim)
    save_state(st)
    return {"ok": True, "state": st, "sim": sim}


def start_canary(
    *,
    frac: Optional[float] = None,
    force: bool = False,
    serve: bool = False,
) -> Dict[str, Any]:
    """Enter canary 1–5% only after shadow_ok + graduation ready_for_canary."""
    st = load_state()
    bar = load_rollout_bar()
    if not st.get("policy_id"):
        return {"ok": False, "error": "propose a policy_id first"}
    # ensure shadow_ok
    if st.get("stage") not in ("shadow_ok", "canary") and not force:
        # try auto shadow_ok
        r = mark_shadow_ok(force=force)
        if not r.get("ok"):
            return {
                "ok": False,
                "error": "canary requires shadow_ok (similarity + frozen eval)",
                "shadow": r,
            }
        st = load_state()
    frozen = eval_frozen()
    grad = evaluate_graduation(golden_agreement=frozen.get("agreement"))
    if not force and not grad.ready_for_canary:
        return {
            "ok": False,
            "error": "not ready_for_canary — see lab tokens gates",
            "report": grad.to_dict(),
        }
    sim = shadow_compare()
    if not force and bar.get("require_shadow_similarity") and not sim.get("similar_enough"):
        return {"ok": False, "error": "shadow similarity failed", "sim": sim}

    frac = frac if frac is not None else float(bar["canary_start_frac"])
    frac = min(max(frac, 0.0), float(bar["canary_max_frac"]))
    # safer default 1%
    if frac > float(bar["canary_max_frac"]):
        frac = float(bar["canary_max_frac"])

    metrics = collect_window_metrics()
    st["stage"] = "canary"
    st["traffic_frac"] = frac
    st["ramp_index"] = -1
    st["serve_enabled"] = bool(serve)
    st["auto_rollback_armed"] = True
    st["stage_entered_ts"] = time.time()
    st["window_started_ts"] = time.time()
    st["baseline_metrics"] = metrics
    st["shadow_compare"] = sim
    _hist(st, "canary_start", frac=frac, serve=serve)
    save_state(st)
    return {"ok": True, "state": st, "graduation": grad.to_dict()}


def check_and_maybe_rollback(
    *,
    force_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    st = load_state()
    pack = evaluate_window_pack(st, force_metrics=force_metrics)
    st["last_check"] = pack
    if pack.get("should_rollback") and st.get("stage") in ("canary", "ramp", "full"):
        st = _do_rollback(st, reason="hard_stop:" + ",".join(pack.get("hard_stops") or []))
        save_state(st)
        return {"ok": False, "rolled_back": True, "pack": pack, "state": st}
    save_state(st)
    return {"ok": pack.get("ok"), "rolled_back": False, "pack": pack, "state": st}


def advance(*, force: bool = False) -> Dict[str, Any]:
    """
    Advance along: canary 1%→5% → ramp 10→25→50 → full.
    Requires green window pack unless force.
    """
    st = load_state()
    bar = load_rollout_bar()
    stage = st.get("stage")
    if stage not in ("canary", "ramp", "full", "shadow_ok"):
        return {"ok": False, "error": f"cannot advance from stage={stage}"}

    if stage == "shadow_ok":
        return start_canary(force=force)

    pack = evaluate_window_pack(st)
    if not force and not pack.get("ok"):
        if pack.get("should_rollback"):
            st = _do_rollback(st, reason="hard_stop_on_advance")
            save_state(st)
            return {"ok": False, "rolled_back": True, "pack": pack, "state": st}
        return {"ok": False, "error": "window pack not green", "pack": pack}

    steps = list(bar["ramp_steps"])
    frac = float(st.get("traffic_frac") or 0)
    canary_max = float(bar["canary_max_frac"])

    if stage == "canary":
        if frac + 1e-9 < canary_max:
            # bump within canary toward max (e.g. 1% → 5%)
            new_frac = min(canary_max, max(frac * 2, canary_max))  # jump to max after clean window
            # gentler: go to canary_max only
            new_frac = canary_max
            st["traffic_frac"] = new_frac
            st["window_started_ts"] = time.time()
            _hist(st, "canary_bump", frac=new_frac)
            save_state(st)
            return {"ok": True, "state": st, "action": "canary_bump", "pack": pack}
        # leave canary → first ramp step
        st["stage"] = "ramp"
        st["ramp_index"] = 0
        st["traffic_frac"] = float(steps[0])
        st["window_started_ts"] = time.time()
        st["stage_entered_ts"] = time.time()
        _hist(st, "enter_ramp", frac=st["traffic_frac"])
        save_state(st)
        return {"ok": True, "state": st, "action": "enter_ramp", "pack": pack}

    if stage == "ramp":
        idx = int(st.get("ramp_index") or 0)
        if idx + 1 < len(steps):
            st["ramp_index"] = idx + 1
            st["traffic_frac"] = float(steps[idx + 1])
            st["window_started_ts"] = time.time()
            _hist(st, "ramp_step", frac=st["traffic_frac"], index=st["ramp_index"])
            save_state(st)
            return {"ok": True, "state": st, "action": "ramp_step", "pack": pack}
        # → full
        st["stage"] = "full"
        st["traffic_frac"] = 1.0
        st["auto_rollback_armed"] = True
        st["window_started_ts"] = time.time()
        st["stage_entered_ts"] = time.time()
        _hist(st, "full", frac=1.0)
        save_state(st)
        return {"ok": True, "state": st, "action": "full", "pack": pack}

    if stage == "full":
        return {
            "ok": True,
            "state": st,
            "action": "already_full",
            "pack": pack,
            "note": "hold under auto_rollback_armed; retire baseline after window",
        }

    return {"ok": False, "error": "unreachable"}


def _do_rollback(st: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    st["stage"] = "rolled_back"
    st["traffic_frac"] = 0.0
    st["serve_enabled"] = False
    st["auto_rollback_armed"] = False
    st["ramp_index"] = -1
    st["rollback_reason"] = reason
    st["rollback_ts"] = time.time()
    # restore baseline as active policy identity
    st["policy_id"] = st.get("baseline_policy_id") or "heuristic_v1"
    _hist(st, "rollback", reason=reason)
    return st


def rollback(reason: str = "") -> Dict[str, Any]:
    st = load_state()
    st = _do_rollback(st, reason=reason)
    save_state(st)
    return st


def drill() -> Dict[str, Any]:
    """Test one-switch rollback path without requiring active canary metrics."""
    st = load_state()
    prev = {
        "stage": st.get("stage"),
        "traffic_frac": st.get("traffic_frac"),
        "policy_id": st.get("policy_id"),
    }
    # simulate canary then rollback
    st["stage"] = "canary"
    st["traffic_frac"] = 0.01
    st["auto_rollback_armed"] = True
    st = _do_rollback(st, reason="drill")
    st["drill_prev"] = prev
    st["drill_ok"] = (
        st.get("traffic_frac") == 0.0 and st.get("stage") == "rolled_back"
    )
    _hist(st, "drill", prev=prev, ok=st["drill_ok"])
    save_state(st)
    return {"ok": st["drill_ok"], "state": st, "prev": prev}


def status() -> Dict[str, Any]:
    st = load_state()
    bar = load_rollout_bar()
    sim = shadow_compare()
    return {
        "state": st,
        "bar": {
            k: bar[k]
            for k in (
                "canary_start_frac",
                "canary_max_frac",
                "ramp_steps",
                "p95_latency_max_ratio",
                "window_hours_canary",
            )
            if k in bar
        },
        "shadow_compare": sim,
        "stages": ["shadow", "canary", "ramp", "full"],
        "honesty": (
            "traffic_frac assigns sticky local cohorts for measurement; "
            "serve_enabled defaults false on single-user lab"
        ),
    }

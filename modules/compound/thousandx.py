"""
Live 1000× system scorecard — durable operator metric, not marketing.

M_total ≈ waste_kill × context × recovery × eval × body × reuse
See docs/1000X-SYSTEM.md.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _savings_ratio() -> Optional[float]:
    best: Optional[float] = None
    for pack in ("aggressive", "balanced"):
        try:
            prev = os.environ.get("GROK_TOKEN_PACK")
            os.environ["GROK_TOKEN_PACK"] = pack
            from tokens.savings import run_suite

            r = run_suite()
            val = r.get("total_ratio")
            if val is None and r.get("total_ratio_inf"):
                val = 999.0
            if val is not None:
                f = float(val)
                if best is None or f > best:
                    best = f
            if prev is None:
                os.environ.pop("GROK_TOKEN_PACK", None)
            else:
                os.environ["GROK_TOKEN_PACK"] = prev
        except Exception:
            try:
                if prev is None:  # type: ignore[name-defined]
                    os.environ.pop("GROK_TOKEN_PACK", None)
            except Exception:
                pass
    return best


def _body_signals() -> Dict[str, Any]:
    try:
        from body.kpis import waste_report
        from body.outcomes import all_scorecards

        waste = waste_report()
        cards = all_scorecards()
        grades = [c.get("grade") for c in cards if c.get("grade")]
        avg_score = None
        if cards:
            scores = [_safe_float(c.get("score")) for c in cards]
            avg_score = sum(scores) / len(scores) if scores else None
        totals = waste.get("totals") or {}
        return {
            "n_bodies": len(cards),
            "avg_outcome_score": avg_score,
            "grades": grades,
            "deep_waste_ops": int(totals.get("deep_waste_ops") or 0),
            "mode_totals": {
                "deep": int(totals.get("deep") or 0),
                "local": int(totals.get("local") or 0),
                "short": int(totals.get("short") or 0),
            },
            "recommendations": list(waste.get("recommendations") or []),
        }
    except Exception as e:
        return {"error": str(e), "n_bodies": 0}


def _recovery_signal() -> Dict[str, Any]:
    try:
        from research.logstore import ResearchLog

        rows = ResearchLog().list(limit=80)
        recovered = 0
        retry_ok = 0
        retry_n = 0
        for r in rows:
            rec = r.get("recovery") or {}
            if rec.get("triggered") or "retry_ok" in rec:
                recovered += 1
            if "retry_ok" in rec:
                retry_n += 1
                if rec.get("retry_ok") is True:
                    retry_ok += 1
        rate = (retry_ok / retry_n) if retry_n else None
        return {"recovered_tasks": recovered, "retry_n": retry_n, "retry_ok_rate": rate}
    except Exception as e:
        return {"error": str(e)}


def _gate_signal() -> Dict[str, Any]:
    try:
        from tokens.gates import evaluate_graduation, load_data_bar
        from tokens.eval_router import eval_frozen

        frozen = eval_frozen()
        rep = evaluate_graduation(
            golden_agreement=frozen.get("agreement"),
            bar=load_data_bar(),
        )
        d = rep.to_dict() if hasattr(rep, "to_dict") else dict(rep)
        return {
            "ready_for_canary": d.get("ready_for_canary"),
            "ready_for_online": d.get("ready_for_online"),
            "golden": frozen.get("agreement"),
        }
    except Exception as e:
        return {"error": str(e)}


def estimate_lever_mults(
    *,
    compound_product: float,
    savings_ratio: Optional[float],
    body: Dict[str, Any],
    recovery: Dict[str, Any],
    gates: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Map live signals → six doctrine levers (heuristic, offline, Mac-honest).
    Mults are deliberately conservative; product is a scorecard, not a press claim.
    """
    # 1 waste kill — suite ratio + deep_waste_ops
    waste_mult = 1.0
    suite = savings_ratio or 0.0
    if suite >= 80:
        waste_mult = 25.0
    elif suite >= 50:
        waste_mult = 15.0
    elif suite >= 20:
        waste_mult = 8.0
    elif suite >= 5:
        waste_mult = 3.0
    if int(body.get("deep_waste_ops") or 0) > 0:
        waste_mult *= 0.7

    # 2 context — proxy: compound product high + golden agreement
    context_mult = 1.0
    if compound_product >= 40:
        context_mult = 2.5
    elif compound_product >= 20:
        context_mult = 2.0
    elif compound_product >= 10:
        context_mult = 1.5
    gold = gates.get("golden")
    if gold is not None and float(gold) >= 0.9:
        context_mult *= 1.2

    # 3 recovery
    recovery_mult = 1.0
    rr = recovery.get("retry_ok_rate")
    if rr is not None:
        if rr >= 0.85:
            recovery_mult = 2.2
        elif rr >= 0.7:
            recovery_mult = 1.8
        elif rr >= 0.5:
            recovery_mult = 1.4
    elif int(recovery.get("recovered_tasks") or 0) > 0:
        recovery_mult = 1.3

    # 4 eval
    eval_mult = 1.0
    if gates.get("ready_for_canary") and gates.get("ready_for_online"):
        eval_mult = 1.8
    elif gates.get("ready_for_canary"):
        eval_mult = 1.4

    # 5 body autonomy — outcome scores + body count
    body_mult = 1.0
    n = int(body.get("n_bodies") or 0)
    avg = body.get("avg_outcome_score")
    if n >= 3 and avg is not None:
        if avg >= 85:
            body_mult = 4.0
        elif avg >= 70:
            body_mult = 2.5
        elif avg >= 55:
            body_mult = 1.8
        else:
            body_mult = 1.2
    elif n >= 1:
        body_mult = 1.3

    # 6 reuse — soft: compound factory+body unlocks proxy via product floor
    reuse_mult = 1.0
    if compound_product >= 50:
        reuse_mult = 2.0
    elif compound_product >= 30:
        reuse_mult = 1.5
    elif compound_product >= 15:
        reuse_mult = 1.2

    return {
        "waste_kill": {
            "mult": round(waste_mult, 2),
            "why": "savings suite + deep_waste_ops",
            "suite_ratio": savings_ratio,
        },
        "context": {
            "mult": round(context_mult, 2),
            "why": "compound plane + golden proxy for context discipline",
        },
        "recovery": {
            "mult": round(recovery_mult, 2),
            "why": "LEAD retry_ok_rate / recovered tasks",
            "retry_ok_rate": rr,
        },
        "eval": {
            "mult": round(eval_mult, 2),
            "why": "graduation bars ready_for_canary/online",
        },
        "body": {
            "mult": round(body_mult, 2),
            "why": "outcome scorecards + body registry density",
            "avg_outcome_score": avg,
        },
        "reuse": {
            "mult": round(reuse_mult, 2),
            "why": "compound maturity proxy (skills/memory/proofs over time)",
        },
    }


def evaluate_1000x(*, compound: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Full scorecard for lab compound 1000x."""
    if compound is None:
        from compound.engine import evaluate_rounds

        compound = evaluate_rounds()

    product = _safe_float(compound.get("product"), 1.0)
    savings = _savings_ratio()
    body = _body_signals()
    recovery = _recovery_signal()
    gates = _gate_signal()
    levers = estimate_lever_mults(
        compound_product=product,
        savings_ratio=savings,
        body=body,
        recovery=recovery,
        gates=gates,
    )

    system_product = 1.0
    for v in levers.values():
        system_product *= float(v.get("mult") or 1.0)

    # Path remaining toward 1000
    target = 1000.0
    gap = target / system_product if system_product > 0 else target
    tier = "seed"
    if system_product >= 1000:
        tier = "1000x_claimed_heuristic"
    elif system_product >= 300:
        tier = "approaching"
    elif system_product >= 100:
        tier = "hundreds"
    elif system_product >= 30:
        tier = "compound_operating"
    else:
        tier = "early"

    blockers: List[str] = []
    if _safe_float(savings) < 50:
        blockers.append("raise savings suite (waste kill) via ops→local + aggressive pack habit")
    if int(body.get("deep_waste_ops") or 0) > 0:
        blockers.append("kill deep-on-ops routes (lab body kpi --waste)")
    if body.get("avg_outcome_score") is not None and float(body["avg_outcome_score"]) < 80:
        blockers.append("raise body outcome scores (factory green + close obligations)")
    if recovery.get("retry_ok_rate") is not None and float(recovery["retry_ok_rate"]) < 0.7:
        blockers.append("improve LEAD recover success rate")
    if not gates.get("ready_for_online"):
        blockers.append("hold graduation bars (lab tokens gates)")
    if not blockers and system_product < 1000:
        blockers.append(
            "grow mind=false standing procedures + skill/memory reuse on real product work"
        )

    return {
        "doctrine": "docs/1000X-SYSTEM.md",
        "formula": "waste_kill × context × recovery × eval × body × reuse",
        "target": target,
        "system_product": round(system_product, 2),
        "gap_factor": round(gap, 2),
        "tier": tier,
        "levers": levers,
        "signals": {
            "compound_lever_product": product,
            "compound_highest_round": compound.get("highest_round"),
            "savings_suite_ratio": savings,
            "body": body,
            "recovery": recovery,
            "gates": gates,
        },
        "blockers": blockers,
        "claim_language": (
            "Heuristic offline scorecard — not a press claim. "
            "Use band language: ops ∞ / build ~50–100 / deep ~8–15; "
            "system product is product of levers on live signals."
        ),
    }

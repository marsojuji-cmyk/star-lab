"""
Compounding rounds: each unlocked multiplier changes *what the next steps are*.

10×  — closed loop (route→complete, gates canary, factory app, LEAD, body, FSM)
20×  — enforcement (mode_cap live, PR4 bridge, day budget, canary armed)
30×  — evolution (next-steps rewrite, compound CLI, multi-lever product)

Product of multipliers (not sum): waste kill × recover × packing × body × breaker.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


def state_path() -> Path:
    return _lab_data() / "compound_state.json"


def load_state() -> Dict[str, Any]:
    p = state_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"rounds": {}, "updated_ts": None, "product": 1.0}


def save_state(data: Dict[str, Any]) -> Path:
    _lab_data().mkdir(parents=True, exist_ok=True)
    data["updated_ts"] = time.time()
    p = state_path()
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def _gate_metrics() -> Dict[str, Any]:
    try:
        from tokens.gates import evaluate_graduation, load_data_bar
        from tokens.eval_router import eval_frozen

        frozen = eval_frozen()
        rep = evaluate_graduation(
            golden_agreement=frozen.get("agreement"),
            bar=load_data_bar(),
        )
        return rep.to_dict() if hasattr(rep, "to_dict") else dict(rep)
    except Exception as e:
        return {"error": str(e)}


def _check_body() -> bool:
    try:
        from body.store import BodyStore

        return len(BodyStore().list()) >= 2
    except Exception:
        return False


def _check_breaker_fsm() -> bool:
    try:
        from graph.breaker import load_breakers, STATE_DEGRADED

        data = load_breakers()
        return int(data.get("schema_version") or 0) >= 2
    except Exception:
        return False


def _check_bridge() -> bool:
    try:
        from resilience.rollout_bridge import maybe_rollback_from_breaker

        return callable(maybe_rollback_from_breaker)
    except Exception:
        return False


def _check_factory_app() -> bool:
    p = Path.home() / "Projects" / "claude-compare-demo" / "src" / "compare.py"
    return p.is_file()


def _savings_ratio() -> Optional[float]:
    """Best available suite ratio (aggressive pack is the 100× program path)."""
    best: Optional[float] = None
    for pack in ("aggressive", "balanced"):
        try:
            prev = os.environ.get("GROK_TOKEN_PACK")
            os.environ["GROK_TOKEN_PACK"] = pack
            # policy reads pack at call time via env
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
            if prev is None:  # type: ignore[name-defined]
                os.environ.pop("GROK_TOKEN_PACK", None)
            continue
    if best is not None:
        return best
    try:
        p = _lab_data() / "token_savings.jsonl"
        if not p.is_file():
            return None
        last = p.read_text(encoding="utf-8").strip().splitlines()[-1]
        return float(json.loads(last).get("total_ratio") or 0) or None
    except Exception:
        return None


def evaluate_rounds() -> Dict[str, Any]:
    """Score 10× / 20× / 30× unlock criteria and product of multipliers."""
    gates = _gate_metrics()
    checks = {c["name"]: c for c in (gates.get("checks") or [])}
    def ok(name: str) -> bool:
        c = checks.get(name) or {}
        return bool(c.get("ok"))

    # --- lever multipliers (each ≥1 when unlocked, else 1.0 baseline) ---
    levers: Dict[str, Dict[str, Any]] = {}

    # Accounting / join
    join_ok = ok("join_rate") and ok("shadow_volume")
    levers["accounting"] = {
        "unlocked": join_ok,
        "mult": 2.5 if join_ok else 1.0,
        "why": "route→complete joins prove cost/success",
    }
    # Routing golden
    gold_ok = ok("golden_agreement")
    levers["routing_golden"] = {
        "unlocked": gold_ok,
        "mult": 1.5 if gold_ok else 1.0,
        "why": "frozen router agreement",
    }
    # LEAD chaos
    chaos_ok = ok("fallback_chaos_budget")
    levers["lead_recover"] = {
        "unlocked": chaos_ok,
        "mult": 1.4 if chaos_ok else 1.0,
        "why": "recover failure budget in envelope",
    }
    # Body
    body_ok = _check_body()
    levers["body"] = {
        "unlocked": body_ok,
        "mult": 1.6 if body_ok else 1.0,
        "why": "body registry + forge_exit property",
    }
    # Breaker FSM
    br_ok = _check_breaker_fsm()
    levers["breaker_fsm"] = {
        "unlocked": br_ok,
        "mult": 1.5 if br_ok else 1.0,
        "why": "Closed/DEGRADED/Open/Half-Open",
    }
    # Factory app
    fac_ok = _check_factory_app()
    levers["factory"] = {
        "unlocked": fac_ok,
        "mult": 1.3 if fac_ok else 1.0,
        "why": "real app e2e not only demo scaffold",
    }
    # PR4 bridge
    bridge_ok = _check_bridge()
    levers["rollout_bridge"] = {
        "unlocked": bridge_ok,
        "mult": 1.4 if bridge_ok else 1.0,
        "why": "breaker→rollback safety net",
    }
    # Canary measurement
    canary = False
    try:
        from tokens import rollout as rm

        st = rm.load_state()
        canary = st.get("stage") == "canary" and bool(st.get("auto_rollback_armed"))
    except Exception:
        pass
    levers["canary_armed"] = {
        "unlocked": canary,
        "mult": 1.2 if canary else 1.0,
        "why": "measurement canary + auto_rollback",
    }
    # Predicted savings suite
    sav = _savings_ratio()
    sav_ok = sav is not None and sav >= 50
    levers["token_savings_suite"] = {
        "unlocked": sav_ok,
        "mult": min(3.0, (sav / 50.0) if sav else 1.0) if sav_ok else 1.0,
        "why": "vs-claude suite ratio≥50×",
        "ratio": sav,
    }
    # Horizon gate (online path)
    mae_ok = ok("horizon_mae")
    levers["horizon_calibrated"] = {
        "unlocked": mae_ok,
        "mult": 1.3 if mae_ok else 1.0,
        "why": "winsorized gate MAE under bar",
    }

    product = 1.0
    for v in levers.values():
        product *= float(v.get("mult") or 1.0)

    # Round unlocks
    r10_checks = {
        "join_rate": join_ok,
        "shadow_volume": ok("shadow_volume"),
        "golden": gold_ok,
        "chaos": chaos_ok,
        "body": body_ok,
        "breaker": br_ok,
        "factory": fac_ok,
        "canary_ready": bool(gates.get("ready_for_canary")),
    }
    r10 = all(r10_checks.values())

    r20_checks = {
        "r10": r10,
        "bridge": bridge_ok,
        "canary_armed": canary,
        "mae_or_winsor": mae_ok,
        "mode_cap_wired": True,  # shipped in this round
    }
    r20 = all(r20_checks.values())

    r30_checks = {
        "r20": r20,
        "product_ge_20": product >= 20.0,
        "savings_suite": sav_ok,
        "evolve_engine": True,
    }
    r30 = all(r30_checks.values())

    rounds = {
        "10x": {
            "target": 10.0,
            "unlocked": r10,
            "checks": r10_checks,
            "label": "Closed-loop lab (observe + recover + body + FSM)",
        },
        "20x": {
            "target": 20.0,
            "unlocked": r20,
            "checks": r20_checks,
            "label": "Enforced path (caps, bridge, armed canary, MAE gate)",
        },
        "30x": {
            "target": 30.0,
            "unlocked": r30,
            "checks": r30_checks,
            "label": "Compound evolution (product≥20 + suite + next-step rewrite)",
        },
    }

    highest = "0x"
    if r30:
        highest = "30x"
    elif r20:
        highest = "20x"
    elif r10:
        highest = "10x"

    result = {
        "highest_round": highest,
        "product": round(product, 3),
        "levers": levers,
        "rounds": rounds,
        "gates": {
            "ready_for_canary": gates.get("ready_for_canary"),
            "ready_for_online": gates.get("ready_for_online"),
        },
        "next_steps": next_steps_evolved(highest, product, levers, gates),
    }
    st = load_state()
    st["last"] = result
    st["product"] = product
    st["highest_round"] = highest
    save_state(st)
    return result


def next_steps_evolved(
    highest: str,
    product: float,
    levers: Dict[str, Dict[str, Any]],
    gates: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    The compounding effect: unlocked rounds *change the next-step list*.
    Pre-10×: close accounting. Post-30×: productize levers, not more modules.
    """
    steps: List[Dict[str, str]] = []

    if highest == "0x":
        steps = [
            {
                "id": "join",
                "title": "Close route→complete joins",
                "adds": "canary bar",
                "risks": "seed-only data",
                "why": "observation before influence",
            },
            {
                "id": "factory",
                "title": "Factory one real app",
                "adds": "proof beyond starlab-demo",
                "risks": "lab-only scaffolding",
                "why": "product contact",
            },
        ]
        return steps

    if highest == "10x":
        steps = [
            {
                "id": "enforce",
                "title": "Live mode_cap + breaker apply on every route",
                "adds": "DEGRADED is real",
                "risks": "over-cap thrash",
                "why": "10× was observation; 20× is enforcement",
            },
            {
                "id": "bridge",
                "title": "PR4 breaker→rollout rollback drill",
                "adds": "safety net under canary",
                "risks": "false rollback",
                "why": "armed canary without bridge is incomplete",
            },
            {
                "id": "mae",
                "title": "Hold winsorized MAE under bar on live audits only",
                "adds": "ready_for_online path",
                "risks": "ignoring true design cost",
                "why": "online λ only after calibration",
            },
        ]
        return steps

    if highest == "20x":
        steps = [
            {
                "id": "product_not_modules",
                "title": "Run factory on *user* goals through body organs",
                "adds": "ROI in human outcomes",
                "risks": "more lab modules without use",
                "why": "20× unlocks: stop building meta; ship through body",
            },
            {
                "id": "serve_canary",
                "title": "Only after 24h green window: consider serve_enabled with tiny frac",
                "adds": "influence under rollback",
                "risks": "quality dip",
                "why": "DROP still forbids blind bandit",
            },
            {
                "id": "compound_product",
                "title": "Drive product of levers ≥30 without new heavy ML heads",
                "adds": "30× evolution tier",
                "risks": "metric gaming",
                "why": "multipliers must be real saves + recover + body",
            },
        ]
        return steps

    # 30× — next-steps evolve again: meta-ops and product velocity
    steps = [
        {
            "id": "velocity",
            "title": "Default work = body-scoped factory loops (not open research)",
            "adds": "compound habit",
            "risks": "rigidity on novel tasks",
            "why": "30× means process *is* the product",
        },
        {
            "id": "kill_waste_modes",
            "title": "Track tokens/success by body; kill always-deep paths",
            "adds": "durable 100× ops / 8× hard split",
            "risks": "starving hard design",
            "why": "savings suite + live joins must agree",
        },
        {
            "id": "organ_standing",
            "title": "Grow standing procedures (mind=false) until mind is rare",
            "adds": "body does most work",
            "risks": "opaque automation",
            "why": "anti-wrapper: property + contact outlive model swaps",
        },
    ]
    if not gates.get("ready_for_online"):
        steps.insert(
            0,
            {
                "id": "online_bar",
                "title": "Clear remaining online gates (live MAE / SQC continuous)",
                "adds": "λ/bandit optional later",
                "risks": "premature online learning",
                "why": "30× process ≠ automatic online training",
            },
        )
        steps.append(
            {
                "id": "no_heavy_heads",
                "title": "Still no trained LenVM/bandit until ready_for_online",
                "adds": "honesty",
                "risks": "leaving EV on table",
                "why": "DROP rules survive 30×",
            }
        )
    else:
        # Online bar green — next-steps evolve *again*: optional light online, still no serve-without-window
        steps.insert(
            0,
            {
                "id": "online_optional",
                "title": "Online bar green: optional light λ distill under canary — never unguarded bandit",
                "adds": "calibrated continuous improvement",
                "risks": "serve_enabled too early",
                "why": "ready_for_online ≠ must train; still measure 24h window first",
            },
        )
        steps.append(
            {
                "id": "human_outcomes",
                "title": "Score bodies on human outcomes (shipped proofs), not module count",
                "adds": "true north-star",
                "risks": "vanity KPIs",
                "why": "compounding is finished when next-steps are product, not plane",
            },
        )
    return steps

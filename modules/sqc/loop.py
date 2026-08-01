"""
Iterative Annotation Quality Loop (Figure 1).

  Annotate → Evaluate → Quality Sufficient?
      Yes → End / promote to distill
      No  → Apply quality-improving methods → Annotate
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .risk import prioritize_for_audit, score_item_risk
from .sampling import (
    SamplingDecision,
    single_sample,
    double_sample,
    sequential_sprt_step,
    SequentialState,
)


def _lab_data() -> Path:
    env = os.environ.get("GROK_LAB_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".grok" / "lab"


@dataclass
class LoopResult:
    loop_id: str
    decision: str  # accept_batch | reject_batch | improve | continue_sampling
    quality_sufficient: bool
    sampling: Optional[Dict[str, Any]]
    interventions: List[str]
    high_risk_ids: List[str]
    metrics: Dict[str, Any]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QualityLoop:
    """
    Loop 3 support: annotate → audit (SQC) → distill gate.

    Items are dicts with at least:
      id, text (or output), optional is_correct (bool, if audited)
    """

    def __init__(self, db_dir: Optional[Path] = None) -> None:
        self.root = db_dir or (_lab_data() / "sqc")
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(self.root), 0o700)
        except OSError:
            pass
        self.log_path = self.root / "loop_log.jsonl"

    def evaluate_batch(
        self,
        items: Sequence[Dict[str, Any]],
        *,
        plan: str = "double",
        # single
        n: int = 40,
        c: int = 2,
        # double
        n1: int = 25,
        c1: int = 0,
        c2: int = 3,
        n2: int = 25,
        # quality threshold on audited error rate
        max_error_rate: float = 0.08,
        risk_audit_fraction: float = 0.25,
    ) -> LoopResult:
        items = list(items)
        loop_id = uuid.uuid4().hex[:12]
        notes: List[str] = []

        # Risk-prioritized order (error modeling → focus audit)
        ranked = prioritize_for_audit(items)
        high_risk = [str(r.get("id", i)) for i, r in enumerate(ranked) if r["risk"]["recommend_audit"]]
        notes.append(f"high_risk_count={len(high_risk)} / {len(ranked)}")

        # Build audit outcomes: prefer explicit is_correct; else risk-proxy (not for final accept)
        audited = [r for r in ranked if "is_correct" in r and r["is_correct"] is not None]
        if audited:
            outcomes = [bool(r["is_correct"]) for r in audited]
            notes.append(f"using {len(outcomes)} human/oracle labels")
        else:
            # bootstrap: treat risk < 0.45 as provisional good (for demo only)
            outcomes = [r["risk"]["score"] < 0.45 for r in ranked]
            notes.append("no is_correct labels — using risk proxy (mark labels for real audits)")

        # Run sampling plan on outcomes (risk-ordered so early samples hit riskier items)
        if plan == "single":
            samp = single_sample(outcomes, n=n, c=c)
        elif plan == "sequential" or plan == "sprt":
            st = SequentialState()
            samp = None
            for good in outcomes:
                st, samp = sequential_sprt_step(st, good)
                if samp.decision in ("accept", "reject"):
                    break
            if samp is None:
                samp = SamplingDecision("sequential_sprt", "continue", 0, 0, ["empty"], {})
        else:
            samp = double_sample(outcomes, n1=n1, c1=c1, c2=c2, n2=n2)

        err = samp.defects / samp.inspected if samp.inspected else 1.0
        metrics = {
            "n_items": len(items),
            "n_inspected": samp.inspected,
            "n_defects": samp.defects,
            "error_rate": round(err, 4),
            "max_error_rate": max_error_rate,
            "plan": samp.plan,
            "sampling_decision": samp.decision,
        }

        interventions: List[str] = []
        if samp.decision == "accept" and err <= max_error_rate:
            quality_ok = True
            decision = "accept_batch"
            notes.append("quality sufficient — safe to distill / promote traces")
        elif samp.decision in ("continue", "need_second_sample"):
            quality_ok = False
            decision = "continue_sampling"
            interventions.append("Continue sampling (inconclusive)")
            interventions.append("Prioritize high-risk item audits")
        else:
            quality_ok = False
            decision = "improve"
            interventions.extend(
                [
                    "Correct Annotations (high-risk slice first)",
                    "Update Guidelines",
                    "Train Annotators / tighten rubrics",
                    "Re-score with error model after fixes",
                ]
            )
            # risk-focused audit quota
            k = max(1, int(len(ranked) * risk_audit_fraction))
            interventions.append(f"Audit top-{k} risk items before next distill")
            notes.append("quality insufficient — block Loop 3 distill until improved")

        result = LoopResult(
            loop_id=loop_id,
            decision=decision,
            quality_sufficient=quality_ok,
            sampling=samp.to_dict(),
            interventions=interventions,
            high_risk_ids=high_risk[:50],
            metrics=metrics,
            notes=notes,
        )
        self._log(result)
        return result

    def _log(self, result: LoopResult) -> None:
        row = result.to_dict()
        row["ts"] = time.time()
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

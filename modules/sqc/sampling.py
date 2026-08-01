"""
Acceptance sampling plans for annotation / model-output quality gates.

Implements the three plans in the SQC figures:
  (a) Single sampling
  (b) Sequential (SPRT-style boundaries)
  (c) Double sampling
plus ASN curve estimates for efficiency comparison.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class SamplingDecision:
    plan: str
    decision: str  # accept | reject | continue | need_second_sample
    inspected: int
    defects: int
    reasons: List[str]
    meta: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def single_sample(
    outcomes: Sequence[bool],
    n: int,
    c: int,
) -> SamplingDecision:
    """
    outcomes: True = correct/good, False = incorrect/bad.
    Sample first n items; accept if defects d <= c.
    """
    sample = list(outcomes[:n])
    if len(sample) < n:
        return SamplingDecision(
            plan="single",
            decision="continue",
            inspected=len(sample),
            defects=sum(1 for x in sample if not x),
            reasons=[f"need n={n}, have {len(sample)}"],
            meta={"n": n, "c": c},
        )
    d = sum(1 for x in sample if not x)
    ok = d <= c
    return SamplingDecision(
        plan="single",
        decision="accept" if ok else "reject",
        inspected=n,
        defects=d,
        reasons=[f"d={d} c={c} → {'accept' if ok else 'reject'}"],
        meta={"n": n, "c": c},
    )


def double_sample(
    outcomes: Sequence[bool],
    n1: int,
    c1: int,
    c2: int,
    n2: int,
) -> SamplingDecision:
    """
    First sample n1:
      d1 <= c1 → accept
      d1 > c2 → reject
      else second sample n2; decide on d1+d2 vs c2 (standard double plan).
    """
    if c1 > c2:
        raise ValueError("c1 must be <= c2")
    s1 = list(outcomes[:n1])
    if len(s1) < n1:
        return SamplingDecision(
            plan="double",
            decision="continue",
            inspected=len(s1),
            defects=sum(1 for x in s1 if not x),
            reasons=[f"need first sample n1={n1}"],
            meta={"stage": 1, "n1": n1, "c1": c1, "c2": c2, "n2": n2},
        )
    d1 = sum(1 for x in s1 if not x)
    if d1 <= c1:
        return SamplingDecision(
            plan="double",
            decision="accept",
            inspected=n1,
            defects=d1,
            reasons=[f"stage1 d1={d1} <= c1={c1}"],
            meta={"stage": 1, "d1": d1, "n1": n1, "c1": c1, "c2": c2},
        )
    if d1 > c2:
        return SamplingDecision(
            plan="double",
            decision="reject",
            inspected=n1,
            defects=d1,
            reasons=[f"stage1 d1={d1} > c2={c2}"],
            meta={"stage": 1, "d1": d1, "n1": n1, "c1": c1, "c2": c2},
        )
    # need second sample
    s2 = list(outcomes[n1 : n1 + n2])
    if len(s2) < n2:
        return SamplingDecision(
            plan="double",
            decision="need_second_sample",
            inspected=n1 + len(s2),
            defects=d1 + sum(1 for x in s2 if not x),
            reasons=[f"inconclusive stage1 d1={d1}; need n2={n2}"],
            meta={"stage": 2, "d1": d1, "have_n2": len(s2), "n2": n2, "c2": c2},
        )
    d2 = sum(1 for x in s2 if not x)
    d = d1 + d2
    ok = d <= c2
    return SamplingDecision(
        plan="double",
        decision="accept" if ok else "reject",
        inspected=n1 + n2,
        defects=d,
        reasons=[f"stage2 d1+d2={d} vs c2={c2} → {'accept' if ok else 'reject'}"],
        meta={"stage": 2, "d1": d1, "d2": d2, "n1": n1, "n2": n2, "c1": c1, "c2": c2},
    )


@dataclass
class SequentialState:
    """Running SPRT state for sequential sampling of Bernoulli defects."""

    inspected: int = 0
    defects: int = 0
    # H0: p = p0 (good), H1: p = p1 (bad), p0 < p1
    p0: float = 0.02
    p1: float = 0.10
    alpha: float = 0.05  # producer risk
    beta: float = 0.10  # consumer risk

    def thresholds(self) -> Tuple[float, float]:
        # SPRT boundaries for log-likelihood ratio
        a = math.log((1 - self.beta) / self.alpha)
        b = math.log(self.beta / (1 - self.alpha))
        return b, a  # lower accept, upper reject (on LLR scale)

    def llr(self) -> float:
        # sum log(f1/f0) for Bernoulli
        if self.inspected == 0:
            return 0.0
        p0, p1 = self.p0, self.p1
        # protect bounds
        p0 = min(max(p0, 1e-9), 1 - 1e-9)
        p1 = min(max(p1, 1e-9), 1 - 1e-9)
        d, n = self.defects, self.inspected
        return d * math.log(p1 / p0) + (n - d) * math.log((1 - p1) / (1 - p0))


def sequential_sprt_step(
    state: SequentialState,
    is_correct: bool,
) -> Tuple[SequentialState, SamplingDecision]:
    """Inspect one more instance; return updated state + decision."""
    state.inspected += 1
    if not is_correct:
        state.defects += 1
    llr = state.llr()
    lo, hi = state.thresholds()
    if llr >= hi:
        dec = "reject"
        reasons = [f"SPRT LLR={llr:.3f} >= reject {hi:.3f}"]
    elif llr <= lo:
        dec = "accept"
        reasons = [f"SPRT LLR={llr:.3f} <= accept {lo:.3f}"]
    else:
        dec = "continue"
        reasons = [f"SPRT LLR={llr:.3f} in ({lo:.3f},{hi:.3f}) → continue"]
    decision = SamplingDecision(
        plan="sequential_sprt",
        decision=dec,
        inspected=state.inspected,
        defects=state.defects,
        reasons=reasons,
        meta={
            "llr": llr,
            "accept_bound": lo,
            "reject_bound": hi,
            "p0": state.p0,
            "p1": state.p1,
            "alpha": state.alpha,
            "beta": state.beta,
        },
    )
    return state, decision


def asn_curve(
    p_values: Optional[Sequence[float]] = None,
    n: int = 50,
    c: int = 2,
    n1: int = 30,
    c1: int = 0,
    c2: int = 3,
    n2: int = 30,
    p0: float = 0.02,
    p1: float = 0.10,
    alpha: float = 0.05,
    beta: float = 0.10,
    trials: int = 200,
) -> Dict[str, Any]:
    """
    Monte Carlo ASN (average sample number) vs true defect rate p.

    Plans:
      CI  — continuous inspection (100%) fixed at large N_ci for plotting bound
      SSP — single sampling fixed n
      DSP — expected n under double sampling (simulated)
      SPRT — expected n under sequential (simulated, capped)
    """
    import random

    if p_values is None:
        p_values = [i / 100.0 for i in range(0, 31)]  # 0%..30%
    N_ci = 200  # continuous inspection reference budget
    rng = random.Random(42)
    curves = {"p_pct": [], "CI": [], "SSP": [], "DSP": [], "SPRT": []}
    pa = p0 * 100
    pr = p1 * 100

    for p in p_values:
        curves["p_pct"].append(round(p * 100, 2))
        curves["CI"].append(N_ci)
        curves["SSP"].append(float(n))

        # Double sampling ASN simulation
        dsp_ns = []
        for _ in range(trials):
            outcomes = [rng.random() >= p for _ in range(n1 + n2)]
            d = double_sample(outcomes, n1, c1, c2, n2)
            dsp_ns.append(d.inspected)
        curves["DSP"].append(sum(dsp_ns) / len(dsp_ns))

        # SPRT ASN simulation (cap at N_ci)
        sprt_ns = []
        for _ in range(trials):
            st = SequentialState(p0=p0, p1=p1, alpha=alpha, beta=beta)
            while st.inspected < N_ci:
                good = rng.random() >= p
                st, dec = sequential_sprt_step(st, good)
                if dec.decision in ("accept", "reject"):
                    break
            sprt_ns.append(st.inspected)
        curves["SPRT"].append(sum(sprt_ns) / len(sprt_ns))

    return {
        "pa_pct": pa,
        "pr_pct": pr,
        "params": {
            "ssp": {"n": n, "c": c},
            "dsp": {"n1": n1, "c1": c1, "c2": c2, "n2": n2},
            "sprt": {"p0": p0, "p1": p1, "alpha": alpha, "beta": beta},
            "ci_budget": N_ci,
            "trials": trials,
        },
        "curves": curves,
        "ranking_note": (
            "Typically ASN: SPRT < DSP < SSP ≤ CI when p is far from indifference; "
            "ASN peaks near the p_a–p_r band where decisions are hardest."
        ),
    }


def render_asn_ascii(asn: Dict[str, Any], width: int = 56) -> str:
    """Simple ASCII multi-line ASN plot for terminal."""
    curves = asn["curves"]
    ps = curves["p_pct"]
    series = {k: curves[k] for k in ("CI", "SSP", "DSP", "SPRT")}
    all_y = [v for k in series for v in series[k]]
    ymin, ymax = min(all_y), max(all_y)
    if ymax <= ymin:
        ymax = ymin + 1
    lines = [
        f"ASN vs defect rate p%  (pa={asn['pa_pct']:.1f} pr={asn['pr_pct']:.1f})",
        f"y-range [{ymin:.1f}, {ymax:.1f}]  legend: C=CI S=SSP D=DSP R=SPRT",
    ]
    # sample every few points
    step = max(1, len(ps) // 16)
    for i in range(0, len(ps), step):
        p = ps[i]
        row = [" "] * width
        for key, ch in (("CI", "C"), ("SSP", "S"), ("DSP", "D"), ("SPRT", "R")):
            y = series[key][i]
            col = int((y - ymin) / (ymax - ymin) * (width - 1))
            row[col] = ch
        # mark pa/pr
        mark = ""
        if abs(p - asn["pa_pct"]) < 0.6:
            mark = "  |pa"
        if abs(p - asn["pr_pct"]) < 0.6:
            mark = "  |pr"
        lines.append(f"{p:5.1f}% |" + "".join(row) + mark)
    lines.append(asn["ranking_note"])
    return "\n".join(lines)

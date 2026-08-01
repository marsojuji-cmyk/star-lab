"""
Embedding expansion drift evaluation.

After vocab/embedding growth, compare baseline vs expanded model on three slices:
  - legacy:    only old tokens (untouched text)
  - new_token: only / dominated by new tokens
  - mixed:     new tokens interacting with old vocab

Gate:
  - harmful: high embedding displacement on legacy + task metric hit
  - warning: displacement up but tasks flat → watch, don't block
  - expected: drift only on new_token slice
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ── vector helpers (stdlib only) ──────────────────────────────────────────


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in a)) or 1e-12


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return _dot(a, b) / (_norm(a) * _norm(b))


def l2(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def mean_vec(rows: List[List[float]]) -> List[float]:
    if not rows:
        return []
    d = len(rows[0])
    out = [0.0] * d
    for r in rows:
        for i, v in enumerate(r):
            out[i] += v
    n = float(len(rows))
    return [x / n for x in out]


# ── slice taxonomy ────────────────────────────────────────────────────────

SLICE_LEGACY = "legacy"
SLICE_NEW = "new_token"
SLICE_MIXED = "mixed"
SLICES = (SLICE_LEGACY, SLICE_NEW, SLICE_MIXED)


@dataclass
class SliceItem:
    id: str
    text: str
    slice: str  # legacy | new_token | mixed
    # optional precomputed embedding from baseline / expanded (for offline eval)
    emb_baseline: Optional[List[float]] = None
    emb_expanded: Optional[List[float]] = None
    # optional task labels / scores
    label: Optional[str] = None
    pred_baseline: Optional[str] = None
    pred_expanded: Optional[str] = None
    score_baseline: Optional[float] = None
    score_expanded: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def load_slice_file(path: Path) -> List[SliceItem]:
    """
    JSONL or JSON list. Each row:
      id, text, slice, emb_baseline?, emb_expanded?, label?, pred_*, score_*
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        rows = json.loads(raw)
    else:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    items = []
    for r in rows:
        items.append(
            SliceItem(
                id=str(r.get("id") or r.get("text", "")[:32]),
                text=str(r.get("text") or ""),
                slice=str(r.get("slice") or SLICE_LEGACY),
                emb_baseline=r.get("emb_baseline") or r.get("embedding_baseline"),
                emb_expanded=r.get("emb_expanded") or r.get("embedding_expanded"),
                label=r.get("label"),
                pred_baseline=r.get("pred_baseline"),
                pred_expanded=r.get("pred_expanded"),
                score_baseline=r.get("score_baseline"),
                score_expanded=r.get("score_expanded"),
            )
        )
    return items


# ── metrics ───────────────────────────────────────────────────────────────


def cosine_shifts(
    items: List[SliceItem],
) -> Dict[str, Any]:
    """Per-item 1 - cosine(baseline, expanded); aggregate by slice."""
    by: Dict[str, List[float]] = {s: [] for s in SLICES}
    pairs = 0
    for it in items:
        if it.emb_baseline is None or it.emb_expanded is None:
            continue
        if len(it.emb_baseline) != len(it.emb_expanded):
            # pad/truncate to min dim for expansion cases where dim grew
            d = min(len(it.emb_baseline), len(it.emb_expanded))
            a, b = it.emb_baseline[:d], it.emb_expanded[:d]
        else:
            a, b = it.emb_baseline, it.emb_expanded
        shift = 1.0 - cosine(a, b)
        sl = it.slice if it.slice in by else SLICE_LEGACY
        by[sl].append(shift)
        pairs += 1

    def agg(xs: List[float]) -> Optional[Dict[str, float]]:
        if not xs:
            return None
        return {
            "n": len(xs),
            "mean_cosine_shift": sum(xs) / len(xs),
            "max_cosine_shift": max(xs),
            "p95_cosine_shift": sorted(xs)[max(0, int(len(xs) * 0.95) - 1)],
        }

    return {
        "n_pairs": pairs,
        "by_slice": {s: agg(by[s]) for s in SLICES},
        "overall": agg([x for xs in by.values() for x in xs]),
    }


def mean_embedding_displacement(items: List[SliceItem]) -> Dict[str, Any]:
    """Mean L2 displacement of paired embeddings by slice."""
    by: Dict[str, List[float]] = {s: [] for s in SLICES}
    for it in items:
        if it.emb_baseline is None or it.emb_expanded is None:
            continue
        d = min(len(it.emb_baseline), len(it.emb_expanded))
        disp = l2(it.emb_baseline[:d], it.emb_expanded[:d])
        sl = it.slice if it.slice in by else SLICE_LEGACY
        by[sl].append(disp)

    def agg(xs: List[float]) -> Optional[Dict[str, float]]:
        if not xs:
            return None
        return {"n": len(xs), "mean_l2": sum(xs) / len(xs), "max_l2": max(xs)}

    return {
        "by_slice": {s: agg(by[s]) for s in SLICES},
        "overall": agg([x for xs in by.values() for x in xs]),
    }


def nearest_neighbor_stability(
    items: List[SliceItem],
    *,
    k: int = 3,
) -> Dict[str, Any]:
    """
    For each item with embeddings, take top-k nearest neighbors under baseline
    and expanded (among the set). Stability = mean Jaccard of neighbor id sets.
    """
    usable = [
        it
        for it in items
        if it.emb_baseline is not None and it.emb_expanded is not None
    ]
    if len(usable) < 2:
        return {"n": 0, "mean_jaccard": None, "by_slice": {}}

    def topk(embs: List[List[float]], idx: int, kk: int) -> List[int]:
        scores = []
        a = embs[idx]
        for j, b in enumerate(embs):
            if j == idx:
                continue
            d = min(len(a), len(b))
            scores.append((cosine(a[:d], b[:d]), j))
        scores.sort(key=lambda x: -x[0])
        return [j for _, j in scores[:kk]]

    base_embs = []
    exp_embs = []
    for it in usable:
        d = min(len(it.emb_baseline), len(it.emb_expanded))  # type: ignore
        base_embs.append(list(it.emb_baseline[:d]))  # type: ignore
        exp_embs.append(list(it.emb_expanded[:d]))  # type: ignore

    jaccards: Dict[str, List[float]] = {s: [] for s in SLICES}
    all_j: List[float] = []
    for i, it in enumerate(usable):
        nb = set(topk(base_embs, i, k))
        ne = set(topk(exp_embs, i, k))
        if not nb and not ne:
            continue
        j = len(nb & ne) / float(len(nb | ne) or 1)
        sl = it.slice if it.slice in jaccards else SLICE_LEGACY
        jaccards[sl].append(j)
        all_j.append(j)

    def mean(xs: List[float]) -> Optional[float]:
        return sum(xs) / len(xs) if xs else None

    return {
        "n": len(all_j),
        "k": k,
        "mean_jaccard": mean(all_j),
        "by_slice": {s: {"n": len(jaccards[s]), "mean_jaccard": mean(jaccards[s])} for s in SLICES},
    }


def task_slice_metrics(items: List[SliceItem]) -> Dict[str, Any]:
    """Accuracy / score delta by slice when labels or scores present."""
    by: Dict[str, Dict[str, Any]] = {}
    for sl in SLICES:
        subset = [it for it in items if it.slice == sl]
        n_lab = 0
        n_ok_b = 0
        n_ok_e = 0
        score_b: List[float] = []
        score_e: List[float] = []
        for it in subset:
            if it.label is not None and it.pred_baseline is not None:
                n_lab += 1
                if it.pred_baseline == it.label:
                    n_ok_b += 1
            if it.label is not None and it.pred_expanded is not None:
                if it.pred_expanded == it.label:
                    n_ok_e += 1
            if it.score_baseline is not None:
                score_b.append(float(it.score_baseline))
            if it.score_expanded is not None:
                score_e.append(float(it.score_expanded))
        by[sl] = {
            "n": len(subset),
            "n_labeled": n_lab,
            "acc_baseline": (n_ok_b / n_lab) if n_lab else None,
            "acc_expanded": (n_ok_e / n_lab) if n_lab else None,
            "acc_delta": (
                (n_ok_e / n_lab) - (n_ok_b / n_lab) if n_lab else None
            ),
            "mean_score_baseline": (sum(score_b) / len(score_b)) if score_b else None,
            "mean_score_expanded": (sum(score_e) / len(score_e)) if score_e else None,
            "score_delta": (
                (sum(score_e) / len(score_e)) - (sum(score_b) / len(score_b))
                if score_b and score_e and len(score_b) == len(score_e)
                else None
            ),
        }
    return by


# ── gate ──────────────────────────────────────────────────────────────────


@dataclass
class DriftGateConfig:
    # mean cosine shift (1-cos) on legacy → above this is "high displacement"
    legacy_shift_warn: float = 0.05
    legacy_shift_harm: float = 0.12
    # task accuracy drop on legacy or overall
    task_acc_drop_harm: float = 0.03  # 3pp
    task_acc_drop_warn: float = 0.01
    # NN stability
    nn_jaccard_warn: float = 0.5
    # if only new_token slice is hot, classify expected
    new_only_ratio: float = 2.0  # new_shift / legacy_shift


DEFAULT_GATE = DriftGateConfig()


def evaluate_gate(
    report: Dict[str, Any],
    cfg: DriftGateConfig = DEFAULT_GATE,
) -> Dict[str, Any]:
    """
    Returns verdict: expected | warning | harmful | insufficient_data
    """
    cos = report.get("cosine_shift") or {}
    by = cos.get("by_slice") or {}
    legacy = (by.get(SLICE_LEGACY) or {}).get("mean_cosine_shift")
    new_s = (by.get(SLICE_NEW) or {}).get("mean_cosine_shift")
    mixed = (by.get(SLICE_MIXED) or {}).get("mean_cosine_shift")
    tasks = report.get("task_metrics") or {}
    leg_task = tasks.get(SLICE_LEGACY) or {}
    acc_delta = leg_task.get("acc_delta")
    nn = report.get("nn_stability") or {}
    nn_j = nn.get("mean_jaccard")

    reasons: List[str] = []
    if legacy is None and new_s is None:
        return {
            "verdict": "insufficient_data",
            "reasons": ["need emb_baseline + emb_expanded pairs on slices"],
            "gate": asdict(cfg),
        }

    # expected adaptation: new slice drifts, legacy quiet
    if (
        legacy is not None
        and new_s is not None
        and legacy < cfg.legacy_shift_warn
        and new_s >= cfg.legacy_shift_warn
        and (legacy <= 0 or new_s / max(legacy, 1e-9) >= cfg.new_only_ratio)
    ):
        reasons.append("drift concentrated on new_token slice (expected adaptation)")
        verdict = "expected"
    elif legacy is not None and legacy >= cfg.legacy_shift_harm:
        reasons.append(
            f"legacy mean cosine shift {legacy:.4f} >= harm {cfg.legacy_shift_harm}"
        )
        verdict = "harmful"
    elif legacy is not None and legacy >= cfg.legacy_shift_warn:
        reasons.append(
            f"legacy mean cosine shift {legacy:.4f} >= warn {cfg.legacy_shift_warn}"
        )
        verdict = "warning"
    else:
        verdict = "expected"
        if legacy is not None:
            reasons.append(f"legacy shift low ({legacy:.4f})")

    # task gate
    if acc_delta is not None:
        if acc_delta <= -cfg.task_acc_drop_harm:
            reasons.append(f"legacy task acc_delta {acc_delta:.4f} harmful")
            verdict = "harmful"
        elif acc_delta <= -cfg.task_acc_drop_warn and verdict != "harmful":
            reasons.append(f"legacy task acc_delta {acc_delta:.4f} warning")
            if verdict == "expected":
                verdict = "warning"

    # high displacement + flat tasks → warning (watch later)
    if (
        legacy is not None
        and legacy >= cfg.legacy_shift_warn
        and acc_delta is not None
        and abs(acc_delta) < cfg.task_acc_drop_warn
        and verdict == "harmful"
        and acc_delta > -cfg.task_acc_drop_harm
    ):
        # actually: displacement high, tasks flat → warning not block
        if acc_delta > -cfg.task_acc_drop_harm:
            verdict = "warning"
            reasons.append(
                "embedding drift up but task metrics flat — watch, do not block yet"
            )

    if nn_j is not None and nn_j < cfg.nn_jaccard_warn and verdict == "expected":
        if legacy is not None and legacy >= cfg.legacy_shift_warn:
            verdict = "warning"
            reasons.append(f"NN jaccard {nn_j:.3f} below {cfg.nn_jaccard_warn}")

    # refine: harm only if displacement + task hit (user rule)
    if (
        verdict == "harmful"
        and legacy is not None
        and legacy >= cfg.legacy_shift_harm
        and (acc_delta is None or acc_delta > -cfg.task_acc_drop_harm)
    ):
        verdict = "warning"
        reasons.append(
            "high legacy displacement without clear task hit → warning not hard block"
        )

    if (
        verdict != "harmful"
        and legacy is not None
        and legacy >= cfg.legacy_shift_harm
        and acc_delta is not None
        and acc_delta <= -cfg.task_acc_drop_harm
    ):
        verdict = "harmful"
        reasons.append("stable lexical setup but rising displacement + task hit")

    return {
        "verdict": verdict,
        "reasons": reasons,
        "signals": {
            "legacy_cosine_shift": legacy,
            "new_token_cosine_shift": new_s,
            "mixed_cosine_shift": mixed,
            "legacy_acc_delta": acc_delta,
            "nn_mean_jaccard": nn_j,
        },
        "gate": asdict(cfg),
    }


def run_drift_eval(
    items: List[SliceItem],
    *,
    cfg: Optional[DriftGateConfig] = None,
    nn_k: int = 3,
) -> Dict[str, Any]:
    """Full before/after report."""
    cfg = cfg or DEFAULT_GATE
    # slice counts
    counts = {s: sum(1 for it in items if it.slice == s) for s in SLICES}
    cos = cosine_shifts(items)
    disp = mean_embedding_displacement(items)
    nn = nearest_neighbor_stability(items, k=nn_k)
    tasks = task_slice_metrics(items)
    report = {
        "ts": time.time(),
        "n_items": len(items),
        "slice_counts": counts,
        "cosine_shift": cos,
        "mean_displacement": disp,
        "nn_stability": nn,
        "task_metrics": tasks,
        "interpretation": {
            "legacy": "untouched old-vocab text — drift here means disturbed geometry",
            "new_token": "new vocab only — drift usually expected after expansion",
            "mixed": "new tokens in old context — interaction effects",
        },
    }
    report["gate"] = evaluate_gate(report, cfg)
    return report


def write_example_slices(path: Path) -> Path:
    """Write a tiny synthetic JSONL for demos/tests."""
    path = Path(path)
    # 3D toy embeddings: baseline vs expanded (legacy almost same, new drifted)
    rows = [
        {
            "id": "L1",
            "text": "the cat sat on the mat",
            "slice": "legacy",
            "emb_baseline": [1.0, 0.0, 0.0],
            "emb_expanded": [0.99, 0.05, 0.0],
            "label": "A",
            "pred_baseline": "A",
            "pred_expanded": "A",
        },
        {
            "id": "L2",
            "text": "hello world from lab",
            "slice": "legacy",
            "emb_baseline": [0.0, 1.0, 0.0],
            "emb_expanded": [0.02, 0.98, 0.0],
            "label": "B",
            "pred_baseline": "B",
            "pred_expanded": "B",
        },
        {
            "id": "N1",
            "text": "<NEWTOK> entity",
            "slice": "new_token",
            "emb_baseline": [0.1, 0.1, 0.1],
            "emb_expanded": [0.0, 0.0, 1.0],
            "label": "C",
            "pred_baseline": "A",
            "pred_expanded": "C",
        },
        {
            "id": "M1",
            "text": "hello <NEWTOK> world",
            "slice": "mixed",
            "emb_baseline": [0.5, 0.5, 0.0],
            "emb_expanded": [0.4, 0.4, 0.4],
            "label": "A",
            "pred_baseline": "A",
            "pred_expanded": "A",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path

# Grok Star Lab — Baseline vs Upgrades

**Date:** 2026-08-01  
**Repo:** `~/Projects/grok-home` (main)  
**Tip:** `9e62600`  

## Executive summary

Baseline Grok Star Lab was a free Mac-local control plane with token-aware EV routing, forge/gym/showroom, and doctor. Upgrades add closed-loop quality, multi-agent context discipline, progressive delivery, mind/body doctrine, and model packaging (safetensors + manifest + tokenizer + drift).

## 3.1 Annotation quality — SQC (Loop 3)

_Commit:_ `b3b6f26`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Quality control | No formal annotation acceptance sampling | lab sqc risk|sample|loop|asn — single/double/sequential plans, risk scoring |
| Distill gate | tokens distill could run on any audits | Hard SQC gate: distill blocked unless last loop quality_sufficient (or --ungated) |
| Operator UX | Manual judgment only | Loop log + diagram; KPI tracks sqc_pass_rate / last decision |

Why it matters: prevents training/routing rules on rejected label batches.

## 3.2 Golden research log + KPI board

_Commit:_ `b11e2e4 / 2aa4b45`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Workflow logging | No structured end-to-end task log | lab research start|action|complete → research_log.db |
| KPIs | Doctor health only | accepted_patch_rate, tokens/success, recovery_rate, latency, portal/kpi.html |
| Volume | Empty or thin samples | Golden batch on starlab-demo (~26+ completions, audits n≈40+) |

Why it matters: Loop 4 measure/compare needs real outcomes, not vibes.

## 3.3 Context packets + LEAD recovery

_Commit:_ `0070c97`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Escalation context | Free-form paste / whole-repo stuffing | lab research packet create|show — goal, files, failing tests, route, budget |
| Attach to task | No structured context_pack | start --packet + logstore.attach_context_pack |
| On failure | One-shot hope; no standard retry plan | lab research recover + lab forge run --recover (LEAD one retry + plan) |

Why it matters: cleaner Grok escalations and fewer wasted long tasks after a red test.

## 3.4 Graph L2 — context carriage

_Commit:_ `0070c97`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Multi-agent view | Fixed workflow / full memory dump risk | Graph as budgeted nodes: B_i under L1 envelope |
| Context decision | Append packing knobs only | 3 gates (role, stage, recency) → pass | summarize | drop |
| CLI / telemetry | No per-node log | lab graph route-context|log-node|stats|ablate |
| Ablation | None | full vs budgeted vs role_aware; save_vs_full reported |

Why it matters: optimizes context carriage (RCR-style), not just model mode choice.

## 3.5 Shadow dual-log + graduation gates

_Commit:_ `75e139d`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Online policy proof | Route once; no dual log | Every lab tokens route logs shadow (log-only) |
| Router golden | No frozen suite | modules/tokens/goldens/router_v1.jsonl + lab tokens eval |
| Drift | Silent heuristic edits | lab tokens eval --drift vs frozen baseline |
| Graduation bar | Could “learn” anytime | lab tokens gates: shadow n, join rate, golden agreement, SQC |
| Session continuity | i.i.d. mode switches mid tool-loop | lab tokens session lock pins mode |

Why it matters: observation precedes influence; no bandit without data bar.

## 3.6 Four-stage progressive delivery

_Commit:_ `b3f0293`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Release path | Jump promote / advisory canary | shadow → canary 1–5% → ramp 10/25/50 → full |
| Promotion criterion | Snapshot green | Window pack: success, p95 ≤1.15×, cost/success, zero safety |
| Rollback | Manual / untested | One-switch rollout rollback + drill |
| Multi-agent isolate | No role isolation | lab graph breaker trip|reset |

Why it matters: each stage answers a different eval question.

## 3.7 Design: agentic circuit breakers

_Commit:_ `24e719a`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Breaker model | Binary trip/reset → force budgeted | Designed FSM: Closed → DEGRADED → Open → Half-Open |
| DEGRADED | Not present | Mode cap, budget_frac, budgeted packing |
| Rollout link | Unconditional rollback risk | Breakers may only rollback when armed; never advance |

Why it matters: contain cascading multi-agent failure without killing the graph.

## 3.8 Design: mind + body architecture

_Commit:_ `ced64cd`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Product shape | Toolbelt / wrapper risk | Every agent = mind (Grok) + body (identity, property, contact, limits) |
| Body registry | None | Proposed modules/body + lab body; lab:grok-home + starlab-demo |
| Contact with reality | Prompt-only | Producers: forge_exit, research, ship → ledger without chat |
| Skills | Global ~/.grok/skills | Skills land against a body |

Why it matters: operators pay for durable edges, not rented intelligence alone.

## 3.9 Safetensors interchange

_Commit:_ `6f148ec`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Weight format | Ad hoc .pt / pickle possible | Publish safetensors only; thin MLX/PyTorch adapters |
| Package layout | Undefined | config + tokenizer + model.safetensors or sharded + index |
| CLI | None | lab weights validate|convert|publish-check |
| Security | Pickle code execution risk | Header-only validate; STRICT fails on pickle |

Why it matters: portable, safer local heads for Apple Silicon.

## 3.10 Model manifest + schema

_Commit:_ `892fcc3`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Version metadata | Optional ad hoc notes | manifest.json with JSON Schema; schema_version ≠ model version |
| Integrity | No sealed hash | weights_sha256; seal CLI |
| Lineage | None | parent_version, code_commit, data_version, body_id, metrics |
| Publish | Manual checklist | publish-check --strict requires sealed manifest |

Why it matters: reproducibility, rollback, canaries, cross-runtime loaders.

## 3.11 Tokenizer-major versioning

_Commit:_ `e571224`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| Tokenizer changes | Silent file edits possible | Own artifact + tokenizer_manifest; freeze by default |
| Breaking rule | Undefined | Vocab/merge/special change → major + new package |
| Model bind | Optional id/version only | Must set tokenizer_hash; bind-tokenizer; assert_compatible |
| Growth | Undefined forks | append_only + provenance; dynamic discouraged |

Why it matters: silent tokenizer drift corrupts routing, horizon, and evals.

## 3.12 Embedding expansion drift

_Commit:_ `9e62600`

| Area | Baseline (before) | Upgrade (now) |
|------|-------------------|---------------|
| After vocab growth | No structured check | Before/after same prompts; slices legacy / new_token / mixed |
| Metrics | None | Cosine shift, L2 displacement, NN Jaccard, task deltas |
| Gate | None | expected | warning | harmful | insufficient_data |
| CLI | None | lab weights drift example|eval |

Why it matters: separate expected new-token adaptation from disturbed legacy geometry.


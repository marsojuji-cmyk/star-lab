# Plan cross-reference: closed-loop TACP vs token-awareness research thread

**Date:** 2026-08-01  
**Plan:** session plan “Closed-loop token policy research program”  
**Thread:** [Perplexity token-awareness chat](https://www.perplexity.ai/search/4d5b59f7-bc73-48c4-8ac5-7a64479965bd)  
**Lab baseline:** `~/Projects/grok-home` TACP (`modules/tokens/`), research goldens, SQC  

**Access note:** The live Perplexity URL is behind Cloudflare from this agent host. Cross-check used (1) the full closed-loop program text the user pasted from that thread, (2) primary sources cited in that thread and re-fetched independently, (3) in-repo TACP docs and code.

---

## Verdict

**The plan is sound and aligned with the token-awareness research program.**  
Suggested order (shadow → golden/drift → online λ/bandit → memory→skill → cache/tenant → ablation) matches both the Perplexity thread and 2025–2026 routing literature. Star Lab already implements the **single-price EV core** (`reward − λ·kilotokens`); the plan correctly moves from offline design to **prove → learn → harden**.

**Confidence:** high on sequencing and math shape; medium on multi-tenant KV claims until real cache telemetry exists (plan already honest about instrumentation-first).

---

## Theme map (thread → plan → lab)

| Thread theme | Plan phase | Already in lab? | Literature support |
|--------------|------------|-----------------|--------------------|
| Shadow router predicts horizon + mode; log cost/quality/route correctness | **P1** | Partial: route+audit, no shadow dual-log | Shadow/mirror is the standard safe online compare (Future AGI routing-policy eval 2026) |
| Frozen golden + A/B until cost/success wins w/o quality regression | **P2** | Workflow goldens yes; **router** golden set no | Four axes: route correctness, cost realized, quality under substitution, fallback |
| Price-based policy `Q − λC`; tune λ from budget pressure | **P3** | **Yes formula** in `policy.py` (`GROK_TOKEN_LAMBDA`); λ fixed, not online | TMLS bandit routing: single-price optimal under budget; dual controller on spend |
| Bandit / online learning from real feedback | **P3** | Distill rules offline + SQC gate only | BaRP / MetaLLM / contextual bandit routing papers |
| Wins→skills, failures→guardrails, prefs→memory | **P4** | Memory + skills exist; **promotion metrics** no | Session-aware / role routing need durable priors (SAAR, RCR-Router) |
| Cache-aware placement + multi-tenant fill/hit/fairness | **P5** | No | llm-d / GKE KV-aware routing; isolation vs reuse is open hard problem |
| Ablation: horizon vs cascade vs learned | **P6** | No | Standard research gate after shadow+golden |
| Packets + LEAD recover (prior launch) | **P0** | Mid-flight | Escalation hygiene before volume (reduces label noise) |

---

## Formula alignment (must stay true)

**Lab doctrine (already shipped):**

```text
EV(mode) = expected_reward(mode) − λ · predicted_token_spend_kilotokens
choose argmax EV  s.t. local baseline + safety
```

**Research optimal (TMLS / budgeted bandit):**

```text
a*(x) = argmax_m [ q_m(x) − λ · c_m ]
λ set so budget binds (raise λ if overspend, lower if underspend)
```

These are the **same scalarization**. Plan Phase 3 is “make λ and quality estimates online,” not “invent a new objective.” Do not replace EV with pure confidence thresholds.

**Checklist from theory that the plan should keep:**

1. Prefer **single price λ** over hand mode thresholds.  
2. **Calibrate** quality/horizon signals before pricing hard against them.  
3. Measure **variance of quality gap** across tasks (ceiling on router savings).  
4. Watch **λ itself** as ops signal (high λ → quality-starved / raise budget; λ≈0 → slack).  

---

## Routing-policy eval axes vs plan gates

Industry pattern (evaluate the **policy**, not only the model):

| Axis | Meaning | Plan coverage | Gap / patch |
|------|---------|---------------|-------------|
| 1. Route correctness | Right mode for task class | P2 golden agreement | Add labels: correct / over / under / ambiguous |
| 2. Cost realized vs theory | Cost **per successful outcome**, not token fantasy | P1–P2 join route→complete | Emphasize cost_per_success (already in research KPI) |
| 3. Quality under substitution | Cheaper mode within pre-committed ε | P2 gate “no quality regression” | **Pre-commit ε before experiment** (write in eval harness) |
| 4. Fallback correctness | Recovery path works | P0 LEAD recover | Add explicit **chaos/fallback** sample on golden (force fail → recover once) |

Shadow workflow literature: instrument → golden set → shadow candidate → same rubric → promote only on **Pareto** (not single axis). Plan already says B beats A on cost/success and not worse on quality/agreement — **keep Pareto discipline**.

---

## Session / multi-agent / cache (hard questions)

| Open problem (thread + papers) | Plan | Reality check |
|--------------------------------|------|---------------|
| Calibrated horizon under distribution shift | P2 drift + P6 | Correct first-class open problem |
| Session-aware routing (long agents) | Open-problems doc; light touch in P4 | Add **session continuity fields** early (session_id on route audit) even if policy stays i.i.d. |
| Role/token-budget in multi-agent graphs | Open | Deferred; packing `subagents` is mode-governed today — good seed |
| Safe multi-tenant cache isolation without killing reuse | P5 instrument-first | Correct: do **not** claim hit-rate wins without KV backend; schema + prefix_id only |

**SAAR-style caution:** hard-lock model/mode switches mid tool-loop. For Grok Build OS, recovery (P0) and session locks should not escalate mid-validate without completing the atomic unit.

---

## Gaps found (plan patches)

| # | Gap | Severity | Patch into plan |
|---|-----|----------|-----------------|
| G1 | No explicit **fallback/chaos** eval axis | Med | P2: sample force-fail → `lab research recover` / forge `--recover` |
| G2 | Shadow initially same policy only | Low | OK for instrumentation; P1 exit requires alternate shadow policy_id |
| G3 | Missing **session_id** on audits from day one | Med | P1: stamp session + tenant on every route/shadow row |
| G4 | Quality calibration not named | Med | P2/P3: horizon MAE + quality calibration before hard λ control |
| G5 | Mirror cost when dual *model* shadow | Low | Local modes free; document if dual Grok calls ever shadow-paid |
| G6 | Cascade baseline not built | Med | P6 ablation needs a **cascade stub** (short→retry medium→deep) by P2/P3 |
| G7 | Perplexity thread not re-fetched live | Ops | Paste-ready brief below; user can re-run in thread |

**No blockers.** Sequencing is right; do **not** jump to bandit (P3) before golden (P2).

---

## Anti-patterns the plan correctly avoids

| Anti-pattern | Plan stance |
|--------------|-------------|
| Serve learned policy without shadow | Serve baseline until gate |
| Single-axis “always cheaper” | EV + quality gate |
| Distill without SQC | Existing hard gate kept |
| Fake multi-tenant hit rates | Instrument-first honesty |
| Train MLX before clean joins | Explicitly deferred |

---

## Paste into Perplexity (share plan for re-verify)

Copy the block below into the existing thread:

```text
Please cross-check this Grok Star Lab closed-loop plan against this thread’s
token-awareness program and the sources you already cited.

CONTEXT (what we already built locally, free/offline):
- lab tokens route: EV = reward − λ·kilotokens; modes local|short|medium|deep
- audit complete + distill gated by lab sqc (annotation quality)
- lab research golden logs + KPI board (cost/success, recovery, MAE)
- SessionStart arms token policy; per-task route still required
- Mid-flight: context packets + LEAD one-shot recovery

PROPOSED PHASES (gates, no skip):
0) Finish packets + LEAD recover (clean labels)
1) Shadow dual-log on every route (log-only candidate; serve baseline)
2) Frozen router golden + drift harness; promote only if cost/success improves
   and quality/agreement within ε (Pareto, pre-commit ε)
3) Online λ from budget pressure + light bandit from completed feedback
4) Memory→skill promotion with reuse metrics like cache hit rate
5) Cache-aware prefix_id + multi-tenant telemetry (instrument first; no fake KV)
6) Ablation: horizon signal vs cascade vs learned router

OPEN PROBLEMS we track:
- calibrated horizon under shift
- session-aware long-agent routing
- role/budget multi-agent graphs
- safe multi-tenant KV isolation vs reuse

QUESTIONS FOR YOU:
1) Does this order match best practice for routing-policy eval (shadow before
   bandit, golden before serve)?
2) What’s missing vs production gateways (fallback chaos, cost-per-outcome,
   session locks mid tool-loop)?
3) Any red flags applying single-price λ to Grok Build *modes* (not multi-model
   APIs) on a single Mac lab?
4) What minimum golden-set size/stratification for mode routing (intent × length
   × difficulty)?
5) Confirm: do NOT train heavy local heads until shadow join rate is healthy.

Reply with: ALIGNED | GAPS | CHANGE ORDER | DROP.
```

---

## Sources re-checked (independent of Perplexity paywall)

- Bandit / single-price: [TMLS Bandit Formulations of Model Routing](https://www.tmls.nyc/research/bandit-model-routing)  
- Bandit feedback learning: [BaRP arXiv:2510.07429](https://arxiv.org/html/2510.07429v1)  
- Routing-policy eval + shadow workflow: [Evaluating LLM Routing Policies (2026)](https://futureagi.com/blog/evaluating-llm-routing-policies-2026/)  
- Session-aware: [SAAR / vLLM blog](https://vllm.ai/blog/2026-06-02-session-aware-agentic-routing)  
- KV-aware: [llm-d / Red Hat](https://developers.redhat.com/articles/2025/10/07/master-kv-cache-aware-routing-llm-d-efficient-ai-inference)  
- Isolation risk: multi-tenant KV prompt leakage literature (NDSS-class results)

---

## Next step after this note

Resume execution: **Phase 0 ship**, then **Phase 1 shadow** with session_id + tenant columns (G3), and seed router golden labels for over/under (G1/G6 light).

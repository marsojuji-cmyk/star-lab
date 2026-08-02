# Routing ROI as a **system** (Star Lab)

**Date:** 2026-08-01  
**Thesis:** The ROI case is strongest when routing is measured as a **system**, not as a model trick.  
**Sources:** Future AGI routing-policy eval; FrugalAI cost-aware routing; Orzed break-even guidance; token-aware routing literature.

---

## Best ROI case for *this* lab (ranked)

| Rank | Case | Why it wins here | Evidence path |
|------|------|------------------|---------------|
| **#1** | **Token-aware mode routing + packing** (local/short/medium/deep) | Cheap tasks never enter deep; packing knobs cut wasted context. Biggest lever on a Mac that **must** escalate hard work to Grok (Vega 20 cannot host big local LLMs). | Shadow: cost/success vs always-medium or always-deep baseline |
| **#2** | **Graph context carriage** (role budgets, pass/summarize/drop) | Multi-agent waste is mostly **replayed context**, not wrong model ID. | `lab graph ablate` full vs role_aware; join to research success |
| **#3** | **LEAD recovery + fail-fast** | Saves **failed long trajectories**, not just cheaper first calls. | recovery_rate + tokens on recovered success |
| **#4** | **SQC-gated distill** | Stops bad rules from *increasing* cost (wrong under-route / over-route). | Distill only after quality_sufficient |
| **#5** | Multi-model API market routing | High ROI in multi-provider SaaS; **lower priority** on this single-Grok home lab. | Defer until multi-provider spend is real |

**Winner for home Star Lab:**  
**#1 + #2 together** — mode routing prevents expensive *calls*; graph routing prevents expensive *payloads* on the calls you still make. That is the system story.

---

## What to measure (system scorecard)

Compare **routed pipeline** vs **no-routing baseline** (e.g. always `deep`, or always max context), weekly.

| Axis | Definition | Star Lab signal |
|------|------------|-----------------|
| **Realized cost** | $ or token proxy **per successful outcome**, not per request | `average_tokens_per_success` (research KPI); mode budget × calls |
| **Quality under substitution** | Cheaper mode/context still succeeds | accepted_patch_rate, test_pass_rate, outcome_quality on audits |
| **Latency** | p95 / mean task latency | `latency_per_completed_task_s`; forge duration_ms |
| **Fallback correctness** | Recovery path works | recovery_rate; LEAD recover retry_ok; chaos budget |
| **Route accuracy** | Right mode for task class | frozen `lab tokens eval` + shadow mode agreement |
| **Token budget utilization** | Used / budget; waste on packing | packing plan vs actual_tokens; overrun_rate |
| **Fleet / pool efficiency** | Throughput per unit compute (or per $) | later: cache hit, concurrent tasks; today: tasks/day at fixed budget |
| **Routing overhead** | Cost of router + dual shadow + eval | count shadow routes, eval runtime — subtract from savings |

**Separate the bill:**

```text
gross_savings = cost(baseline_always_deep) − cost(routed_inference)
net_savings   = gross_savings
                − routing_overhead
                − retry_cost
                − (latency_cost if SLA priced)
```

If you only report “% fewer tokens on prompts,” you miss retries, shadow spend, and quality regressions that force rework.

---

## ROI formula

\[
\mathrm{ROI} = \frac{\text{annual savings} - \text{engineering + infra overhead}}{\text{engineering + infra overhead}}
\]

| Side | Include |
|------|---------|
| **Savings** | Reduced model spend; fewer wasted long-context / deep calls; lower GPU-hours if packing/KV improves; fewer failed long trajectories (recovery) |
| **Overhead** | Router logic + maintenance; golden/eval suite; observability; shadow traffic; retraining bandit/heads; human time on gates |

**Token-aware addition to savings:**

- Tasks that stay `local` / `short` instead of `deep`  
- Tighter packing (`max_context_tokens`, graph drop/summarize)  
- Optional: better cache/prefix reuse (instrument later)

**Cleanest production test (already lab doctrine):**  
Shadow routed policy beside baseline → promote only if **cost per successful outcome** improves **and** quality does not regress.

---

## Practical spend threshold

Industry guides: routing often **pays when monthly LLM spend is already material** (order-of-magnitude: a few thousand USD/month), with payback measured in weeks once volume is high. Below that, **engineering + eval maintenance can exceed savings**.

| Spend regime | ROI outlook for full routing program |
|--------------|--------------------------------------|
| **Hobby / &lt; ~$100–500/mo** | Still worth **cheap** heuristics (this lab’s offline EV + local ops) — ROI is **time** and **discipline**, not invoice math |
| **~$1–3k/mo** | Break-even zone for real multi-model routing + eval ops |
| **≫ $3k/mo** | Strong $ ROI if eval suite prevents quality regressions |

**This Mac today:** cloud Grok spend may still be modest. The **best ROI case is still #1+#2**, but the “return” is:

1. **Avoided deep sessions** on ops/typos  
2. **Avoided context bloat** on multi-step agents  
3. **Avoided failed long runs** via recovery  
4. Future: dollars, once invoice-grade metering (OTEL) exists  

Do not claim SaaS-scale % savings until shadow joins actual tokens weekly.

---

## Snapshot from *this* machine (honest, not an invoice)

As of lab KPI pull (research + token audits):

| Metric | Value | ROI reading |
|--------|-------|-------------|
| Completed research tasks | 27 | Small N — direction only |
| Success / accepted patch | ~93% | Quality floor for substitution tests |
| Avg tokens per success | ~1175 | Primary cost proxy for success |
| Recovery rate | ~11% | Some long-fail paths exist to save |
| Token audits n | 41 | Horizon MAE ~1243; overrun_rate high → packing/horizon still leak money |
| Mode mix (audits) | short 29, local 10, deep 2 | Routing is already skewing cheap — good |
| Shadow n | 11 (&lt; 50 gate) | Not enough for canary $ proof yet |
| Join rate route→complete | 0 | **Must fix** for cost-per-success shadow A/B |

**Implication:** Architecture for system ROI is in place; **accounting join is not**. Highest-leverage next ROI engineering is **join every route to actual_tokens + success** so shadow can compute cost/success vs baseline.

---

## How to run the “best” ROI experiment (Star Lab)

### Baseline policies (pick one primary)

| Baseline ID | Behavior |
|-------------|----------|
| `always_deep` | Force deep mode, large packing |
| `always_medium` | Force medium |
| `unpacked` | deep packing max_context always |

### Candidate (current lab)

`heuristic_v1` + optional graph `role_aware` packing on multi-agent tasks.

### Protocol

```text
1. lab tokens eval                    # route accuracy on frozen golden
2. For each task in stratified set + live samples:
     route with candidate → execute → complete(actual_tokens, quality, success)
     dual-log shadow of baseline mode (or offline re-score packing cost)
3. Weekly:
     cost_per_success_candidate  vs  cost_per_success_baseline
     quality / success rates within ε
     latency p95 within 10–20%
     fallback chaos fail rate within budget
4. Promote only if candidate wins economics AND quality (Pareto)
```

### Stratified golden dimensions

- Intent: ops / implement / debug / architecture  
- Length: short / medium / long  
- Failure: clean vs recover  
- Multi-agent: single node vs graph handoff  

---

## Token-aware ROI checklist (production)

- [ ] Cost per **successful** outcome (not per token alone)  
- [ ] Direct inference savings **minus** shadow + retry + router overhead  
- [ ] Token budget utilization + packing waste  
- [ ] Quality under substitution (cheaper mode still works)  
- [ ] Fallback correctness (recover / breaker)  
- [ ] Route accuracy on golden + live samples  
- [ ] Shadow before canary; window pack before ramp  

---

## Formula worked example (illustrative)

Assume baseline always-deep costs **$2.00** per successful task; routed average **$0.80**; 500 successes/month; routing ops **$200/month** amortized.

```text
monthly_savings = 500 × (2.00 − 0.80) = $600
monthly_overhead = $200
monthly_net = $400
annual_net ≈ $4800
annual_overhead ≈ $2400
ROI ≈ (4800 − 2400) / 2400 = 100%
```

Replace dollars with **tokens** on this Mac until OTEL/$ exists:

```text
tokens_saved_per_success = baseline_tokens − routed_tokens
ROI_proxy = sum(tokens_saved on successes) / tokens_spent_on_router_and_shadow
```

---

## Ranking recap

| Question | Answer for Star Lab |
|----------|---------------------|
| Best ROI *mechanism*? | Token-aware **mode + packing** + **graph context** |
| Best ROI *measurement*? | **Cost per successful outcome** with shadow A/B |
| Best ROI *when to invest heavy*? | When monthly LLM $ is material (k$/mo scale) |
| Best ROI *today on this Mac*? | Time + avoided deep bloat; instrument joins now so $ROI later is real |

---

## 100× program (Claude-style baseline)

See **`docs/TOKEN-SAVINGS-100X.md`** and `lab tokens savings vs-claude`.  
That suite measures system multiplier vs deep+fat unbounded packing (Claude-pattern waste), not vs an already-routed peer.

## Related lab surfaces

| Need | Command / doc |
|------|----------------|
| Cost proxy | `lab research kpi` |
| Route accuracy | `lab tokens eval` |
| Shadow | `lab tokens route` / `shadow compare` |
| Promote gates | `lab tokens gates` / `rollout` |
| Context savings | `lab graph ablate` |
| Policy eval theory | Future AGI routing-policy eval 2026 |
| Hardware constraint | `docs/HARDWARE-AI-EXPECTATIONS.md` (Grok for hard work) |

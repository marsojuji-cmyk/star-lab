# Closed-loop gates — four-stage progressive delivery

**Status:** `lab tokens rollout` + `lab graph breaker`  
**Doctrine:** observation precedes influence; each stage answers a different question.

---

## Four-stage gate

| Stage | Traffic to candidate | User impact | Eval question | Promote when |
|-------|----------------------|-------------|---------------|--------------|
| **1. Shadow** | 100% mirrored | **Zero** | Similar to baseline on real traffic? | mode agree + frozen eval |
| **2. Canary** | **1–5%** sticky cohorts | Limited | At least as good with users in the loop? | full **window** pack green |
| **3. Percentage ramp** | 10 → 25 → 50% | Broader | Deltas hold over windows? | each step window green |
| **4. Full** | 100%, auto-rollback armed | All | Hold under load? | hold window; prior baseline retained |

**Multi-agent:** canary does **not** start until shadow similarity **and** frozen eval pass.

---

## CLI

```bash
# Stage 1
lab tokens route "…"
lab tokens shadow compare
lab tokens eval && lab tokens gates

# Stage 2 (blocked until gates + shadow_ok)
lab tokens rollout propose --policy-id candidate_v2
lab tokens rollout shadow-ok
lab tokens rollout start --frac 0.01          # default 1%, max 5%
lab tokens rollout check                      # window pack; hard stop → rollback
lab tokens rollout advance                    # 1%→5% then →10% ramp…

# Stage 3–4
lab tokens rollout advance                    # 10→25→50→full
lab tokens rollout rollback --reason "p95"
lab tokens rollout drill                      # test one-switch path

# Multi-agent isolation
lab graph breaker trip --role implementer --reason "cascade"
lab graph breaker reset --role implementer
lab graph breaker status
```

Compat wrappers: `lab tokens canary *` maps onto rollout (promote → advance, not jump-to-full).

---

## Window promotion pack

Advance only if **all** hold for the stage window (not a single snapshot):

| Metric | Default gate |
|--------|----------------|
| Task success | ≥ baseline − 2pp |
| Human intervention | ≤ baseline + 2pp |
| p95 latency (proxy) | ≤ baseline × **1.15** |
| Cost per success | **not worse** than baseline |
| Hard safety / policy violations | **zero** |
| Validate/tool fail rate | ≤ baseline + 5pp |
| Frozen eval | agreement healthy, no deep_violations |
| Window duration | canary 24h / ramp step 12h / full 48h (lab: `GROK_ROLLOUT_FAST=1`) |
| Min samples | ≥ 3 completed research logs (lab-scale) |

Any **hard stop** → automatic one-switch rollback.

---

## Practical first thresholds

- Start canary at **1%**, hold until window clean, then bump to **5%**, then ramp.  
- p95 within **10–20%** of baseline (default 15%).  
- Cost per success not worse.  
- Zero hard safety violations.

Override: `~/.grok/lab/rollout_bar.json`

---

## Sticky cohorts

```text
hash(tenant:session_id) < traffic_frac  →  candidate side
```

Same session stays on one side (pairs with `lab tokens session lock` mid tool-loop).

**Lab honesty:** “traffic %” is sticky assignment of local sessions/tasks for measurement, not a multi-user CDN. `serve_enabled` defaults **false**.

---

## Circuit breakers (multi-agent)

One bad role does not take the graph down:

```bash
lab graph breaker trip --role implementer --fallback budgeted
# route-context for that role forced to budgeted until reset
```

---

## Rollback

- **One switch:** `lab tokens rollout rollback --reason …`  
- **Drill:** `lab tokens rollout drill` (must pass in CI/tests)  
- Restores `baseline_policy_id`, zeros frac, disarms serve  

Future (when cache exists): invalidate candidate-tagged semantic cache on rollback.

---

## DROP rules

1. No heavy local heads until shadow volume/join + frozen + windowed stages allow.  
2. No jump from canary to full — use `advance`.  
3. λ remains a calibrated control signal under session locks.  
4. Observation precedes influence.

---

## Related

| Doc | Role |
|-----|------|
| `docs/TOKEN-AWARE-CONTROL-PLANE.md` | L1 EV policy |
| `docs/research/GRAPH-CONTEXT-ROUTING.md` | L2 context carriage |
| `modules/tokens/rollout.py` | stage machine |
| `modules/graph/breaker.py` | role isolation |

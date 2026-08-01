# Closed-loop gates (shadow → canary → online)

**Status:** implemented as `lab tokens gates|eval|canary|session`  
**Doctrine:** observation precedes influence.

Perplexity / literature alignment (2026-08-01): **ALIGNED** on funnel; **GAPS** closed here with explicit canary, data bar, frozen-vs-drift, fallback budget, session locks; **CHANGE ORDER** adopted; **DROP** heavy heads until bars pass.

---

## Stricter order

| # | Phase | Gate before next |
|---|-------|------------------|
| 0 | Clean packets + LEAD recovery | recover works offline |
| 1 | Shadow dual-log | shadow n growing, join path exists |
| 2 | **Frozen** golden + **drift** harness (separated) | agreement + no drift flags |
| 3 | **Canary / guarded promotion** + rollback | ready_for_canary |
| 4 | Online λ + light bandit | ready_for_online |
| 5 | Memory → skill promotion | reuse metrics |
| 6 | Cache / multi-tenant telemetry | schema only until real KV |
| 7 | Ablation publish | repro commands |

---

## Declared data bar (graduation)

Defaults in `modules/tokens/gates.py` / override `~/.grok/lab/graduation_bar.json`:

| Bar | Default | Meaning |
|-----|---------|---------|
| `min_shadow_n` | 50 | shadow dual-log volume |
| `min_join_rate` | 0.50 | shadow → completed audit join |
| `min_mode_agree_frac` | 0.85 | served vs shadow (mirror ≈1.0) |
| `min_golden_agreement` | 0.80 | frozen suite exact mode match |
| `max_horizon_mae` | 2500 | calibration under shift |
| `require_sqc_accept` | true | Loop 3 before online |
| `max_fallback_chaos_fail_rate` | 0.15 | LEAD recover failure budget |
| `canary_max_traffic_frac` | 0.10 | cap canary slice |

```bash
lab tokens gates          # graduation report
lab tokens eval           # frozen suite
lab tokens eval --drift   # drift vs frozen baseline
lab tokens eval --freeze-baseline
```

---

## Canary / rollback

```bash
lab tokens canary propose --policy-id rules_v2
lab tokens canary start --traffic-frac 0.05   # requires ready_for_canary
lab tokens canary status
lab tokens canary rollback --reason "quality drop"
lab tokens canary promote                     # requires ready_for_online
```

**Lab default:** canary is **registry + advisory traffic_frac**; it does **not** auto-serve alternate policies until an explicit serve path is wired. Rollback always zeros traffic.

---

## Frozen vs drift (separated)

| Artifact | Path | Mutability |
|----------|------|------------|
| Frozen suite | `modules/tokens/goldens/router_v1.jsonl` | versioned in git; labels = **current heuristic baseline** (regression), not aspirational targets |
| Frozen baseline snapshot | `~/.grok/lab/frozen_eval_baseline.json` | set via `--freeze-baseline` |
| Drift report | `lab tokens eval --drift` | live window vs baseline |

Do not mix: golden edits are intentional suite changes; drift flags are live regression signals.

---

## Session locks (tool loops)

Sequential prompt evolution breaks i.i.d. routing. While a tool loop is in flight:

```bash
lab tokens session lock --reason tool_loop --mode medium
# … tools …
lab tokens session unlock
```

`lab tokens route` respects lock: pins `locked_mode` when set (unless `--force-mode`).

---

## Fallback chaos failure budget

LEAD recover failures count toward `max_fallback_chaos_fail_rate`.  
Sample intentionally:

```bash
lab research recover <task_id> --cmd "false"   # expect fail path
# then real validate cmd
```

---

## DROP rules (hard)

1. **Do not** train heavy local heads until `ready_for_online`.  
2. **Do not** serve bandit/alternate policy without canary + rollback.  
3. **Do not** treat single-price λ as a blind day-one rule for all modes — calibrate under session locks and budgets (`GROK_TOKEN_LAMBDA` is a control signal).  
4. Observation precedes influence.

---

## λ as control signal

```text
EV = reward − λ · kilotokens
```

λ is **tunable**, not a sacred constant. High λ → quality-starved / raise budget or fix under-routing; λ≈0 → slack. Online dual control only in phase 4 after gates.

# Tokenomics Report — Entire Grok Chat (World Stage → Star Lab → Tokens)

| Field | Value |
|-------|--------|
| **Generated** | 2026-08-01 |
| **Primary session** | `019fbb71-7207-7410-bf43-1c2edb1c84bc` |
| **Model** | `grok-4.5` (reasoning_effort: high) |
| **Window** | ~2026-08-01 03:50 UTC → 06:26 UTC (~**2.05 hours** wall clock on main) |
| **Scope** | Main agent session + forked design/implement/review subagents from this chat |

---

## 1. Executive summary

This chat was a **heavy build session**: home setup, full design loop, multi-PR execute-plan with dozens of subagents, Model Gym, and a token-aware control plane.

| Metric | Value | Confidence |
|--------|-------|------------|
| **User-visible turns (main)** | **13** | High (telemetry) |
| **Model stream starts (all related agents)** | **~565** | High (`first_token` events) |
| **Tool completions (all related)** | **~1,454–1,886** | High |
| **Peak context occupancy (main)** | **273,645 / 500,000** (54%) | High |
| **Estimated cumulative tokens processed** | **~19M – 42M** (band) | Medium (modeled) |
| **Central estimate** | **~28.6M tokens** | Medium |
| **Billable $ (API)** | **Unknown locally** — CLI does not store $; subscription/plan dependent | — |

> **Important:** Grok Build on this machine does **not** persist official per-request `input_tokens` / `output_tokens` / `$` in session files (OTEL can export them if configured). Numbers below mix **exact telemetry** with a **transparent estimate** of cumulative token processing.

---

## 2. Exact telemetry (authoritative)

### 2.1 Main session (`signals.json`)

| Signal | Value |
|--------|------:|
| Session duration | **7,393 s** (~2.05 h) |
| User messages | **13** |
| Assistant messages | **126** |
| Turns (`turn_ended`) | **13** |
| Model stream starts (`first_token`) | **134** |
| Tool calls completed | **~260–267** |
| Latency samples | **36** |
| Stream chunks | **9,567** |
| Context tokens used (peak fill) | **273,645** |
| Context window | **500,000** |
| Context window usage | **54%** |
| Compactions | **0** |
| Avg time-to-first-token | **5,089 ms** |
| Avg response time | **12,224 ms** |
| Peak RSS | **~271 MB** |
| Agent lines added | **18,862** |
| Agent lines removed | **200** |
| Files touched | **154** |
| Git commits (main agent) | **2** |
| Errors / tool failures | **7 / 6** |
| Cancellations | **2** |
| Primary model | **grok-4.5** |

### 2.2 Whole chat ecosystem (main + subagents)

From **~44–45** agent sessions with signals/events:

| Signal | Aggregate |
|--------|----------:|
| Model stream starts (`first_token`) | **565** |
| User messages (sum of session counters) | **84** |
| Assistant messages | **696** |
| Tool completions | **~1,454** (events) / **1,886** (signals) |
| Wall time summed across agents | **~14,277 s** (~4.0 agent-hours, parallelized) |
| Peak context (largest single session) | **273,645** (main) |

Subagents (design writer/reviewer, implementers, PR reviewers) dominate **stream count** even though the user only sent **13** main-chat prompts.

---

## 3. Token spend estimate (modeled)

### 3.1 Method

For each agent session with peak context \(C\) and \(N\) model streams (`first_token`):

\[
\text{input-ish} \approx 0.45 \times C \times N
\]
\[
\text{output-ish} \approx 600 \times N
\]

| Band | Formula | Estimated total tokens |
|------|---------|------------------------:|
| **Conservative** | \(0.30 C N + 400 N\) | **~19.1M** |
| **Central** | \(0.45 C N + 600 N\) | **~28.6M** |
| **Aggressive** | \(0.65 C N + 1200 N\) | **~41.5M** |

### 3.2 Split (central)

| Bucket | Est. tokens | Share |
|--------|------------:|------:|
| Input / context processed | **~28.3M** | ~99% |
| Output generation | **~0.34M** | ~1% |
| **Total** | **~28.6M** | 100% |

This pattern is normal for long agent sessions: **most cost is re-reading a fat context**, not writing long answers.

### 3.3 Main vs subagents (central)

| Lane | Streams (approx) | Role |
|------|-----------------:|------|
| Main orchestrator | **134** | User chat, design orchestration, execute-plan control |
| Subagents / worktrees | **~431** | Design write/review, PR implement/review loops |

Subagents are the bulk of **stream volume**; main holds the **largest single context**.

---

## 4. Dollar tokenomics (illustrative only)

Local CLI has **no cost ledger**. Use these only as **what-if** scales against the **central ~28.6M** estimate:

| Assumed blended price (in+out) | Implied cost @ 28.6M |
|--------------------------------|---------------------:|
| $0.50 / 1M tokens | **~$14** |
| $2 / 1M tokens | **~$57** |
| $5 / 1M tokens | **~$143** |
| $15 / 1M tokens | **~$429** |

If you are on a **flat Grok/xAI subscription**, cash outlay may be **$0 incremental** for this chat even when “token mass” is large.

**Cache reads** (if any) are not broken out locally — true bill can be lower than raw processed context.

---

## 5. Work product vs token mass (ROI)

| Delivered | Evidence |
|-----------|----------|
| Memory + home rules + safety rails | `~/.grok/memory`, `rules`, `hooks` |
| Grok Home / Star Lab design | `docs/GROK-STAR-LAB-DESIGN.md` (~60KB design) |
| Execute-plan stack | 14 PR branches + many worktrees |
| Model Gym + Forge | `modules/gym`, `modules/forge` |
| Token control plane | `modules/tokens`, `lab tokens` |
| Auto SessionStart policy | `token-session-start.json` + boot script |
| Code volume | **+18.8k / −0.2k** lines (main signal) across **154** files |

**Tokenomics takeaway:** Most spend bought **multi-agent implementation bandwidth**, not user chat verbosity (13 user turns → 565 model streams).

---

## 6. Token-policy lens (what the new design would do)

`lab tokens` audit log (local policy DB), routes recorded this machine:

| Mode | Routes logged | Σ predicted horizon | Σ budgets |
|------|--------------:|--------------------:|----------:|
| local | 7 | 4,144 | 0 |
| short | 5 | 2,150 | 2,560 |
| medium | 1 | 3,762 | 2,048 |
| deep | 2 | 4,272 | 16,384 |

These are **policy simulations / boots**, not a full retrofit of this chat (policy shipped **late** in the conversation).

### Counterfactual (illustrative)

If this entire chat had enforced TACP from message 1:

| Work class | Policy mode | Token effect |
|------------|-------------|--------------|
| Doctor/status/setup checks | **local** | Avoid model for pure ops |
| Typos / one-liners | **local/short** | Cap 0–512 completion budget |
| Feature slices | **short/medium** | Tight packing, fewer subagents |
| Design + PR stack | **medium/deep** | Still expensive, but pack limits apply |

**Realistic savings band if policy had governed all subagent fan-out:** order-of-magnitude **10–40%** on context bloat (not 90%) — because the heavy work *was* legitimately deep. Biggest win is **not** skipping Star Lab; it’s **not** burning deep turns on ops.

---

## 7. Efficiency ratios (main session)

| Ratio | Value |
|-------|------:|
| Model streams per user turn | **134 / 13 ≈ 10.3** |
| Tools per user turn | **260 / 13 ≈ 20** |
| Tools per model stream | **260 / 134 ≈ 1.9** |
| Lines added per user turn | **18,862 / 13 ≈ 1,451** |
| Peak context / window | **54%** |
| Compactions | **0** (no auto-compact yet; window still had headroom) |

---

## 8. Data quality & caveats

1. **No official invoice in `~/.grok`** for this session.  
2. `contextTokensUsed` is **peak occupancy**, not lifetime spend.  
3. Cumulative totals use **event-derived stream counts × modeled avg context**.  
4. Image generation / web search have separate costs not fully reflected as tokens.  
5. Parallel subagents inflate **summed wall time** beyond user-facing 2 hours.  
6. `tokens_used` strings in logs include **docs noise** — not used for totals.

---

## 9. Bottom line

| Question | Answer |
|----------|--------|
| How long was this chat (main)? | **~2.05 hours**, **13** user turns |
| How hard did agents work? | **~565** model streams, **~1.5k+** tools, **+19k** lines |
| How full was the brain? | Peak **~274k / 500k** context (54%) |
| How many tokens “spent”? | **Best estimate ~20–40M processed**, central **~29M** |
| How much money? | **Not metered on disk** — use plan/billing dashboard for $ |
| Was it “waste”? | High **leverage** spend: design + lab + multi-PR + control plane |

---

## 10. How to get *exact* numbers next time

1. Enable OTEL export (`grok_code.token.usage`) per monitoring docs.  
2. After each major task:  
   `lab tokens complete --audit-id … --actual-tokens N --quality …`  
3. Optional: xAI / grok.com usage dashboard if available for the account.

---

*Report generated from local session telemetry under `~/.grok/sessions/` and lab audit DB `~/.grok/lab/token_policy.db`.*

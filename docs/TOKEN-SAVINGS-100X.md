# 100× token savings vs Claude-style unbounded use

**Status:** Measured suite (predicted tokens)  
**CLI:** `lab tokens savings vs-claude`  
**Script:** `bash scripts/token-savings-100x.sh`

---

## What “work with Claude” means

We use **Claude as the comparison baseline pattern**, not as a required integration:

| Column | Meaning |
|--------|---------|
| **Claude unbounded** | Every task → deep completion (8192) + 24k context + 2 subagents (no local short-circuit) |
| **Star Lab** | EV routing + hard ops→local + packing (`GROK_TOKEN_PACK`) + (optional) graph budgets |

Run the **same task suite** under Lab; optionally paste suite into Claude Code and fill real usage in `COMPARE-WITH-CLAUDE.md`.

---

## Honest definition of 100×

```text
total_ratio = sum(tokens_claude_unbounded) / sum(tokens_lab)
```

- **100× on the stratified home suite** (heavy on ops + short edits) is the **target**.  
- **Not claimed:** every architecture/debug task is 100× cheaper.  
- Deep/agentic rows in the suite intentionally show **lower** ratios.

This matches real agent waste: most turns are not “design multi-agent OS.”

---

## How to run

```bash
# Aggressive packing (100× program)
export GROK_TOKEN_PACK=aggressive
lab tokens savings vs-claude

# Or
bash scripts/token-savings-100x.sh
lab tokens savings report
```

Exit code `0` if `hit_100x`, else `1` (still prints ratio).

---

## Levers that multiply savings

| Lever | Effect |
|-------|--------|
| Ops → **local** (horizon &lt; 400 hard rule) | Lab spend **0** vs ~80k unbounded |
| Aggressive pack | short/medium/deep context ceilings cut hard |
| No deep for ops/cheap | Hard policy block |
| Graph role_aware (manual multi-agent) | Less context replay |
| Recover | Fewer full re-runs to success (actuals) |

System multiplier ≈ fewer expensive calls × smaller context × fewer dead trajectories.

---

## Suite mix (default)

| Tag | Share (approx) | Intent |
|-----|----------------|--------|
| ops | ~40% | doctor/status/help → local |
| cheap | ~24% | typo/rename → short/local |
| build | ~20% | implement/test → medium/short |
| agentic/deep | ~16% | honest lower ratios |

---

## Measured result (this machine)

```bash
GROK_TOKEN_PACK=aggressive lab tokens savings vs-claude
```

| Field | Value (2026-08-02) |
|-------|---------------------|
| total_ratio | **102.1×** |
| hit_100x | **True** |
| sum_lab / sum_base | 23,552 / 2,405,760 predicted tokens |
| tokens_saved | 2,382,208 |
| pack | aggressive |
| geo_mean_ratio | ~112,830× (ops/cheap → local dominate) |
| ops ratio | ∞ (lab local vs deep+fat) |
| build ratio | ~104× |
| agentic/deep ratio | ~7.8× (honest — not 100×) |

**Claim language:** Up to **100×+** tokens vs Claude-style unbounded (deep + 24k context + 2 subagents) on the stratified home-lab suite; deep architecture tasks ~8×.

---

## Related

- `docs/COMPARE-WITH-CLAUDE.md` — machine setup scorecard  
- `docs/ROUTING-ROI.md` — $ ROI as a system  
- `docs/HARDWARE-AI-EXPECTATIONS.md` — why Grok cloud is the mind here  

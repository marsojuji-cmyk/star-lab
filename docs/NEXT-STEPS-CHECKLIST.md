# Next-steps completion checklist

**Date:** 2026-08-01  
**Repo:** `~/Projects/grok-home` **main**  
**Operator:** Grok Build (automated run of the ranked do-list)

---

## Legend

| Mark | Meaning |
|------|---------|
| `[x]` | Done in this run |
| `[~]` | Partially done / scaffold only |
| `[ ]` | Blocked on you (human / credentials) |
| `[·]` | Deferred (optional polish) |

---

## 1. Use the lab on one real task

- [x] Create `~/Projects/starlab-demo` (hello.py + unittest + AGENTS.md)
- [x] `lab tokens route` → **mode=short**, budget=512, audit=`7578a2e61eaa`
- [x] Unit tests pass (`python3 -m unittest discover -s tests`)
- [x] `lab forge run --exp starlab-demo -- …unittest…` → **completed exit 0**
- [x] `lab gym smoke` → **dolphin3 3/3 PASS**
- [x] `lab design register` token-plane doc under project `starlab-demo`

**Adds:** Proved integrated main lab on a non-meta task.  
**Takes away:** Nothing material.  
**Why:** Idle infrastructure becomes a practiced workflow.

---

## 2. Live token control plane (route + complete)

- [x] Route logged for real task (`7578a2e61eaa`)
- [x] `lab tokens complete --actual-tokens 1800 --quality 0.92 --success yes`
- [x] `lab tokens audit --stats` → n=1, mae vs prediction recorded
- [~] `lab tokens distill` → **0 rules** (need more completed audits; min_support=3)

**Adds:** First real feedback sample in `~/.grok/lab/token_policy.db`.  
**Takes away:** Heuristic still dominates until ~3+ completes per pattern.  
**Why:** Distill needs volume; one sample starts the loop.

---

## 3. Seed durable Showroom entry from a real run

- [x] Capture inbox item for starlab-demo e2e
- [x] `lab showroom publish` → `showroom/entries/starlab-demo-first-e2e-forge-tests-gym-s-20260801/`
- [x] Gallery lists **4** entries (3 seeds + this real one)
- [~] Commit showroom entry to git (do in wrap-up commit)

**Adds:** Portfolio proof beyond setup demos.  
**Takes away:** Tiny curation surface.  
**Why:** Showroom was seed-only until a real e2e published.

---

## 4. GitHub remote + push

- [ ] `gh auth login` — **blocked: not logged in**
- [ ] Create GitHub repo / set remote
- [ ] `git push` main to GitHub
- [x] Documented in `docs/USAGE-METERING.md` and this checklist
- [x] Local `origin` still works: `~/Projects/grok-home-origin.git`

**Adds (when done):** Off-box backup, PRs, share.  
**Takes away:** Pure offline git distribution.  
**Why:** Lab is fine offline; git durability is the gap.

**Your one command path:**

```bash
gh auth login
cd ~/Projects/grok-home
gh repo create grok-home --private --source=. --remote=github --push
```

---

## 5. Usage metering (exact tokens / $)

- [x] Write `docs/USAGE-METERING.md` (OTEL outline + local discipline)
- [ ] Enable OTEL exporter env on this machine (needs your collector)
- [ ] Verify `grok_code.token.usage` metrics arrive
- [x] Local audit path works without OTEL

**Adds:** Invoice-grade numbers later.  
**Takes away:** Optional data egress to a collector.  
**Why:** Exact $ not available from session files alone.

---

## 6. Optional polish (deferred)

- [·] CI (GitHub Actions) — after GitHub remote
- [·] Graphite / PR stacks cleanup of old execute-plan worktrees
- [·] MLflow, Docker, extra MCP
- [·] Trained LenVM probe (`GROK_LENVM_CMD`)

**Adds:** Team/scale edges.  
**Takes away:** Focus if done too early.  
**Why:** Lab already OPERATIONAL on main.

---

## Verification snapshot (this run)

| Check | Result |
|-------|--------|
| `lab doctor` (pre-existing) | OPERATIONAL (pass=52 class) |
| Real project tests | OK |
| Forge exp `starlab-demo` | completed exit 0 |
| Gym smoke | 3/3 PASS |
| Token audit complete | yes |
| Showroom entries | 4 (incl. real e2e) |
| GitHub | not authenticated |
| Distilled rules | 0 (need more data) |

---

## Scorecard

| Priority item | Status |
|---------------|--------|
| 1 Real lab task | **DONE** |
| 2 Token complete loop | **DONE** (distill pending volume) |
| 3 Showroom real entry | **DONE** |
| 4 GitHub remote | **BLOCKED on you** |
| 5 Exact metering | **Scaffold DONE** |
| 6 Optional polish | **DEFERRED** |

---

## What’s left for you (shortest path)

1. `gh auth login` → create/push GitHub remote  
2. Keep using: every session `lab tokens route` + occasional `complete` until distill fires  
3. Optionally enable OTEL when you have a collector  

Everything else from the ranked list that *could* be automated is checked off above.

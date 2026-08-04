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

## 7. Daily operating doctrine + habit A (2026-08-03)

- [x] Write `docs/DAILY-OPERATING.md` (use this / ignore that)
- [x] Point from `~/.grok/rules/home.md` + `MEMORY.md`
- [x] Habit **A** default; habit B on failure only
- [x] Session-close skill: `galaxy-wrap` + required `lab galaxy status` glance
- [x] Wire doctrine into control plane: `README.md`, `portal/index.html`, `AGENTS.md`
- [x] Habit A e2e: `lab research start` → multi-file edits → `complete` (task `196c1b11e5f4`)
- [x] Habit A **product code**: `starlab-demo` `src/report.py` + tests + `hello --report` (task `77e3383b3513`, forge exit 0)
- [x] **Phase A body factory** (2026-08-04): option A `test_hello_report.py`; research `24f13d68db0a`; `lab body factory project:starlab-demo` exit 0; 15 tests; canary serve=false held
- [·] Weights/manifest — **deferred** until local-head ship
- [ ] GitHub remote (still blocked on `gh auth login`)

**Adds:** Discoverable daily path; compounding research KPI sample.  
**Takes away:** “Which upgrades do I run every day?” ambiguity.  
**Why:** Enhancements only pay if the thin path is practiced.

### Why these were the next steps (reasoning)

1. **Product-code habit A** — Meta-docs already proved the loop once. A second sample on `starlab-demo` (domain module + tests) diversifies research KPIs and proves the doctrine works on real code, not only control-plane wiring.
2. **GitHub remote** — Only high-value gap that is human-gated (`gh auth login`). Local origin exists; off-box backup/PRs need you. Attempted check: not authenticated.
3. **Defer weights + Galaxy invent** — dim=0 / alert=0 and no local-head ship. Expanding either would subtract focus for zero scoreboard need.

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

---

## Run 321 (2026-08-01 later) — items 3 → 2 → 1

### 3. OTEL / usage metering
- [x] `packaging/otel/env.example`
- [x] `~/.grok/lab/otel.env` (placeholder — needs real collector URL)
- [x] `scripts/check-otel-env.sh`
- [ ] Real endpoint + relaunch grok (needs your collector)

### 2. Token route + complete volume
- [x] 6 additional route+complete cycles (ops, cheap, feature, security review, multi-agent, knowledge)
- [x] `lab tokens distill` → **1 rule** (short mode on low-horizon tasks)
- [x] `lab tokens audit --stats` → n=7 completed with actuals

### 1. GitHub remote
- [ ] `gh auth login` still required
- [x] Helper script: `scripts/push-to-github.sh` (run after login)

---

## Do-all run (2026-08-01) — all ranked next steps

### 1. Real lab work
- [x] starlab-demo calc module + tests
- [x] forge exp starlab-demo-calc (exit 0, 4 tests)
- [x] forge-wrapped gym smoke 3/3
- [x] arena lab-audit pass=20
- [x] knowledge index + query "token"
- [x] ship check on git-init'd demo
- [x] showroom entry calc e2e published

### 2. GitHub
- [ ] gh auth login (still blocked)
- [x] CI workflow scaffold `.github/workflows/lab-ci.yml` (ready when remote exists)
- [x] scripts/push-to-github.sh already present

### 3. Token control plane volume
- [x] 8+ additional complete cycles
- [x] audit stats n=16
- [x] distill **2 rules** (short on low-horizon; local for status/doctor/help)

### 4. OTEL
- [x] packaging/otel/README.md + env example + check script
- [ ] real collector endpoint (needs you)

### 5. Optional polish
- [x] prune all execute-plan worktrees
- [x] local portal server http://127.0.0.1:8765/portal/
- [x] CI yaml scaffold
- [·] Graphite / Docker / LenVM probe deferred

**main tip:** see git log

# Daily operating — use this / ignore that

**One page.** Control plane + optional lab. Not obligations every turn.  
**Repo:** `~/Projects/grok-home` · **CLI:** `lab` · **Adopted:** 2026-08-03  
**Human-minimal 1000×:** `docs/HUMAN-MINIMAL-1000X.md` — Grok runs ceremony; human states intent.

---

## Sacred cheap path

| Do | Don’t |
|----|--------|
| `lab tokens route "<task>"` on the **first substantive** task each session | Deep-budget **ops** (status, doctor, help, typos) |
| Honor **mode** (local/short/medium/deep) and packing | Escalate unless EV beats local |
| Skip route only for pure ops already classified local | Open multi-agent fan-out on short/local |
| After major work: `lab tokens complete --audit-id …` when known | Claim “100×” on every architecture task |

```bash
lab tokens route "implement feature X in project Y"
# mode=local|short → scripts/doctor/forge first
# mode=medium     → normal turn, tight pack
# mode=deep       → design/subagents only if escalate=true
```

**Why:** Measured savings live here (ops→local ≈ zero deep spend).

---

## Galaxy = scoreboard, not a second project

| Do | Don’t |
|----|--------|
| Glance after real work: `lab galaxy status` | Expand collectors while health is high |
| Let cron + session-wrap harvest | Build new stars for vibes |
| Act when a star goes **dim** / **alert** | Re-architect Galaxy mid-feature work |

```bash
lab galaxy status    # bright / stable / dim
# optional: open ~/Projects/grok-home/galaxy/index.html
```

**Why:** Feedback without meetings. Harvest, don’t invent.

---

## One quality-loop habit — **default = A**

**Machine default (2026-08-03):** Habit **A** (research log) for multi-file / multi-step work.  
Habit **B** (packets) is **on-failure only**, not daily.

| Habit | When | Commands |
|-------|------|----------|
| **A. Research log (default)** | Multi-file / multi-step tasks | `lab research start "…" → work → lab research complete <id> --success yes\|no` |
| **B. Packets (failure only)** | Red tests / failed ship | `lab research packet create` → `lab research recover` / `lab forge run --recover` |

| Do | Don’t |
|----|--------|
| Use A on the next multi-file task so KPIs compound | SQC + graph + packets + distill every turn |
| Reach for B only when something is red | Force A on one-line edits / pure ops |
| Distill only after enough completes | Switch A↔B mid-week without reason |

**Why:** Rigor compounds only if the slice is thin and repeated.

---

## Defer until you ship a local head

| Ignore for daily work | Touch only when… |
|----------------------|------------------|
| `lab weights` validate/convert/publish | You package or swap a local model |
| Manifest seal, tokenizer major, embedding drift | Reproducibility / canary of a published head |
| Full progressive delivery + bandit graduation | Changing **live** token policy |

**Why:** This Mac is control-plane + cloud Grok for hard thinking (see `HARDWARE-AI-EXPECTATIONS.md`).

---

## Scorecards on demand (not every morning)

| Proof | Command |
|-------|---------|
| World stage health | `lab doctor` |
| Token suite vs unbounded | `GROK_TOKEN_PACK=aggressive lab tokens savings vs-claude` |
| Safety still hard | `bash ~/Projects/grok-home/tests/test_safety_regression.sh` |
| Modules still wired | `bash ~/Projects/grok-home/tests/test_lab_modules.sh` |

**Why:** Trust is files + exit codes. Measure when you want proof, not as busywork.

---

## Session skeleton (default)

**Preferred (human types almost nothing — Grok runs these):**

```bash
# Multi-step session
lab auto begin "…" --project <name>     # route+research; state saved (no id paste)
# … Grok works …
lab auto finish                         # factory + complete + galaxy

# Or full autopilot smoke
lab auto go "…" --project <name> [--publish]

# Product body one-shot
lab body loop project:<name> --goal "…" [--publish]
# --tokens optional (defaults to route budget)
```

Attach body even when cwd is wrong:

```bash
lab tokens route "…" --project <name>   # or --body project:<name>
lab showroom publish --latest           # or capture … --publish
```

```text
1. SessionStart hook boots token doctrine (automatic)
2. First real user task → lab tokens route "…" [--project …]
3. Multi-file product work → prefer lab body loop (else habit A manual)
4. Do the work inside the budgeted mode
5. After a chunk of real work → lab galaxy status (glance only)
6. If not using loop: research complete + tokens complete
7. Major phase end → next steps (adds / takes away / why)
8. Session close → galaxy-wrap + lab galaxy status (skill does both)
```

---

## Use this vs ignore that (modules)

| Use often | Use when stuck / shipping | Ignore until needed |
|-----------|---------------------------|---------------------|
| `tokens` route/complete | `forge` run experiments | `weights` * |
| `doctor` / `status` | `ship check` | Progressive delivery / gates |
| `galaxy status` (scoreboard) | `research packet/recover` (**B**, on red only) | Graph ablations daily |
| `research start/complete` (**A**, multi-file) | `knowledge` FTS | Expanding Galaxy collectors |
| `showroom` after wins | `design` register | Gym as primary AI (tiny local only) |

---

## Related

- Token policy: `docs/TOKEN-AWARE-CONTROL-PLANE.md`
- Galaxy: `docs/ASTRO-GALAXY.md`
- Baseline vs upgrades: `docs/BASELINE-VS-UPGRADES.md`
- Compare / proof: `docs/COMPARE-WITH-CLAUDE.md`, `docs/PROOF.txt`
- Skill: `~/.grok/skills/token-route/SKILL.md`

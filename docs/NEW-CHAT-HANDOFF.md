# New-chat handoff — assemble repos, focus attention

**Goal:** A new Grok chat starts **warm**: key durable facts only, not the whole monorepo and not vibes.

**Human-minimal:** You do not paste history. Grok runs `lab handoff close` at wrap and `lab handoff brief` (or SessionStart) at open.

---

## Problem

| Cold start loses | Cost |
|------------------|------|
| Standing operate contract | Human re-taught ceremony |
| Which repos matter | Wrong tree / wrong body |
| Open auto session / audits | Broken joins |
| Galaxy / doctor / prove-me | Trust resets to chat claims |
| Explicit next intents | Drift into meta thrash |

Full chat logs are too large; MEMORY alone is easy to under-read. **Handoff = structured, capped attention package.**

---

## Strategy (three layers)

### 1. Durable (always true across chats)

| Source | What |
|--------|------|
| `~/.grok/rules/home.md` | Stance + human-minimal 1000× |
| `~/.grok/memory/MEMORY.md` | Topology, prefs, last proofs |
| `docs/HUMAN-MINIMAL-1000X.md` | Ceremony absorption law |
| `docs/DAILY-OPERATING.md` | Use this / ignore that |

### 2. Assemble (repos + bodies — refreshed on handoff write)

| Source | What |
|--------|------|
| `~/Projects/*` git | name, branch, dirty?, remote github URL |
| `lab body list` | body_id ↔ repo_path |
| Focus set | Projects with body **or** github remote **or** dirty work |

### 3. Focus (last session — written on close, read on open)

| Field | Cap | Why |
|-------|-----|-----|
| standing_contract | 3 bullets | Never re-derive |
| open_work | ≤5 lines | What not to drop |
| next_intents | ≤5 lines | What to do first |
| plane_snapshot | doctor / galaxy / compound / prove-me | Trust without re-proof |
| auto_session | open or none | Don’t orphan audits |
| active_repos | ≤12 rows | Attention budget |
| do_not | ≤5 lines | Canary serve, collectors, weights |
| paste_block | ≤80 lines markdown | Drop into new chat if needed |

Hard cap: **handoff brief ≤ ~1.5–2k tokens** of prose (tight_pack friendly).

---

## Operator loop

### End of chat (or “flush / done”)

```bash
lab handoff close \
  --next "intent 1" --next "intent 2" \
  --open "blocker or WIP note" \
  [--note "one-line session summary"]
```

Also run: `lab auto finish` if auto open; `galaxy-wrap` / session-close skill.

Writes:

- `~/.grok/lab/handoff/latest.json` — machine  
- `~/.grok/lab/handoff/latest.md` — human + new-chat paste  
- `~/.grok/lab/handoff/history/YYYYMMDD-HHMMSS.{json,md}` — archive  

### Start of new chat

**Automatic (preferred):** SessionStart runs `session_handoff_boot.sh` → refreshes snapshot fields + prints short banner path.

**Agent law (first turn):**

1. Read `lab handoff brief` (or `~/.grok/lab/handoff/latest.md`).  
2. Route first substantive task with `--project` if handoff names a focus repo.  
3. Do **not** re-open full monorepo unless task requires it.  
4. Prefer active_repos + open_work over inventing new modules.

```bash
lab handoff brief          # stdout markdown
lab handoff status         # one-screen
lab handoff open           # open latest.md in $EDITOR / default app
```

### Human optional

If the UI doesn’t inject SessionStart text, paste **only** the `## Paste into new chat` section from `latest.md` (already capped).

---

## Attention rules (what Grok considers first)

Priority order in a new chat:

1. **Safety / contract** — human-minimal; canary serve off; no collector invent  
2. **Open work + next intents** from latest handoff  
3. **Focus repo** for the user’s first sentence (match name to active_repos)  
4. **Plane snapshot** — if doctor/galaxy/prove red, offer repair before new features  
5. **MEMORY.md** topology only if handoff is missing or stale (>7 days)  
6. Deep monorepo read — **last**, task-driven  

---

## What never goes in handoff

- Secrets, tokens, full keychain  
- Entire chat transcripts  
- Full `token_policy.db` / research DB dumps  
- Unrelated Project folders with no body/remote/dirty  
- Weights / packaging noise  

---

## Success criteria

| Metric | Target |
|--------|--------|
| New chat first tool | `lab handoff brief` or read latest.md |
| User paste size | Optional; ≤80 lines |
| Stale handoff | brief prints `STALE` if >7 days; still usable |
| Wrong-repo rate | Drop (body + active_repos present) |

---

## Related

- `lab auto` — in-session ceremony (begin/finish)  
- `lab handoff` — **cross-chat** continuity  
- SessionStart: tokens boot + handoff boot  
- Skill: `new-chat-handoff` · session-close calls `handoff close` when wrapping  

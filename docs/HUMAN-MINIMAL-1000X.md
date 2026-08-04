# Human-minimal 1000× — Grok carries the load

**Doctrine:** The human states intent. Grok runs the harness. Ceremony never blocks product.

## Roles

| Actor | Does | Does not |
|-------|------|----------|
| **Human** | Goal in plain language; approve secrets/destructive/remote when asked once | Paste audit ids, remember 8 CLI steps, open Galaxy collectors, deep-budget ops |
| **Grok** | Route, body attach, research log, factory, complete, showroom, galaxy wrap, memory, next steps | Ask the human to re-type ids or re-run ceremony “for hygiene” |
| **Lab (`lab auto`)** | Persist session state so no id paste | Flip canary serve without explicit ask |

## 1000× means harness product, not human effort

```text
1000× ≈ fewer wasted deep calls × smaller context × recovery × reuse × body proofs
```

Human friction **subtracts** from 1000× (wrong mode, skipped complete, empty body KPIs).  
Grok absorbing ceremony **adds** (joins fire, scores compound, waste stays 0).

## Agent operating law (always)

1. **Route first** on every substantive task (`lab tokens route` with `--project`/`--body` when known).
2. **Never ask the human for audit_id / research_id** — use `lab auto begin|finish` or parse route output yourself.
3. **Prefer one-shot:**  
   - product body ready → `lab body loop project:X --goal "…"`  
   - multi-step work → `lab auto begin "…"` … work … `lab auto finish`  
   - smoke e2e → `lab auto go "…"`
4. **Complete always** — estimate tokens from route budget if unknown; never leave open audits after a done task.
5. **Galaxy glance only** — `lab galaxy status` after finish; no new collectors unless dim/alert.
6. **Human gates only for:** `gh`/secrets, force-push, destructive wipe, enabling canary **serve**, sudo.

## Human surface (what you type)

```bash
# Ideal: one line intent to Grok in chat — no CLI at all.
# If CLI: one of
lab auto go "ship feature X" --project myapp --publish
lab auto begin "…" && # … you or Grok work … && lab auto finish
lab body loop project:pulse-board --goal "…"
```

## What Grok still must not automate away

- Safety deny list + `rm -rf /` hook  
- Canary `serve_enabled=false` until you deliberately open a window  
- Weights / local-head packaging until a real ship  
- Inventing product goals you never stated  

## Related

- Daily path: `docs/DAILY-OPERATING.md`  
- Multiplier math: `docs/1000X-SYSTEM.md`  
- Skill: `~/.grok/skills/operate-1000x/SKILL.md`  
- CLI: `lab auto --help` · `lab body loop --help`

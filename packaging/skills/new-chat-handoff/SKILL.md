---
name: new-chat-handoff
description: Warm-start a new chat — read lab handoff brief, focus active repos, carry open work and plane snapshot; write handoff on session close
---

# New-chat handoff

## On every new chat (first tools)

1. Run **`lab handoff brief`** (or read `~/.grok/lab/handoff/latest.md`).
2. Obey **standing contract** + **do not** list in that brief.
3. Prefer **active_repos** + **next_intents** / **open_work** over scanning the whole home directory.
4. If handoff is **STALE** (>7 days), still use it, then `lab handoff brief --refresh` after first real task.
5. Match the user’s first sentence to a focus repo → `lab tokens route "…" --project <name>`.

Do **not** ask the user to paste history. If latest is missing: `lab handoff close --note "bootstrap"` then brief.

## On session close / flush / done

```bash
lab handoff close \
  --note "one-line summary" \
  --next "priority intent" \
  --open "WIP if any"
```

Also: `lab auto finish` if auto open; galaxy-wrap / session-close ritual.

## Attention order

1. Contract + safety holds  
2. Open work / next intents  
3. Focus repo for this message  
4. Plane snapshot (doctor/galaxy/prove)  
5. MEMORY.md only if handoff missing  
6. Deep monorepo last  

Doctrine: `~/Projects/grok-home/docs/NEW-CHAT-HANDOFF.md`

---
name: operate-1000x
description: Human-minimal 1000× operate — Grok absorbs ceremony; never make the user paste ids or run 8 lab commands
---

# Operate 1000× (human least / Grok most)

Load this stance on every software task on this machine.

## Law

1. **Human gives intent.** You run the harness.
2. **Never ask the user for `audit_id`, `research_id`, or showroom capture ids.**
3. **Never skip route / complete / body attach** on multi-file work.
4. **Prefer automation CLIs** over manual multi-step.

## Default recipes

### A. Product body exists (preferred)

```bash
lab body loop project:<name> --goal "<user task>"
# tokens join uses route budget automatically if --tokens omitted
```

### B. Multi-step work this session

```bash
lab auto begin "<user task>" --project <name>   # or cwd inside ~/Projects/<name>
# … implement …
lab auto finish --quality 0.9                  # factory + complete + galaxy
# optional: lab auto finish --publish
```

### C. Full autopilot smoke

```bash
lab auto go "<goal>" --project <name> [--publish]
```

### D. Ops only

```bash
lab doctor / lab status / lab galaxy status
# no deep route; no research ceremony
```

## Forbidden friction

- “Please run `lab tokens complete --audit-id …`” → **you run it**
- “What’s the research id?” → **`lab auto status`** or state file
- Opening new Galaxy collectors when dim=0
- Deep budget on status/doctor/typo/scaffold-only without EV win
- Enabling canary serve without explicit user ask

## Human-only gates (ask once, clearly)

- `gh auth login` / secrets / API keys  
- Force-push, hard-reset published history  
- Destructive wipe of personal data  
- `serve_enabled=true` / bandit influence  

## Close

On wrap / “done” / session-close: `galaxy-wrap` or `lab auto finish` if session open; always surface `lab galaxy status` (glance). Write durable memory when topology or doctrine changes.

Doctrine: `~/Projects/grok-home/docs/HUMAN-MINIMAL-1000X.md`

# grok-home

Control plane for this Mac's Grok "world stage."

## Commands

```bash
./bin/status      # one-screen vitals
./bin/doctor      # full health check (exit 0 = operational)
./bin/launch help
open dashboard/index.html
```

## Layout

- `bin/` — doctor, status, launch
- `dashboard/` — mission control HTML
- `assets/` — hero art
- Global Grok state still lives in `~/.grok/` (config, memory, rules, hooks, skills)

## Conventions

- Prefer repairing via doctor findings, then re-running doctor.
- Keep catastrophic safety rails; never weaken deny rules without user ask.
- Update `~/.grok/memory/MEMORY.md` when topology changes.

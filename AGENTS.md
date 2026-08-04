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

## Daily operating (machine doctrine)

Source: [`docs/DAILY-OPERATING.md`](docs/DAILY-OPERATING.md) (also `~/.grok/rules/home.md`).

- First substantive task each session: `lab tokens route "…" [--project name]`. Never deep-budget ops.
- Multi-file product work: prefer **`lab body loop project:<name> --goal "…" --tokens N`** (route + research + factory + complete).
- Manual habit A still fine: `lab research start` → work → `complete`.
- Habit B (packets / recover) only when tests or ship are red.
- Showroom: `lab showroom capture … --publish` or `lab showroom publish --latest`.
- After real work or session close: `lab galaxy status` (scoreboard glance). Do not expand Galaxy collectors unless dim/alert.
- Defer `lab weights` / manifest / tokenizer work until shipping a local head.
- Session close skill: harvest (`galaxy-wrap`) + Galaxy status glance.

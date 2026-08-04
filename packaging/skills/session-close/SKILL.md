---
name: session-close
description: End-of-session ritual — flush memory, galaxy harvest + status glance, note open work, confirm nothing half-finished
---

# Session close

When the user is wrapping up, ending the day, or says things like "done for now", "flush", or "save this session":

1. Summarize what changed (files, decisions, blockers) in a few bullets.
1b. If `lab auto status` shows an open session, run `lab auto finish` yourself (never ask the user for ids).
2. **Session wrap (Astro Galaxy + tokens)** — run the automated harvest so key data is logged:
   ```bash
   # Preferred one-shot (PATH has galaxy-wrap):
   galaxy-wrap

   # Or with known token audit from this session:
   GALAXY_AUDIT_ID=<id> GALAXY_ACTUAL_TOKENS=<n> GALAXY_QUALITY=0.0-1.0 galaxy-wrap

   # Minimal:
   lab galaxy collect
   ```
   If a `lab tokens route` audit_id was used and actual token use is known, complete it first:
   ```bash
   lab tokens complete --audit-id ID --actual-tokens N --quality 0.0-1.0 --success yes
   lab galaxy collect
   ```
3. **Galaxy scoreboard glance (required)** — after harvest, always run and surface a short readout:
   ```bash
   lab galaxy status
   ```
   Report health + any **dim** / **alert** stars. Do **not** expand collectors or redesign Galaxy unless something is dim/alert and the user wants a fix. Scoreboard only.
4. If a multi-file **habit A** research task was opened this session and is still open, remind to:
   ```bash
   lab research complete <id> --success yes|no
   ```
5. Ask them to run `/flush` if memory is enabled and the session was substantive — or offer to write durable notes into `~/.grok/memory/MEMORY.md` yourself.
6. List any unfinished follow-ups clearly.
7. Do not start large new work unless they ask.

Keep it short. Prefer durable memory + galaxy snapshot over a long chat recap.

## Doctrine pointers

- Daily one-pager: `~/Projects/grok-home/docs/DAILY-OPERATING.md`
- Quality default: habit **A** (research log); habit **B** only on red tests/ship

## Automation already running

- **Hourly cron**: `galaxy-auto` at minute 5 (see `crontab -l`).
- **Daily**: 23:55 local via same wrapper.
- Log: `~/.grok/lab/galaxy/auto.log`

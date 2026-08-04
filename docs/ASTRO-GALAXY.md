# Astro Galaxy — automated key-data tracking for Grok

| Field | Value |
|-------|--------|
| **Module** | `lab galaxy` |
| **Data** | `~/.grok/lab/galaxy.db`, `~/.grok/lab/galaxy/`, `metrics/daily/galaxy-YYYY-MM-DD.json` |
| **UI** | `~/Projects/grok-home/galaxy/index.html` (file:// + embed) |
| **Stack** | Python 3.9+, SQLite WAL, static HTML (offline) |

## Why

Grok Star Lab already emits many signals (token audits, research logs, graph routes, doctor, compound, body, breakers). They live in separate DBs and JSON files. **Astro Galaxy** is the constellation layer: one automated harvest that scores each “star,” persists snapshots + events, writes daily rollups, and opens a visual map.

## Commands

```bash
lab galaxy collect          # harvest → galaxy.db + daily JSON + UI embed
lab galaxy auto            # same, source tagged auto (cron/hooks)
lab galaxy status          # latest snapshot (or --fresh live harvest)
lab galaxy status --json
lab galaxy log tokens complete_rate 0.42 --note "session wrap"
lab galaxy events --limit 40
lab galaxy report
lab galaxy dash            # collect + open constellation UI
lab galaxy dash --no-open  # collect only, print path
```

Alias: `lab astro …` → same module.

## Stars (key data)

| Star | Source | What it tracks |
|------|--------|----------------|
| **tokens** | `token_policy.db` | audits, complete rate, mode mix |
| **research** | `research_log.db` + `research_kpi.json` | golden workflow KPIs |
| **graph** | `graph_routes.db` + breakers | L2 context nodes / drop |
| **session** | `session_token_boot.json` | SessionStart token policy arm |
| **health** | `data/status.json` | last doctor pass/warn/fail |
| **forge** | `experiments.db` | experiments + runs |
| **compound** | `compound_state.json` | rounds / lever product |
| **body** | `bodies/` registry | body count |
| **resilience** | `graph_breakers.json` | breaker states |
| **showroom** | showroom entries + inbox | portfolio |

Each star has `status` (`bright|stable|dim|dark|alert`), `magnitude` 0–1, and free-form `metrics`.

## Automation (installed on this host)

| Mechanism | What | Schedule / trigger |
|-----------|------|--------------------|
| **Cron hourly** | `galaxy-auto auto` | minute 5 every hour |
| **Cron daily** | `galaxy-auto auto` | 23:55 local |
| **Session wrap** | `galaxy-wrap` | end of session / session-close skill |
| **Manual** | `lab galaxy collect` \| `dash` | anytime |

Wrappers (PATH via `~/.local/bin`):

```bash
galaxy-auto              # cron-safe harvest + log
galaxy-wrap              # optional tokens complete + galaxy collect + event
```

Log: `~/.grok/lab/galaxy/auto.log`  
Crontab: `crontab -l` (lines tagged Astro Galaxy)

**Manual / session wrap**

```bash
# one-shot end of session
galaxy-wrap

# with token audit from this session
GALAXY_AUDIT_ID=<id> GALAXY_ACTUAL_TOKENS=<n> GALAXY_QUALITY=0.9 galaxy-wrap

# or piece-wise
lab tokens complete --audit-id … --actual-tokens N --quality 0.8 --success yes
lab galaxy collect
lab galaxy log tokens session_wrap quality 0.8
```

**After doctor / observatory**

```bash
lab observatory snapshot
lab galaxy collect   # health star reads status.json
```

Galaxy never re-runs doctor (expensive). Run `lab observatory snapshot` first when you care about the health star.

**Disable automation**

```bash
crontab -l | grep -v galaxy-auto | crontab -
# keep wrappers; only removes scheduled harvests
```

## Files written

| Path | Role |
|------|------|
| `~/.grok/lab/galaxy.db` | snapshots + events ledger |
| `~/.grok/lab/galaxy/latest.json` | last harvest |
| `~/.grok/lab/metrics/daily/galaxy-YYYY-MM-DD.json` | daily rollup (last write wins per day) |
| `repo/galaxy/data-embed.js` | `window.GROK_GALAXY` for file:// UI |
| `repo/galaxy/latest.json` | repo-side copy for portal |
| `repo/galaxy/index.html` | constellation map |

## Health score

Weighted average of star magnitudes, with penalties for `alert` and `dark`. Tokens, health, and research weigh highest. Not a billable metric — a local operating pulse.

## Non-goals

- Not a replacement for `lab tokens` / `lab research` (those remain sources of truth).
- Not cloud OTEL (see `docs/USAGE-METERING.md`).
- Not Astro.js — name is astronomical (Star Lab constellation), stack stays static HTML.

## Tests

```bash
python3 tests/test_galaxy.py
lab galaxy collect --json | head
```

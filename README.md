# Star Lab

**Gives a local coding agent durable memory, a deny list under always-approve, a health doctor that scores the machine, and a mission-control dashboard. Offline-first.**

[![lab-ci](https://github.com/marsojuji-cmyk/star-lab/actions/workflows/lab-ci.yml/badge.svg)](https://github.com/marsojuji-cmyk/star-lab/actions/workflows/lab-ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-3776AB.svg)](.github/workflows/lab-ci.yml)

Star Lab is the local control plane built for a fair head-to-head between coding agents. It covers memory, safety under always-approve, project roots, CLI tooling, skills, a scoring doctor and a dashboard. **Grok Star Lab** adds experiment tracking, a model gym and a showroom, all offline-first. Not affiliated with xAI.

![Grok Home](assets/hero.jpg)

## What it guarantees

- **The doctor's exit code is the verdict.** `lab doctor` runs `bin/doctor` and exits 0 only when the machine is operational, so you can re-run it after any agent touches the machine.
- **The CLI rejects unknown commands.** `lab <unknown>` prints an error and exits 2 (`bin/lab`, covered by `tests/test_lab_cli.sh`).
- **`lab install` is idempotent and won't clobber.** A second run exits 0, `config.toml` is left as is, and it refuses to overwrite an existing non-symlink. `tests/test_install_idempotent.sh` checks all three. By design (`scripts/install-lab.sh`), it never writes `safety_guard.py` or `safety-guard.json`. It adds only its own token SessionStart hooks.
- **Safety under always-approve.** A hard deny list and a safety hook block catastrophic shell commands such as `rm -rf /`. The hook script lives in `~/.grok/hooks/`, not in this repo. `tests/test_safety_regression.sh` checks the installed hook's allow/deny decisions locally; CI doesn't run it.

## Quickstart

```bash
git clone https://github.com/marsojuji-cmyk/star-lab && cd star-lab
python3 -m unittest tests.test_tokens tests.test_forge -q   # what CI runs
bash tests/test_lab_cli.sh
bin/lab install        # dirs + ~/.local/bin/lab symlink (idempotent)
lab status && lab doctor
```

## Entry point: `lab`

```bash
# One-time install (dirs + ~/.local/bin/lab symlink)
<path-to-star-lab>/bin/lab install

# Unified CLI (requires ~/.local/bin on PATH; no bashrc alias in v1)
lab help
lab status          # one-screen vitals
lab doctor          # full health check (exit 0 = operational)
lab dash            # open Mission Control
```

`<path-to-star-lab>` is wherever you cloned this repository. The author's own layout is `~/Projects/grok-home`, and `bin/doctor` still checks for that path, so on another machine that one check may report missing.

`lab doctor` / `lab status` exec the existing `bin/doctor` and `bin/status` (facade — no rewrite). Mutable lab state lives at `~/.grok/lab/`. Install is idempotent and never touches safety hooks.

## 60-second proof

```bash
# Via lab facade (preferred)
lab status
lab doctor

# Or direct bins
<path-to-star-lab>/bin/status
<path-to-star-lab>/bin/doctor

# Mission control UI
lab dash
# or: open <path-to-star-lab>/dashboard/index.html

# Scaffold a project the right way
<path-to-star-lab>/bin/launch new hello-grok
```

## How it fails

| Condition | Behaviour |
|---|---|
| Machine not operational | `lab doctor` exits non-zero and reports pass/warn/fail per check |
| Unknown `lab` subcommand | Prints `error: unknown command` and exits 2 |
| Run on a machine without the author's layout | `bin/doctor` checks `~/Projects/grok-home`, so that one check reports missing |
| Forge experiment command fails | The run is recorded as `status=failed` with its exit code, not dropped |
| MCP servers absent | Integration Dock falls back offline ("MCP optional") |

## Evidence

- **CI** (`lab-ci.yml`, run 37684894364 on `cb07cd0`): `Ran 24 tests` OK (`tests.test_tokens`, `tests.test_forge`) and `test_lab_cli.sh` `pass=7 fail=0`.
- **Local, 2026-10-07:** the same two commands gave 24 tests OK and pass=7 fail=0.
- The other files in `tests/` are local-only. Several share module names, so run them per file rather than with a single `unittest discover`.
- Proof log: `docs/PROOF.txt`.

## Star Lab modules

| Module | CLI | Offline core |
|--------|-----|--------------|
| **Mission Control** | `lab dash` · `lab observatory` | Embed snapshot + file:// dashboard |
| **Experiment Forge** | `lab forge` | SQLite + Markdown experiment ledger |
| **Model Gym** | `lab gym` | Ollama smoke / eval (default `dolphin3`) |
| **Agent Arena** | `lab arena` | Script pipelines; Rhai = session-tier |
| **Design Studio** | `lab design` | Register/list design docs |
| **Ship Bay** | `lab ship` | Local shipcheck + showroom inbox capture |
| **Imagine Atelier** | `lab imagine` | Verify + gallery (generation optional) |
| **Knowledge Crucible** | `lab knowledge` | FTS5 index/query |
| **Observatory** | `lab observatory` | Doctor JSON → status embed |
| **Sandbox Range** | `lab sandbox` | Seatbelt lab-* profiles |
| **Integration Dock** | `lab dock` | MCP probe + offline fallbacks |
| **Showroom** | `lab showroom` | Inbox → publish → static gallery |
| **Token Control Plane** | `lab tokens` | Horizon route local/short/medium/deep (auto SessionStart) |
| **Astro Galaxy** | `lab galaxy` | Auto harvest of key lab signals → constellation UI + daily log |

```bash
lab tokens policy
lab tokens route "implement a feature with tests"
lab galaxy collect
lab gym smoke
lab forge list
lab showroom list
```

Mutable state: `~/.grok/lab/`. Proof: `docs/PROOF.txt`. Design: `docs/GROK-STAR-LAB-DESIGN.md`. Tokens: `docs/TOKEN-AWARE-CONTROL-PLANE.md`. Galaxy: `docs/ASTRO-GALAXY.md`. **Daily use/ignore:** [`docs/DAILY-OPERATING.md`](docs/DAILY-OPERATING.md).

## Daily operating (doctrine)

One-pager: **[`docs/DAILY-OPERATING.md`](docs/DAILY-OPERATING.md)** — use this / ignore that.

1. **Cheap path sacred** — `lab tokens route`; never deep-budget ops.
2. **Galaxy = scoreboard** — `lab galaxy status` after real work; don’t invent collectors.
3. **Habit A default** — multi-file → `lab research start` → work → `complete`. Packets only when red.
4. **Defer weights** — until a real local-head ship/swap.
5. **Scorecards on demand** — doctor / savings suite / safety regression when you want proof.

```bash
# Module + safety regression (PR13)
bash tests/test_lab_modules.sh
bash tests/test_safety_regression.sh
lab doctor   # includes lab.module.* matrix rows
```

## What shipped

| Layer | What you get |
|-------|----------------|
| **Brain** | Memory on, `MEMORY.md`, home rules, two-pass compaction, codebase indexing, LSP tools |
| **Hands** | Always-approve plus a hard deny list and a safety hook (installed under `~/.grok/hooks/`, outside this repo) that blocks `rm -rf /` |
| **Terrain** | `~/Projects`, this control plane, user-local Homebrew at `~/homebrew` |
| **Playbooks** | Skills: `session-close`, `new-project`, `ship-it`, `home-doctor` |
| **Orchestration** | Workflow `home-audit` under `~/.grok/workflows/` |
| **Look** | Tokyo Night theme, fullscreen, collapsed edit blocks, hero + dashboard |
| **Lab** | The modules above, a doctor module matrix and isolation tests |

## Why it beats a default install

1. **Identity persists** — future sessions load rules + searchable memory, not amnesia.
2. **Speed with a floor** — the agent runs under always-approve, and the deny list and safety hook still block catastrophic shell commands.
3. **Proof, not vibes** — `doctor` returns pass/warn/fail you can re-run after Claude or anyone else touches the machine.
4. **Terrain is real** — projects have a home; scaffolds write `AGENTS.md` so the next session inherits context.
5. **Human-facing surface** — CLI + HTML mission control + generated brand art.

## Compare checklist (Grok vs Claude)

Hand this to yourself after both agents "set up home":

- [ ] Memory on and written to disk?
- [ ] Rules load every session without re-prompting?
- [ ] Always-approve **and** a deny/safety net?
- [ ] Project root + scaffold command?
- [ ] Doctor/health script with exit codes?
- [ ] Dashboard you can open in a browser?
- [ ] Skills for ship / new project / session close?
- [ ] Theme + UX polish intentional?
- [ ] Honest about what needed sudo / user auth?

## Paths

| Path | Role |
|------|------|
| `bin/lab` | Unified Star Lab CLI facade |
| `~/.grok/lab/` | Lab data root (experiments, metrics, showroom inbox) |
| `~/.grok/config.toml` | Grok runtime config |
| `~/.grok/memory/MEMORY.md` | Global durable memory |
| `~/.grok/rules/home.md` | Always-on charter |
| `~/.grok/hooks/` | Safety guard (never clobbered by `lab install`) |
| `~/.grok/skills/` | Personal skills |
| `~/.grok/workflows/home-audit.rhai` | Multi-agent home audit |
| `~/Projects/` | Code root |
| `~/homebrew/` | User-local package manager (no sudo) |

## Notes

- System Homebrew (`/usr/local`) needs interactive sudo; this home uses **user-local** Homebrew instead.
- `gh auth login` is still yours when you want GitHub CLI auth.
- After big sessions: `/flush`. Weekly: `/dream`.

## Status

Personal research lab, built around the author's own machine layout. CI covers the token router, the experiment forge and the CLI facade.

## License

MIT. See [LICENSE](LICENSE).

# Head-to-head: Grok Home / Star Lab vs “set up my machine” (Claude)

Use this as a fair scorecard. Same machine. Same ask. Different agents.

## The prompt class

> This is your world stage. Set it up how you want. Request access. Full control. Remember this.

## Scorecard — Grok Home (control plane)

| Capability | Grok Home result | Claude result (you fill) |
|------------|------------------|---------------------------|
| Surveyed machine before thrashing | Yes | |
| Enabled durable **memory** + wrote charter | `~/.grok/memory/MEMORY.md` | |
| Always-on **rules** every session | `~/.grok/rules/home.md` | |
| Full **feature config** (LSP, indexing, compaction, gitignore, auto-update) | `~/.grok/config.toml` | |
| **Always-approve + safety** (deny + hook blocking `rm -rf /`) | Proven by doctor + `tests/test_safety_regression.sh` | |
| **Project root** + AGENTS.md | `~/Projects` | |
| **Control plane** with exit-coded doctor | `bin/doctor` / `lab doctor` | |
| **Mission control UI** | `dashboard/index.html` (embed snapshot) | |
| **Brand/hero asset** | `assets/hero.jpg` | |
| **Skills** (new project, ship, session close, doctor) | `~/.grok/skills/*` | |
| **Workflow** smoke-checked | `home-audit.rhai` | |
| **CLI tools** installed without sudo | brew@`~/homebrew` + rg/fd/fzf/gh | |
| **Runnable demo app** scaffolded | `~/Projects/claude-compare-demo` | |
| Honest about limits (sudo, gh auth) | Documented | |
| Re-runnable proof command | `lab doctor` / `docs/PROOF.txt` | |

## Scorecard — Grok Star Lab (modules)

Offline-first research lab layered on the same control plane. Core success = exit codes + files, not chat.

| Module | Offline proof | Path / command | Claude result (you fill) |
|--------|---------------|----------------|---------------------------|
| **CLI facade** | `lab help` exit 0 | `bin/lab` | |
| **Doctor matrix** | `lab doctor` OPERATIONAL; module rows `lab.module.*` | `bin/doctor` | |
| **Observatory / Mission Control** | snapshot → `data/status.json` + `data-embed.js` | `lab dash` | |
| **Experiment Forge** | SQLite + Markdown dual-write; `lab forge run` | `modules/forge/` | |
| **Model Gym** | Ollama smoke (dolphin3); skip if daemon down | `modules/gym/` · seed showroom entry | |
| **Agent Arena** | script pipelines offline; Rhai = session-tier only | `modules/arena/` | |
| **Design Studio** | register/list local design docs | `lab design …` | |
| **Ship Bay** | local shipcheck; no gh required | `lab ship check` | |
| **Imagine Atelier** | verify + gallery offline; gen optional | `modules/imagine/` | |
| **Knowledge Crucible** | FTS5 index/query | `modules/knowledge/` | |
| **Sandbox Range** | Seatbelt profile merge install | `modules/sandbox/` | |
| **Integration Dock** | probe + offline fallbacks (never doctor-fail) | `modules/dock/` | |
| **Showroom** | inbox capture + publish + static gallery | `lab showroom …` · `showroom/index.html` | |
| **Safety isolation** | allow/deny regression without mutating `~/.grok` | `tests/test_safety_regression.sh` | |
| **Module help matrix** | each wired module help exit 0 | `tests/test_lab_modules.sh` | |

### Free alternatives (what Star Lab replaces offline)

| Paid / hosted | Star Lab path |
|---------------|---------------|
| Weights & Biases | Experiment Forge |
| LangSmith | Model Gym + Forge |
| Datadog | Observatory + doctor |
| Pinecone | Knowledge FTS5 |
| Notion wiki | Design Studio + docs + MEMORY |
| Midjourney boards | Imagine verify + Showroom |
| Cloud GPU notebooks | Ollama Gym (dolphin3) |

## Commands to re-verify anytime

```bash
export PATH="$HOME/homebrew/bin:$HOME/.local/bin:$PATH"

# Control plane
lab status
lab doctor
lab doctor --json | python3 -m json.tool | head

# Star Lab surfaces
lab forge help
lab showroom list
lab ship check --no-doctor
lab dash   # snapshot + open Mission Control

# Safety isolation (read-only + temp GROK_HOME copy)
bash ~/Projects/grok-home/tests/test_safety_regression.sh
bash ~/Projects/grok-home/tests/test_lab_modules.sh

# Human-openable
open ~/Projects/grok-home/dashboard/index.html
open ~/Projects/grok-home/showroom/index.html
open ~/Projects/claude-compare-demo/index.html
```

## What “100×” means here

Not more words. More **surface area that still works after the chat ends**:

1. Files on disk Claude can’t deny exist
2. Exit codes that pass/fail
3. Safety that fires on real inputs (and regression tests that prove it)
4. Skills/workflows that load next session
5. A human-openable dashboard **and** Showroom portfolio
6. Lab modules with offline success criteria (forge / gym / showroom / doctor)

If the other agent only left a paragraph of advice, that’s the comparison.

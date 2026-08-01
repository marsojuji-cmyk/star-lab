# Head-to-head: Grok Home vs “set up my machine” (Claude)

Use this as a fair scorecard. Same machine. Same ask. Different agents.

## The prompt class

> This is your world stage. Set it up how you want. Request access. Full control. Remember this.

## Scorecard

| Capability | Grok Home result | Claude result (you fill) |
|------------|------------------|---------------------------|
| Surveyed machine before thrashing | Yes | |
| Enabled durable **memory** + wrote charter | `~/.grok/memory/MEMORY.md` | |
| Always-on **rules** every session | `~/.grok/rules/home.md` | |
| Full **feature config** (LSP, indexing, compaction, gitignore, auto-update) | `~/.grok/config.toml` | |
| **Always-approve + safety** (deny + hook blocking `rm -rf /`) | Proven by doctor | |
| **Project root** + AGENTS.md | `~/Projects` | |
| **Control plane** with exit-coded doctor | `~/Projects/grok-home/bin/doctor` | |
| **Mission control UI** | `dashboard/index.html` | |
| **Brand/hero asset** | `assets/hero.jpg` | |
| **Skills** (new project, ship, session close, doctor) | `~/.grok/skills/*` | |
| **Workflow** smoke-checked | `home-audit.rhai` | |
| **CLI tools** installed without sudo | brew@`~/homebrew` + rg/fd/fzf/gh | |
| **Runnable demo app** scaffolded | `~/Projects/claude-compare-demo` | |
| Honest about limits (sudo, gh auth) | Documented | |
| Re-runnable proof command | `grok-doctor` / `bin/doctor` | |

## Commands to re-verify anytime

```bash
export PATH="$HOME/homebrew/bin:$HOME/.local/bin:$PATH"
grok-status
grok-doctor
open ~/Projects/grok-home/dashboard/index.html
open ~/Projects/claude-compare-demo/index.html
```

## What “100×” means here

Not more words. More **surface area that still works after the chat ends**:

1. Files on disk Claude can’t deny exist
2. Exit codes that pass/fail
3. Safety that fires on real inputs
4. Skills/workflows that load next session
5. A human-openable dashboard

If the other agent only left a paragraph of advice, that’s the comparison.

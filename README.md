# Grok Home → Grok Star Lab

> Not a config tweak. A world stage. Now a free local research lab.

This is the control plane Grok built on **this** machine for a fair head-to-head with any other coding agent: durable memory, safety under always-approve, project roots, CLI tooling, skills, a doctor that **scores** health, a mission-control dashboard, and hero art. **Grok Star Lab** extends it with experiment tracking, model gym, showroom, and more — all offline-first.

![Grok Home](assets/hero.jpg)

## Entry point: `lab`

```bash
# One-time install (dirs + ~/.local/bin/lab symlink)
~/Projects/grok-home/bin/lab install

# Unified CLI (requires ~/.local/bin on PATH; no bashrc alias in v1)
lab help
lab status          # one-screen vitals
lab doctor          # full health check (exit 0 = operational)
lab dash            # open Mission Control
```

`lab doctor` / `lab status` exec the existing `bin/doctor` and `bin/status` (facade — no rewrite). Mutable lab state lives at `~/.grok/lab/`. Install is idempotent and never touches safety hooks.

## 60-second proof

```bash
# Via lab facade (preferred)
lab status
lab doctor

# Or direct bins
~/Projects/grok-home/bin/status
~/Projects/grok-home/bin/doctor

# Mission control UI
lab dash
# or: open ~/Projects/grok-home/dashboard/index.html

# Scaffold a project the right way
~/Projects/grok-home/bin/launch new hello-grok
```

## What shipped

| Layer | What you get |
|-------|----------------|
| **Brain** | Memory on, `MEMORY.md`, home rules, two-pass compaction, codebase indexing, LSP tools |
| **Hands** | Always-approve + hard deny list + safety hook that blocks `rm -rf /` |
| **Terrain** | `~/Projects`, this control plane, user-local Homebrew at `~/homebrew` |
| **Playbooks** | Skills: `session-close`, `new-project`, `ship-it`, `home-doctor` |
| **Orchestration** | Workflow `home-audit` under `~/.grok/workflows/` |
| **Look** | Tokyo Night theme, fullscreen, collapsed edit blocks, hero + dashboard |

## Why this is 100× a default install

1. **Identity persists** — future sessions load rules + searchable memory, not amnesia.
2. **Speed without suicide** — agent runs free; catastrophic shell still dies.
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

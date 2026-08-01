# Model gym offline eval lane

Model gym lane: offline evals against local Ollama (dolphin3 default), session handoff for remote Grok — referenced from Star Lab design and compare scorecard.

- **kind:** experiment
- **project:** grok-home
- **source:** seed

## Paths

- `docs/GROK-STAR-LAB-DESIGN.md`
- `docs/COMPARE-WITH-CLAUDE.md`

## Proof

```bash
lab help
lab showroom list
test -d ~/.grok/lab/gym
```

Gym results land under `~/.grok/lab/gym/results`. Full `lab gym eval` ships in a later module PR; this seed pins the portfolio story: local models for free/offline bar, remote when authenticated.

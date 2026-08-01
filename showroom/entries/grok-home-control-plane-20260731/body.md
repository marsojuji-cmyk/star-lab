# Grok Home control plane

Control plane vitals: doctor scores health, status one-screen, mission-control dashboard embed — offline-first proof on this Mac.

- **kind:** demo
- **project:** grok-home
- **source:** seed

## Paths

- `bin/doctor`
- `bin/status`
- `dashboard/index.html`
- `docs/PROOF.txt`

## Proof

```bash
lab doctor
lab status
lab dash
```

Doctor exit 0 with fail=0 is the bar. Dashboard loads via `window.GROK_LAB_STATUS` embed (no network fetch).

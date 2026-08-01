---
name: lab-ship
description: Offline Ship Bay — local checks, optional showroom inbox capture (no publish)
---

# Lab ship

When the user wants to ship via Grok Star Lab (`lab ship`):

1. Run local checks only (free offline):
   - `lab ship check` — file presence + tests when present; **skip tests cleanly if none**
   - Or `lab ship run` — same checks, then write showroom **inbox** on success
2. Do **not** publish or regenerate the gallery (that is a later step: `lab showroom publish`).
3. Capture for best-model / showcase work later:
   - `lab showroom capture --from-ship --project <name> --title "<short>"`
   - Writes `~/.grok/lab/showroom/inbox/<id>.json` only
4. Skip auto-capture when:
   - `--no-capture` / `GROK_LAB_NO_CAPTURE=1` / `showroom_auto_capture=false`
   - branch is `wip/*` or `tmp/*`
   - shipcheck failed
5. Optional PR notes: `lab ship pr` (gh is optional; offline notes always print).
6. Never force-push or weaken safety rails.

If checks fail, fix or report — do not claim shipped.

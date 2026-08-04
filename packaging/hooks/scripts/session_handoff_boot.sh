#!/usr/bin/env bash
# session_handoff_boot.sh — SessionStart: ensure handoff package exists + refresh plane snapshot
set -euo pipefail
export PATH="${HOME}/.local/bin:${HOME}/homebrew/bin:${HOME}/.grok/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

LAB="${HOME}/.local/bin/lab"
if [[ ! -x "$LAB" ]]; then
  LAB="${HOME}/Projects/grok-home/bin/lab"
fi
if [[ ! -x "$LAB" ]]; then
  exit 0
fi

# If no handoff yet, create a baseline package
if [[ ! -f "${HOME}/.grok/lab/handoff/latest.json" ]]; then
  "$LAB" handoff close --note "SessionStart baseline handoff" >/dev/null 2>&1 || true
else
  # Refresh plane/repos; keep prior next/open/note
  "$LAB" handoff brief --refresh >/dev/null 2>&1 || true
fi

# Tiny banner for session logs (not a full brief dump — agent should run lab handoff brief)
echo "[handoff] latest: ${HOME}/.grok/lab/handoff/latest.md  ·  lab handoff brief"
exit 0

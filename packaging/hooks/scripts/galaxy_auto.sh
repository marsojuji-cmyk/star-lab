#!/usr/bin/env bash
# galaxy-auto.sh — cron/hook-safe Astro Galaxy harvest (PATH + logging).
# Usage: galaxy-auto.sh [collect|auto|dash-quiet]
set -euo pipefail

export PATH="${HOME}/.local/bin:${HOME}/homebrew/bin:${HOME}/.grok/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

LAB_REPO="${GROK_LAB_REPO:-${HOME}/Projects/grok-home}"
LAB_BIN="${HOME}/.local/bin/lab"
LAB_DATA="${GROK_LAB_DATA:-${HOME}/.grok/lab}"
LOG_DIR="${LAB_DATA}/galaxy"
LOG="${LOG_DIR}/auto.log"
MODE="${1:-auto}"

mkdir -p "${LOG_DIR}"
# Keep symlink fresh (same as session boot).
if [[ -x "${LAB_REPO}/bin/lab" ]]; then
  mkdir -p "${HOME}/.local/bin"
  ln -sfn "${LAB_REPO}/bin/lab" "${LAB_BIN}" 2>/dev/null || true
fi

if [[ ! -x "${LAB_BIN}" && -x "${LAB_REPO}/bin/lab" ]]; then
  LAB_BIN="${LAB_REPO}/bin/lab"
fi

if [[ ! -x "${LAB_BIN}" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR lab missing" >>"${LOG}"
  exit 1
fi

export GROK_LAB_REPO="${LAB_REPO}"
export GROK_LAB_DATA="${LAB_DATA}"

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{
  echo "── ${TS} mode=${MODE} ──"
  case "${MODE}" in
    collect)
      "${LAB_BIN}" galaxy collect --auto 2>&1 || "${LAB_BIN}" galaxy collect 2>&1
      ;;
    dash-quiet|dash)
      "${LAB_BIN}" galaxy dash --no-open 2>&1
      ;;
    auto|*)
      "${LAB_BIN}" galaxy auto 2>&1
      ;;
  esac
  echo "ok"
} >>"${LOG}" 2>&1

# Cap log size (~200KB keep tail)
if [[ -f "${LOG}" ]]; then
  sz=$(wc -c <"${LOG}" | tr -d ' ')
  if [[ "${sz}" -gt 200000 ]]; then
    tail -c 100000 "${LOG}" >"${LOG}.tmp" && mv "${LOG}.tmp" "${LOG}"
  fi
fi

exit 0

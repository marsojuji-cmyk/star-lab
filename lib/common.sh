#!/usr/bin/env bash
# Shared PATH, colors, and ROOT for Grok Star Lab.
# Source from bin/lab and other lab scripts. Safe to source multiple times.

# Prefer user-local Homebrew when present (no sudo).
if [[ -x "${HOME}/homebrew/bin/brew" ]]; then
  # shellcheck disable=SC1091
  eval "$("${HOME}/homebrew/bin/brew" shellenv)" 2>/dev/null || true
fi

# PATH contract: match doctor preamble + lab shims.
export PATH="${HOME}/.grok/bin:${HOME}/.local/bin:${HOME}/homebrew/bin:/usr/local/bin:${PATH}"
export PROJECTS="${PROJECTS:-${HOME}/Projects}"

# Colors (empty when not a TTY so logs stay clean).
if [[ -t 1 ]] || [[ -n "${GROK_LAB_FORCE_COLOR:-}" ]]; then
  RED=$'\033[31m'
  GRN=$'\033[32m'
  YLW=$'\033[33m'
  CYN=$'\033[36m'
  BLD=$'\033[1m'
  DIM=$'\033[2m'
  RST=$'\033[0m'
else
  RED="" GRN="" YLW="" CYN="" BLD="" DIM="" RST=""
fi

# ROOT = monorepo root (parent of lib/ when sourced from lib/common.sh).
# Callers may set ROOT before sourcing; otherwise detect from BASH_SOURCE.
if [[ -z "${ROOT:-}" ]]; then
  _common_src="${BASH_SOURCE[0]:-}"
  if [[ -n "$_common_src" && -f "$_common_src" ]]; then
    ROOT="$(cd "$(dirname "$_common_src")/.." && pwd)"
  else
    ROOT="$(cd "$(dirname "${0}")/.." && pwd)"
  fi
  unset _common_src
fi
export ROOT

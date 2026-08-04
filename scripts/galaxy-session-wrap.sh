#!/usr/bin/env bash
# galaxy-session-wrap.sh — end-of-session ritual: optional tokens complete + galaxy harvest.
#
# Env (optional):
#   GALAXY_AUDIT_ID / GROK_TOKEN_AUDIT_ID  — complete this token audit
#   GALAXY_ACTUAL_TOKENS                   — actual tokens used (int)
#   GALAXY_QUALITY                         — 0.0–1.0 quality score
#   GALAXY_SUCCESS                         — yes|no (default yes if quality set)
set -euo pipefail

export PATH="${HOME}/.local/bin:${HOME}/homebrew/bin:${HOME}/.grok/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

LAB_REPO="${GROK_LAB_REPO:-${HOME}/Projects/grok-home}"
LAB_BIN="${HOME}/.local/bin/lab"
LAB_DATA="${GROK_LAB_DATA:-${HOME}/.grok/lab}"

if [[ -x "${LAB_REPO}/bin/lab" ]]; then
  mkdir -p "${HOME}/.local/bin"
  ln -sfn "${LAB_REPO}/bin/lab" "${LAB_BIN}" 2>/dev/null || true
fi
[[ -x "${LAB_BIN}" ]] || LAB_BIN="${LAB_REPO}/bin/lab"
if [[ ! -x "${LAB_BIN}" ]]; then
  echo "error: lab CLI missing" >&2
  exit 1
fi

export GROK_LAB_REPO="${LAB_REPO}"
export GROK_LAB_DATA="${LAB_DATA}"

AUDIT="${GALAXY_AUDIT_ID:-${GROK_TOKEN_AUDIT_ID:-}}"
TOKENS="${GALAXY_ACTUAL_TOKENS:-}"
QUALITY="${GALAXY_QUALITY:-}"
SUCCESS="${GALAXY_SUCCESS:-}"

if [[ -n "${AUDIT}" && -n "${TOKENS}" ]]; then
  qargs=()
  if [[ -n "${QUALITY}" ]]; then
    qargs+=(--quality "${QUALITY}")
  fi
  if [[ -n "${SUCCESS}" ]]; then
    qargs+=(--success "${SUCCESS}")
  elif [[ -n "${QUALITY}" ]]; then
    qargs+=(--success yes)
  fi
  echo "[wrap] tokens complete audit=${AUDIT} tokens=${TOKENS}"
  "${LAB_BIN}" tokens complete --audit-id "${AUDIT}" --actual-tokens "${TOKENS}" "${qargs[@]}" 2>&1 || true
elif [[ -n "${AUDIT}" ]]; then
  echo "[wrap] skip tokens complete (set GALAXY_ACTUAL_TOKENS to complete audit ${AUDIT})"
fi

echo "[wrap] galaxy collect"
"${LAB_BIN}" galaxy collect --auto 2>&1 || "${LAB_BIN}" galaxy collect 2>&1

# Manual log breadcrumb for wrap
"${LAB_BIN}" galaxy log core session_wrap "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --note "session-wrap" 2>&1 || true

echo "[wrap] done · open: lab galaxy dash"
exit 0

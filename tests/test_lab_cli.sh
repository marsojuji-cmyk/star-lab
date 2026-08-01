#!/usr/bin/env bash
# tests/test_lab_cli.sh — PR1 facade smoke tests
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB="${ROOT}/bin/lab"
PASS=0
FAIL=0

assert_exit() {
  local label="$1" expected="$2"
  shift 2
  set +e
  "$@" >/dev/null 2>&1
  local code=$?
  set -e
  if [[ "$code" -eq "$expected" ]]; then
    echo "  PASS  ${label} (exit ${code})"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  ${label} (expected ${expected}, got ${code})"
    FAIL=$((FAIL + 1))
  fi
}

echo "test_lab_cli.sh  root=${ROOT}"

if [[ ! -x "$LAB" ]]; then
  chmod +x "$LAB" 2>/dev/null || true
fi

# lab help exits 0
assert_exit "lab help" 0 "$LAB" help

# lab doctor exits 0 (facade -> bin/doctor; needs host PATH/tools healthy)
export PATH="${HOME}/.grok/bin:${HOME}/.local/bin:${HOME}/homebrew/bin:/usr/local/bin:${PATH}"
assert_exit "lab doctor" 0 "$LAB" doctor

# unknown command exits 2
assert_exit "lab unknown" 2 "$LAB" not-a-real-command

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

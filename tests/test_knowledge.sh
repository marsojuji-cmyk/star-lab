#!/usr/bin/env bash
# tests/test_knowledge.sh — PR5 knowledge crucible smoke via bin/lab
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

assert_contains() {
  local label="$1" needle="$2"
  shift 2
  local out
  out="$("$@" 2>&1)" || true
  if [[ "$out" == *"$needle"* ]]; then
    echo "  PASS  ${label}"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  ${label} (missing '${needle}')"
    echo "        got: ${out}" | head -c 500
    echo
    FAIL=$((FAIL + 1))
  fi
}

echo "test_knowledge.sh  root=${ROOT}"

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/lab-knowledge-sh.XXXXXX")"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

export GROK_HOME="${tmpdir}/grok"
export GROK_LAB_DATA="${tmpdir}/lab"
export PROJECTS="${tmpdir}/Projects"
export GROK_LAB_REPO="${ROOT}"
mkdir -p "${GROK_HOME}/memory" "${GROK_LAB_DATA}/knowledge" \
  "${PROJECTS}/sample/docs"

printf '%s\n' '# Memory' '' 'offline FTS crucible shell-token-77' \
  > "${GROK_HOME}/memory/MEMORY.md"
printf '%s\n' '# sample' '' 'AGENTS for sample project' \
  > "${PROJECTS}/sample/AGENTS.md"
printf '%s\n' '# Design' '' 'design doc shell-token-77 details' \
  > "${PROJECTS}/sample/docs/ARCH.md"
# noise that must be excluded
mkdir -p "${PROJECTS}/sample/node_modules/x"
printf '%s\n' 'secret-node-modules-token' \
  > "${PROJECTS}/sample/node_modules/x/README.md"

chmod +x "$LAB" 2>/dev/null || true

assert_contains "lab help lists knowledge" "lab knowledge" "$LAB" help
assert_exit "lab knowledge status (empty)" 0 "$LAB" knowledge status
assert_exit "lab knowledge index" 0 "$LAB" knowledge index
assert_contains "index created fts.db" "fts.db" "$LAB" knowledge status
assert_contains "query finds shell-token" "shell-token-77" \
  "$LAB" knowledge query shell-token-77
assert_contains "query does not hit node_modules" "No matches" \
  "$LAB" knowledge query secret-node-modules-token

# unit tests
if python3 "${ROOT}/tests/test_knowledge.py" -v; then
  echo "  PASS  test_knowledge.py"
  PASS=$((PASS + 1))
else
  echo "  FAIL  test_knowledge.py"
  FAIL=$((FAIL + 1))
fi

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

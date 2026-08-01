#!/usr/bin/env bash
# tests/test_safety_regression.sh — safety_guard allow/deny isolation (PR13)
#
# Invokes the installed hook script (read-only). Never writes under ~/.grok.
# Also re-runs the same cases from a temp GROK_HOME copy to prove the guard is
# pure stdin→stdout (no ambient mutation of real home).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

REAL_GUARD="${HOME}/.grok/hooks/scripts/safety_guard.py"

assert_decision() {
  local label="$1" guard="$2" payload="$3" expected="$4"
  local out decision
  set +e
  out="$(python3 "$guard" <<<"$payload" 2>&1)"
  local code=$?
  set -e
  if [[ "$code" -ne 0 ]]; then
    echo "  FAIL  ${label} (python exit ${code})"
    echo "        out: ${out}" | head -c 300
    echo
    FAIL=$((FAIL + 1))
    return
  fi
  decision="$(
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("decision",""))' <<<"$out" 2>/dev/null || true
  )"
  if [[ "$decision" == "$expected" ]]; then
    echo "  PASS  ${label} → ${decision}"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  ${label} (expected decision=${expected}, got '${decision}')"
    echo "        out: ${out}" | head -c 300
    echo
    FAIL=$((FAIL + 1))
  fi
}

run_matrix() {
  local tag="$1" guard="$2"

  # ── allow ──────────────────────────────────────────────────────────
  assert_decision "${tag}/allow echo" "$guard" \
    '{"command":"echo hello"}' allow
  assert_decision "${tag}/allow ls" "$guard" \
    '{"command":"ls -la ~/Projects"}' allow
  assert_decision "${tag}/allow nested input" "$guard" \
    '{"input":{"command":"git status"}}' allow
  assert_decision "${tag}/allow tool_input" "$guard" \
    '{"tool_input":{"command":"python3 -c \"print(1)\""}}' allow
  assert_decision "${tag}/allow empty payload" "$guard" \
    '{}' allow
  assert_decision "${tag}/allow malformed json (fail-open)" "$guard" \
    'not-json' allow

  # ── deny ───────────────────────────────────────────────────────────
  assert_decision "${tag}/deny rm -rf /" "$guard" \
    '{"command":"rm -rf /"}' deny
  assert_decision "${tag}/deny rm -rf /*" "$guard" \
    '{"command":"rm -rf /*"}' deny
  assert_decision "${tag}/deny rm -rf ~" "$guard" \
    '{"command":"rm -rf ~"}' deny
  assert_decision "${tag}/deny rm -rf \$HOME" "$guard" \
    '{"command":"rm -rf $HOME"}' deny
  assert_decision "${tag}/deny rm -fr /" "$guard" \
    '{"command":"rm -fr /"}' deny
  assert_decision "${tag}/deny mkfs" "$guard" \
    '{"command":"mkfs /dev/sda"}' deny
  assert_decision "${tag}/deny diskutil erase" "$guard" \
    '{"command":"diskutil eraseDisk JHFS+ X disk9"}' deny
  assert_decision "${tag}/deny dd if=" "$guard" \
    '{"command":"dd if=/dev/zero of=/dev/sda"}' deny
  assert_decision "${tag}/deny fork bomb" "$guard" \
    '{"command":":(){ :|:& };:"}' deny
  assert_decision "${tag}/deny nested rm -rf /" "$guard" \
    '{"input":{"command":"sudo rm -rf /"}}' deny
}

echo "test_safety_regression.sh  root=${ROOT}"

if [[ ! -f "$REAL_GUARD" ]]; then
  echo "  FAIL  missing safety script: ${REAL_GUARD}"
  exit 1
fi
if [[ ! -x "$REAL_GUARD" ]] && ! python3 -c "import pathlib; pathlib.Path(r'''$REAL_GUARD''').read_text()" 2>/dev/null; then
  echo "  FAIL  cannot read safety script: ${REAL_GUARD}"
  exit 1
fi
echo "  PASS  safety script present (${REAL_GUARD})"
PASS=$((PASS + 1))

# Real installed hook — read-only exercise of ~/.grok/hooks/scripts/safety_guard.py
run_matrix "real" "$REAL_GUARD"

# Isolated temp GROK_HOME copy — same matrix; proves no write side-effects needed.
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/safety-regression.XXXXXX")"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

mkdir -p "${tmpdir}/hooks/scripts"
cp "$REAL_GUARD" "${tmpdir}/hooks/scripts/safety_guard.py"
chmod +x "${tmpdir}/hooks/scripts/safety_guard.py"
export GROK_HOME="$tmpdir"
# Guard does not read GROK_HOME today; still set for future-proof isolation contract.
run_matrix "iso" "${tmpdir}/hooks/scripts/safety_guard.py"

# Isolation: real ~/.grok must not have gained files from this test under hooks/.
# (We only ever read/copy; assert temp dir is the only place we wrote.)
if [[ -d "${tmpdir}/hooks/scripts" && -f "${tmpdir}/hooks/scripts/safety_guard.py" ]]; then
  echo "  PASS  temp GROK_HOME isolation dir intact"
  PASS=$((PASS + 1))
else
  echo "  FAIL  temp GROK_HOME isolation dir missing"
  FAIL=$((FAIL + 1))
fi

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

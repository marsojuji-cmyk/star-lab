#!/usr/bin/env bash
# tests/test_arena.sh — PR6 Agent Arena smoke (offline script + workflow handoff)
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

echo "test_arena.sh  root=${ROOT}"
export GROK_LAB_REPO="${ROOT}"
# Isolate lab data for forge wrap / metrics writes
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/arena-test.XXXXXX")"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT
export GROK_LAB_DATA="${tmpdir}/lab"
export GROK_HOME="${tmpdir}/grok"
mkdir -p "${GROK_HOME}/hooks/scripts" "${GROK_LAB_DATA}"

# Minimal safety hook fixtures so lab-audit hard checks pass in isolation
cat > "${GROK_HOME}/hooks/safety-guard.json" <<'EOF'
{"name": "safety-guard", "test": true}
EOF
cat > "${GROK_HOME}/hooks/scripts/safety_guard.py" <<'EOF'
#!/usr/bin/env python3
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw) if raw.strip() else {}
except Exception:
    data = {}
cmd = str(data.get("command") or "")
if "rm -rf /" in cmd or cmd.strip() == "rm -rf /":
    print("deny")
else:
    print("allow")
EOF
chmod +x "${GROK_HOME}/hooks/scripts/safety_guard.py"

if [[ ! -x "$LAB" ]]; then
  chmod +x "$LAB" 2>/dev/null || true
fi

assert_exit "arena help" 0 "$LAB" arena help
assert_contains "arena list shows lab-audit" "lab-audit" "$LAB" arena list
assert_contains "arena list shows home-audit" "home-audit" "$LAB" arena list
assert_contains "describe kind script" "kind:        script" "$LAB" arena describe lab-audit

assert_exit "arena run lab-audit --no-forge" 0 "$LAB" arena run lab-audit --no-forge
assert_contains "lab-audit report path" "report" "$LAB" arena run lab-audit --no-forge

# metrics JSON written
if compgen -G "${GROK_LAB_DATA}/metrics/lab-audit-*.json" >/dev/null; then
  echo "  PASS  metrics JSON written"
  PASS=$((PASS + 1))
else
  echo "  FAIL  metrics JSON missing under ${GROK_LAB_DATA}/metrics"
  FAIL=$((FAIL + 1))
fi

# workflow handoff: source present → exit 0, no headless
assert_exit "home-audit handoff" 0 "$LAB" arena run home-audit
assert_contains "handoff mentions /workflow" "/workflow lab-audit" "$LAB" arena run home-audit
assert_contains "handoff no headless" "No --try-headless" "$LAB" arena run home-audit

prompt="${tmpdir}/prompt.txt"
assert_exit "handoff-prompt writes file" 0 \
  "$LAB" arena run home-audit --handoff-prompt "$prompt"
if [[ -s "$prompt" ]] && grep -q "lab-audit" "$prompt"; then
  echo "  PASS  handoff prompt file non-empty"
  PASS=$((PASS + 1))
else
  echo "  FAIL  handoff prompt file missing/empty"
  FAIL=$((FAIL + 1))
fi

# missing pipeline
assert_exit "unknown pipeline" 1 "$LAB" arena run does-not-exist

# forge wrap path (optional; forge is in this worktree from PR3 base)
assert_exit "lab-audit with forge wrap" 0 "$LAB" arena run lab-audit

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

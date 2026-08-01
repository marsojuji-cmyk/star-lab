#!/usr/bin/env bash
# tests/test_doctor_compat.sh — human doctor green path + --json schema
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="${ROOT}/bin/doctor"
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

echo "test_doctor_compat.sh  root=${ROOT}"

if [[ ! -x "$DOCTOR" ]]; then
  chmod +x "$DOCTOR" 2>/dev/null || true
fi

export PATH="${HOME}/.grok/bin:${HOME}/.local/bin:${HOME}/homebrew/bin:/usr/local/bin:${PATH}"

# Human mode: still exit 0 on healthy host; preserve operational banner.
set +e
human_out="$("$DOCTOR" 2>&1)"
human_ec=$?
set -e
if [[ "$human_ec" -eq 0 ]]; then
  echo "  PASS  doctor human exit 0"
  PASS=$((PASS + 1))
else
  echo "  FAIL  doctor human exit ${human_ec} (expected 0 on green host)"
  FAIL=$((FAIL + 1))
fi

if [[ "$human_out" == *"WORLD STAGE STATUS: OPERATIONAL"* ]] || [[ "$human_out" == *"pass="* ]]; then
  echo "  PASS  doctor human format markers"
  PASS=$((PASS + 1))
else
  echo "  FAIL  doctor human format markers missing"
  echo "        got: $(echo "$human_out" | tail -5)"
  FAIL=$((FAIL + 1))
fi

# JSON mode: must parse with python json; schema_version + checks[]
set +e
json_out="$("$DOCTOR" --json 2>&1)"
json_ec=$?
set -e

# On green host json_ec should be 0; still require parseable JSON either way.
if python3 -c '
import json, sys
doc = json.loads(sys.stdin.read())
assert "schema_version" in doc, "missing schema_version"
assert "checks" in doc and isinstance(doc["checks"], list), "missing checks[]"
assert "pass" in doc and "warn" in doc and "fail" in doc
assert "operational" in doc
assert int(doc["schema_version"]) >= 1
print("checks=%d pass=%s warn=%s fail=%s" % (
    len(doc["checks"]), doc["pass"], doc["warn"], doc["fail"]))
' <<<"$json_out"; then
  echo "  PASS  doctor --json parses (schema_version + checks)"
  PASS=$((PASS + 1))
else
  echo "  FAIL  doctor --json did not parse as expected schema"
  echo "        out: $(echo "$json_out" | head -c 500)"
  FAIL=$((FAIL + 1))
fi

if [[ "$json_ec" -eq 0 ]]; then
  echo "  PASS  doctor --json exit 0 on green host"
  PASS=$((PASS + 1))
else
  # Mirror human: if human was 0, json must be 0
  if [[ "$human_ec" -eq 0 ]]; then
    echo "  FAIL  doctor --json exit ${json_ec} but human was 0"
    FAIL=$((FAIL + 1))
  else
    echo "  SKIP  doctor --json exit ${json_ec} (host not fully healthy)"
  fi
fi

# Observatory snapshot writes both artifacts
export GROK_LAB_REPO="$ROOT"
set +e
snap_out="$(python3 "${ROOT}/modules/observatory/cli.py" snapshot 2>&1)"
snap_ec=$?
set -e
if [[ "$snap_ec" -eq 0 && -f "${ROOT}/data/status.json" && -f "${ROOT}/dashboard/data-embed.js" ]]; then
  if python3 -c '
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
st = json.loads((root / "data" / "status.json").read_text())
assert st.get("schema_version") == 1
assert "doctor" in st and "checks" in st["doctor"]
embed = (root / "dashboard" / "data-embed.js").read_text()
assert "window.GROK_LAB_STATUS" in embed
print("snapshot ok generated_at=%s" % st.get("generated_at"))
' "$ROOT"; then
    echo "  PASS  observatory snapshot status.json + data-embed.js"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  snapshot artifacts invalid"
    FAIL=$((FAIL + 1))
  fi
else
  echo "  FAIL  observatory snapshot (exit ${snap_ec})"
  echo "        ${snap_out}" | head -c 400
  echo
  FAIL=$((FAIL + 1))
fi

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

#!/usr/bin/env bash
# tests/test_lab_modules.sh — module presence + lab help matrix (PR13)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB="${ROOT}/bin/lab"
PASS=0
FAIL=0

# Canonical Star Lab module set (design MODULE_NAMES + observatory).
MODULES=(
  arena
  design
  dock
  forge
  gym
  imagine
  knowledge
  observatory
  sandbox
  ship
  showroom
)

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

echo "test_lab_modules.sh  root=${ROOT}"

if [[ ! -x "$LAB" ]]; then
  chmod +x "$LAB" 2>/dev/null || true
fi

export PATH="${HOME}/.grok/bin:${HOME}/.local/bin:${HOME}/homebrew/bin:/usr/local/bin:${PATH}"
export GROK_LAB_REPO="${ROOT}"

# ── lab help ─────────────────────────────────────────────────────────
assert_exit "lab help" 0 "$LAB" help
assert_exit "lab --help" 0 "$LAB" --help
assert_exit "lab -h" 0 "$LAB" -h

# ── module directory matrix ──────────────────────────────────────────
echo
echo "  Module presence matrix"
echo "  ──────────────────────"
printf "  %-14s %-8s %s\n" "module" "status" "marker"
for m in "${MODULES[@]}"; do
  dir="${ROOT}/modules/${m}"
  if [[ ! -d "$dir" ]]; then
    echo "  FAIL  module dir missing: ${m}"
    FAIL=$((FAIL + 1))
    printf "  %-14s %-8s %s\n" "$m" "MISSING" "—"
    continue
  fi
  if [[ -f "${dir}/cli.py" ]]; then
    status="cli"
    marker="cli.py"
    echo "  PASS  module ${m} has cli.py"
    PASS=$((PASS + 1))
  elif [[ -f "${dir}/.gitkeep" ]] || [[ -z "$(find "$dir" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' -print -quit 2>/dev/null)" ]]; then
    status="stub"
    marker=".gitkeep"
    echo "  PASS  module ${m} dir present (stub ok)"
    PASS=$((PASS + 1))
  else
    status="partial"
    marker="other"
    echo "  PASS  module ${m} dir present (partial)"
    PASS=$((PASS + 1))
  fi
  printf "  %-14s %-8s %s\n" "$m" "$status" "$marker"
done

# ── wired subcommand help (exit 0) ───────────────────────────────────
# Only modules dispatched by bin/lab on this branch.
echo
echo "  Wired CLI help (exit 0)"
echo "  ───────────────────────"

# forge / design use free-form "help"
assert_exit "lab forge help" 0 "$LAB" forge help
assert_exit "lab design help" 0 "$LAB" design help

# argparse modules accept -h
assert_exit "lab ship -h" 0 "$LAB" ship -h
assert_exit "lab showroom -h" 0 "$LAB" showroom -h
assert_exit "lab observatory -h" 0 "$LAB" observatory -h
assert_exit "lab observatory help" 0 "$LAB" observatory help

# doctor / status via facade
assert_exit "lab doctor -h" 0 "$LAB" doctor -h
assert_exit "lab status" 0 "$LAB" status

# ── doctor safety matrix still green ─────────────────────────────────
echo
echo "  Doctor safety matrix"
echo "  ────────────────────"
set +e
json_out="$("${ROOT}/bin/doctor" --json 2>&1)"
json_ec=$?
set -e

if [[ "$json_ec" -eq 0 ]]; then
  echo "  PASS  lab/bin doctor --json exit 0"
  PASS=$((PASS + 1))
else
  echo "  FAIL  doctor --json exit ${json_ec}"
  FAIL=$((FAIL + 1))
fi

if python3 -c '
import json, sys
doc = json.loads(sys.stdin.read())
by = {c.get("id"): c.get("severity") for c in doc.get("checks") or [] if isinstance(c, dict)}
need = ("safety.allow", "safety.deny", "file.safety_hook", "file.safety_script")
missing = [k for k in need if by.get(k) != "pass"]
if missing:
    print("missing or not pass:", ", ".join(missing))
    sys.exit(1)
# module rows (lab.module.*) optional but when present must not be fail
mod_fail = [k for k, v in by.items() if k.startswith("lab.module.") and v == "fail"]
if mod_fail:
    print("module rows failed:", ", ".join(mod_fail))
    sys.exit(1)
print("safety matrix ok; module_fail=0")
' <<<"$json_out"; then
  echo "  PASS  doctor safety.allow/deny + hook files pass"
  PASS=$((PASS + 1))
else
  echo "  FAIL  doctor safety matrix incomplete"
  FAIL=$((FAIL + 1))
fi

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

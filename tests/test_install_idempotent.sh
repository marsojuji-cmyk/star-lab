#!/usr/bin/env bash
# tests/test_install_idempotent.sh — install skeleton modes, symlink, non-clobber
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL="${ROOT}/scripts/install-lab.sh"
PASS=0
FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    echo "  PASS  ${label}"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  ${label} (expected '${expected}', got '${actual}')"
    FAIL=$((FAIL + 1))
  fi
}

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

echo "test_install_idempotent.sh  root=${ROOT}"

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/lab-install-test.XXXXXX")"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

export GROK_LAB_DATA="${tmpdir}/labdata"
export GROK_LAB_LOCAL_BIN="${tmpdir}/localbin"
mkdir -p "$GROK_LAB_LOCAL_BIN"

# dry-run exits 0 and creates nothing
assert_exit "install --dry-run" 0 bash "$INSTALL" --dry-run
if [[ ! -e "$GROK_LAB_DATA" ]]; then
  echo "  PASS  dry-run creates no data dir"
  PASS=$((PASS + 1))
else
  echo "  FAIL  dry-run created ${GROK_LAB_DATA}"
  FAIL=$((FAIL + 1))
fi

# first install
assert_exit "install first run" 0 bash "$INSTALL"

# modes: dir 0700
mode="$(stat -f '%Lp' "$GROK_LAB_DATA" 2>/dev/null || stat -c '%a' "$GROK_LAB_DATA")"
assert_eq "lab data mode 700" "700" "$mode"

for sub in experiments metrics knowledge showroom gym; do
  m="$(stat -f '%Lp' "${GROK_LAB_DATA}/${sub}" 2>/dev/null || stat -c '%a' "${GROK_LAB_DATA}/${sub}")"
  assert_eq "${sub} mode 700" "700" "$m"
done

# pin file
if [[ -f "${GROK_LAB_DATA}/.skills_version" ]]; then
  echo "  PASS  .skills_version written"
  PASS=$((PASS + 1))
else
  echo "  FAIL  .skills_version missing"
  FAIL=$((FAIL + 1))
fi

# symlink
if [[ -L "${GROK_LAB_LOCAL_BIN}/lab" ]]; then
  target="$(readlink "${GROK_LAB_LOCAL_BIN}/lab")"
  assert_eq "symlink target" "${ROOT}/bin/lab" "$target"
else
  echo "  FAIL  lab symlink missing"
  FAIL=$((FAIL + 1))
fi

# symlink entry point resolves real repo
help_out="$("${GROK_LAB_LOCAL_BIN}/lab" help 2>&1)"
if [[ "$help_out" == *"Repo:      ${ROOT}"* ]]; then
  echo "  PASS  installed lab help reports real ROOT"
  PASS=$((PASS + 1))
else
  echo "  FAIL  installed lab help wrong ROOT"
  echo "        ${help_out}" | head -c 400
  echo
  FAIL=$((FAIL + 1))
fi

# create a user file with execute bit; reinstall must not strip it
user_script="${GROK_LAB_DATA}/experiments/user-tool.sh"
printf '#!/bin/sh\necho ok\n' > "$user_script"
chmod 0755 "$user_script"
assert_exit "install second run (idempotent)" 0 bash "$INSTALL"
umode="$(stat -f '%Lp' "$user_script" 2>/dev/null || stat -c '%a' "$user_script")"
assert_eq "user file mode preserved (755)" "755" "$umode"

# config not overwritten on second run
echo "# user marker" >> "${GROK_LAB_DATA}/config.toml"
assert_exit "install third run keeps config" 0 bash "$INSTALL"
if grep -q "user marker" "${GROK_LAB_DATA}/config.toml"; then
  echo "  PASS  config.toml not clobbered"
  PASS=$((PASS + 1))
else
  echo "  FAIL  config.toml was rewritten"
  FAIL=$((FAIL + 1))
fi

# refuse to clobber non-symlink lab binary
rm -f "${GROK_LAB_LOCAL_BIN}/lab"
echo "not a symlink" > "${GROK_LAB_LOCAL_BIN}/lab"
set +e
bash "$INSTALL" >/dev/null 2>&1
clobber_code=$?
set -e
assert_eq "refuse clobber non-symlink" "1" "$clobber_code"
if [[ -f "${GROK_LAB_LOCAL_BIN}/lab" && ! -L "${GROK_LAB_LOCAL_BIN}/lab" ]]; then
  content="$(cat "${GROK_LAB_LOCAL_BIN}/lab")"
  assert_eq "non-symlink content intact" "not a symlink" "$content"
else
  echo "  FAIL  non-symlink lab was replaced"
  FAIL=$((FAIL + 1))
fi

echo "────────────────────────────────────"
echo "pass=${PASS} fail=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

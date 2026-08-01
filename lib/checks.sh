#!/usr/bin/env bash
# Shared doctor check primitives for Grok Star Lab.
# Sourced by bin/doctor. Safe to source once; do not execute directly.
#
# Env / globals:
#   DOCTOR_JSON=0|1   — when 1, suppress human lines and append TSV to DOCTOR_TSV
#   DOCTOR_TSV        — path to checks TSV (id, severity, label, detail) when JSON
#   CHECK_ID          — optional id for next ok/warn/bad (cleared after use)
#
# Counters: pass, warn, fail  (warn is both counter and function name — bash allows this)

: "${DOCTOR_JSON:=0}"
: "${DOCTOR_TSV:=}"
: "${CHECK_ID:=}"

pass="${pass:-0}"
warn="${warn:-0}"
fail="${fail:-0}"

# Colors: honor caller-set values. Only initialize when RST is unset.
if [[ -z "${RST+x}" ]]; then
  if [[ "${DOCTOR_JSON}" != "1" ]] && { [[ -t 1 ]] || [[ -n "${GROK_LAB_FORCE_COLOR:-}" ]]; }; then
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
fi

# Strip ANSI CSI sequences for JSON detail fields.
_strip_ansi() {
  # shellcheck disable=SC2001
  echo "$1" | sed $'s/\x1b\\[[0-9;]*m//g'
}

# Derive a stable-ish id from free-form message when CHECK_ID unset.
_slug_id() {
  local prefix="$1" msg="$2" s
  s="$(_strip_ansi "$msg")"
  s="$(echo "$s" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '_' | sed 's/^_//;s/_$//')"
  s="${s:0:48}"
  echo "${prefix}.${s:-x}"
}

# Append one check row: id \t severity \t label \t detail
_json_row() {
  local id="$1" severity="$2" label="$3" detail="${4:-}"
  [[ -z "${DOCTOR_TSV}" ]] && return 0
  # Escape tabs/newlines in fields so TSV stays one line per check.
  label="${label//$'\t'/ }"
  label="${label//$'\n'/ }"
  detail="${detail//$'\t'/ }"
  detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\t%s\n' "$id" "$severity" "$label" "$detail" >>"${DOCTOR_TSV}"
}

_take_id() {
  local prefix="$1" msg="$2"
  local id="${CHECK_ID:-}"
  CHECK_ID=""
  if [[ -z "$id" ]]; then
    id="$(_slug_id "$prefix" "$msg")"
  fi
  echo "$id"
}

ok() {
  local msg="$*"
  pass=$((pass + 1))
  if [[ "${DOCTOR_JSON}" == "1" ]]; then
    local id clean
    id="$(_take_id "ok" "$msg")"
    clean="$(_strip_ansi "$msg")"
    _json_row "$id" "pass" "$clean" ""
  else
    CHECK_ID=""
    echo "  ${GRN}✓${RST} $*"
  fi
}

warn() {
  local msg="$*"
  warn=$((warn + 1))
  if [[ "${DOCTOR_JSON}" == "1" ]]; then
    local id clean
    id="$(_take_id "warn" "$msg")"
    clean="$(_strip_ansi "$msg")"
    _json_row "$id" "warn" "$clean" ""
  else
    CHECK_ID=""
    echo "  ${YLW}!${RST} $*"
  fi
}

bad() {
  local msg="$*"
  fail=$((fail + 1))
  if [[ "${DOCTOR_JSON}" == "1" ]]; then
    local id clean
    id="$(_take_id "fail" "$msg")"
    clean="$(_strip_ansi "$msg")"
    _json_row "$id" "fail" "$clean" ""
  else
    CHECK_ID=""
    echo "  ${RED}✗${RST} $*"
  fi
}

hdr() {
  if [[ "${DOCTOR_JSON}" == "1" ]]; then
    return 0
  fi
  echo
  echo "${BLD}${CYN}▸ $*${RST}"
}

need_cmd() {
  local c="$1" label="${2:-$1}"
  CHECK_ID="cmd.${c}"
  if command -v "$c" >/dev/null 2>&1; then
    local v
    v=$("$c" --version 2>/dev/null | head -1 | tr -d '\r' || echo "present")
    ok "$label  ${DIM}$v${RST}"
  else
    bad "$label missing"
  fi
}

need_file() {
  local f="$1" label="${2:-$1}"
  CHECK_ID="file.$(echo "$label" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '_' | sed 's/^_//;s/_$//')"
  if [[ -e "$f" ]]; then
    ok "$label"
  else
    bad "$label missing ($f)"
  fi
}

need_toml_key() {
  local key="$1" file="${2:-$HOME/.grok/config.toml}"
  CHECK_ID="toml.${key}"
  if grep -Eq "^[[:space:]]*${key}[[:space:]]*=" "$file" 2>/dev/null; then
    local line
    line=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" | head -1)
    ok "$key  ${DIM}$line${RST}"
  else
    warn "$key not set in config.toml"
  fi
}

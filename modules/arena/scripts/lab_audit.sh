#!/usr/bin/env bash
# lab_audit.sh — offline Agent Arena audit (kind: script)
# Checks: modules, safety allow/deny, disk free, ollama (best-effort),
# packaging version pin. Writes JSON report under ~/.grok/lab/metrics/.
# Hard fail (exit 1): missing safety hook/script, missing lab data root.
set -euo pipefail

# Resolve monorepo root
if [[ -n "${GROK_LAB_REPO:-}" ]]; then
  ROOT="${GROK_LAB_REPO}"
elif [[ -n "${ROOT:-}" ]]; then
  :
else
  _src="${BASH_SOURCE[0]}"
  while [[ -L "$_src" ]]; do
    _dir="$(cd "$(dirname "$_src")" && pwd)"
    _link="$(readlink "$_src")"
    if [[ "$_link" != /* ]]; then
      _src="${_dir}/${_link}"
    else
      _src="$_link"
    fi
  done
  ROOT="$(cd "$(dirname "$_src")/../../.." && pwd)"
  unset _src _dir _link
fi
export ROOT

# shellcheck disable=SC1091
if [[ -f "${ROOT}/lib/common.sh" ]]; then
  # shellcheck source=../../../lib/common.sh
  source "${ROOT}/lib/common.sh"
fi

GROK_HOME="${GROK_HOME:-${HOME}/.grok}"
LAB_DATA="${GROK_LAB_DATA:-${GROK_HOME}/lab}"
METRICS_DIR="${LAB_DATA}/metrics"
REPORT_TS="$(date -u +"%Y%m%dT%H%M%SZ" 2>/dev/null || date -u +"%Y%m%d%H%M%S")"
REPORT_PATH="${METRICS_DIR}/lab-audit-${REPORT_TS}.json"

PASS=0
WARN=0
FAIL=0
HARD_FAIL=0
declare -a NOTES=()
declare -a CHECKS=()

note() { NOTES+=("$1"); }
record() {
  # record name status detail
  CHECKS+=("$1|$2|$3")
}

ok() {
  local msg="$1"
  echo "  ok   ${msg}"
  PASS=$((PASS + 1))
  record "$2" "ok" "$msg"
}

warn() {
  local msg="$1"
  echo "  warn ${msg}"
  WARN=$((WARN + 1))
  record "$2" "warn" "$msg"
}

bad() {
  local msg="$1"
  echo "  FAIL ${msg}"
  FAIL=$((FAIL + 1))
  record "$2" "fail" "$msg"
}

hard() {
  local msg="$1"
  echo "  FAIL ${msg}"
  FAIL=$((FAIL + 1))
  HARD_FAIL=$((HARD_FAIL + 1))
  record "$2" "fail" "$msg"
}

echo "lab-audit  root=${ROOT}"
echo "           data=${LAB_DATA}"
echo "           grok=${GROK_HOME}"
if [[ -n "${GROK_LAB_RUN_ID:-}" ]]; then
  echo "           run_id=${GROK_LAB_RUN_ID}"
fi
echo ""

# ── 1. Lab data root (hard if missing and cannot create) ──────────
echo "== Lab data root"
if [[ -d "$LAB_DATA" ]]; then
  ok "lab data root exists: ${LAB_DATA}" "lab_data_root"
elif mkdir -p -m 0700 "$LAB_DATA" 2>/dev/null; then
  ok "lab data root created: ${LAB_DATA}" "lab_data_root"
else
  hard "lab data root missing and uncreatable: ${LAB_DATA}" "lab_data_root"
fi

mkdir -p -m 0700 "$METRICS_DIR" 2>/dev/null || true

# ── 2. Module directories ────────────────────────────────────────
echo ""
echo "== Modules"
EXPECTED_MODULES=(
  arena design dock forge gym imagine knowledge observatory sandbox ship showroom
)
MISSING_MODS=0
for m in "${EXPECTED_MODULES[@]}"; do
  if [[ -d "${ROOT}/modules/${m}" ]]; then
    ok "module ${m}" "module_${m}"
  else
    bad "module missing: modules/${m}" "module_${m}"
    MISSING_MODS=$((MISSING_MODS + 1))
  fi
done
if [[ "$MISSING_MODS" -eq 0 ]]; then
  note "all ${#EXPECTED_MODULES[@]} module dirs present"
fi

# ── 3. Safety hook allow/deny smoke (same as doctor) ──────────────
echo ""
echo "== Safety"
SAFETY_JSON="${GROK_HOME}/hooks/safety-guard.json"
SAFETY_PY="${GROK_HOME}/hooks/scripts/safety_guard.py"

if [[ ! -f "$SAFETY_JSON" ]]; then
  hard "safety hook missing: ${SAFETY_JSON}" "safety_hook"
else
  ok "safety hook present" "safety_hook"
fi

if [[ ! -f "$SAFETY_PY" ]]; then
  hard "safety script missing: ${SAFETY_PY}" "safety_script"
else
  ok "safety script present" "safety_script"
  if command -v python3 >/dev/null 2>&1; then
    allow_out="$(python3 "$SAFETY_PY" <<<"{\"command\":\"echo hello\"}" 2>/dev/null || true)"
    if echo "$allow_out" | grep -q allow; then
      ok "safety allows safe command" "safety_allow"
    else
      bad "safety allow path failed" "safety_allow"
    fi
    deny_out="$(python3 "$SAFETY_PY" <<<"{\"command\":\"rm -rf /\"}" 2>/dev/null || true)"
    if echo "$deny_out" | grep -q deny; then
      ok "safety blocks rm -rf /" "safety_deny"
    else
      bad "safety deny path failed" "safety_deny"
    fi
  else
    warn "python3 not on PATH; skip safety smoke" "safety_smoke"
  fi
fi

# ── 4. Disk free (warn threshold < 1Gi available) ─────────────────
echo ""
echo "== Disk"
free_h="$(df -h "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
free_k="$(df -k "$HOME" 2>/dev/null | awk 'NR==2{print $4}')"
if [[ -n "${free_k:-}" && "$free_k" =~ ^[0-9]+$ ]]; then
  # 1 GiB = 1048576 KiB
  if [[ "$free_k" -lt 1048576 ]]; then
    warn "disk free low: ${free_h:-${free_k}K} (<1Gi)" "disk_free"
  else
    ok "disk free (home vol): ${free_h:-unknown}" "disk_free"
  fi
else
  warn "disk free unknown" "disk_free"
fi

# ── 5. ollama list (best-effort) ──────────────────────────────────
echo ""
echo "== Ollama"
if command -v ollama >/dev/null 2>&1; then
  models="$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ' ' || true)"
  if [[ -n "${models// }" ]]; then
    ok "ollama models: ${models}" "ollama"
  else
    warn "ollama present but no models listed" "ollama"
  fi
else
  warn "ollama not on PATH (optional for arena)" "ollama"
fi

# ── 6. Packaging version pin ──────────────────────────────────────
echo ""
echo "== Packaging"
VERSION_FILE="${ROOT}/packaging/VERSION"
PIN_FILE="${LAB_DATA}/.skills_version"
if [[ -f "$VERSION_FILE" ]]; then
  VER="$(tr -d '[:space:]' < "$VERSION_FILE")"
  ok "packaging/VERSION = ${VER}" "packaging_version"
else
  warn "packaging/VERSION missing" "packaging_version"
  VER=""
fi
if [[ -f "$PIN_FILE" ]]; then
  PIN="$(tr -d '[:space:]' < "$PIN_FILE")"
  ok "skills_version pin = ${PIN}" "skills_pin"
else
  warn "skills_version pin missing (run lab install)" "skills_pin"
  PIN=""
fi

# ── Report JSON ───────────────────────────────────────────────────
echo ""
echo "== Report"

# Build checks JSON array without requiring jq
checks_json="["
first=1
for entry in "${CHECKS[@]+"${CHECKS[@]}"}"; do
  [[ -z "${entry:-}" ]] && continue
  cname="${entry%%|*}"
  rest="${entry#*|}"
  cstatus="${rest%%|*}"
  cdetail="${rest#*|}"
  # escape for JSON
  cdetail_esc="${cdetail//\\/\\\\}"
  cdetail_esc="${cdetail_esc//\"/\\\"}"
  if [[ "$first" -eq 1 ]]; then
    first=0
  else
    checks_json+=","
  fi
  checks_json+="{\"name\":\"${cname}\",\"status\":\"${cstatus}\",\"detail\":\"${cdetail_esc}\"}"
done
checks_json+="]"

status_overall="ok"
if [[ "$HARD_FAIL" -gt 0 || "$FAIL" -gt 0 ]]; then
  status_overall="fail"
elif [[ "$WARN" -gt 0 ]]; then
  status_overall="warn"
fi

cat > "${REPORT_PATH}" << EOF
{
  "schema_version": 1,
  "pipeline": "lab-audit",
  "kind": "script",
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo unknown)",
  "status": "${status_overall}",
  "pass": ${PASS},
  "warn": ${WARN},
  "fail": ${FAIL},
  "hard_fail": ${HARD_FAIL},
  "root": "${ROOT}",
  "lab_data": "${LAB_DATA}",
  "packaging_version": "${VER}",
  "skills_pin": "${PIN}",
  "run_id": "${GROK_LAB_RUN_ID:-}",
  "checks": ${checks_json}
}
EOF

echo "  wrote ${REPORT_PATH}"
echo ""
echo "summary  pass=${PASS} warn=${WARN} fail=${FAIL} hard_fail=${HARD_FAIL} status=${status_overall}"
echo "report   ${REPORT_PATH}"

# Optional forge metrics when under lab forge / arena forge wrap
if [[ -n "${GROK_LAB_RUN_ID:-}" ]] && command -v python3 >/dev/null 2>&1; then
  LAB_AUDIT_PASS="$PASS" LAB_AUDIT_WARN="$WARN" LAB_AUDIT_FAIL="$FAIL" \
    python3 - <<'PY' 2>/dev/null || true
import os
try:
    from forge import Forge
    f = Forge()
    f.log_param("pipeline", "lab-audit")
    f.log_param("kind", "script")
    f.log_metric("n_pass", float(os.environ.get("LAB_AUDIT_PASS", "0")))
    f.log_metric("n_warn", float(os.environ.get("LAB_AUDIT_WARN", "0")))
    f.log_metric("n_fail", float(os.environ.get("LAB_AUDIT_FAIL", "0")))
except Exception:
    pass
PY
fi

if [[ "$HARD_FAIL" -gt 0 ]]; then
  exit 1
fi
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0

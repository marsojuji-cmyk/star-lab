#!/usr/bin/env bash
# shipcheck.sh — offline local ship gate for Grok Star Lab
# Exit 0 = ready to ship (or checks skipped cleanly); non-zero = hard fail.
#
# Local checks: key file presence (+ optional doctor). Tests run when found;
# if no test harness is detected, tests are skipped (not a failure).
set -euo pipefail

ROOT="${ROOT:-}"
if [[ -z "$ROOT" ]]; then
  _sc_src="${BASH_SOURCE[0]}"
  while [[ -L "$_sc_src" ]]; do
    _sc_dir="$(cd "$(dirname "$_sc_src")" && pwd)"
    _sc_link="$(readlink "$_sc_src")"
    if [[ "$_sc_link" != /* ]]; then
      _sc_src="${_sc_dir}/${_sc_link}"
    else
      _sc_src="$_sc_link"
    fi
  done
  ROOT="$(cd "$(dirname "$_sc_src")/../.." && pwd)"
  unset _sc_src _sc_dir _sc_link
fi
export ROOT

# shellcheck disable=SC1091
if [[ -f "${ROOT}/lib/common.sh" ]]; then
  # shellcheck source=../../lib/common.sh
  source "${ROOT}/lib/common.sh"
fi

PROJECT_DIR="${1:-$(pwd)}"
PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
NO_DOCTOR=0
for arg in "${@:2}"; do
  case "$arg" in
    --no-doctor) NO_DOCTOR=1 ;;
  esac
done

pass=0
warn=0
fail=0
tests_ran=0
tests_skipped=0
capture_skip_reasons=()

ok()   { echo "  ${GRN:-}✓${RST:-} $*"; pass=$((pass + 1)); }
warn() { echo "  ${YLW:-}!${RST:-} $*"; warn=$((warn + 1)); }
bad()  { echo "  ${RED:-}✗${RST:-} $*"; fail=$((fail + 1)); }

echo "${BLD:-}Ship Bay · shipcheck${RST:-}"
echo "  project: ${PROJECT_DIR}"
echo "  repo:    ${ROOT}"

# --- 1. Git presence + branch hygiene ---
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ok "git work tree"
  branch="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "  branch:  ${branch}"
  if [[ "$branch" == "main" || "$branch" == "master" ]]; then
    warn "on ${branch} — prefer a feature branch before shipping"
  fi
  if [[ "$branch" == wip/* || "$branch" == tmp/* ]]; then
    warn "branch matches wip/* or tmp/* — auto-capture will skip"
    capture_skip_reasons+=("wip_or_tmp_branch")
  fi
else
  bad "not a git work tree: ${PROJECT_DIR}"
fi

# --- 2. Simple file presence (lab monorepo or generic project) ---
if [[ -f "${PROJECT_DIR}/AGENTS.md" || -f "${PROJECT_DIR}/Agents.md" ]]; then
  ok "AGENTS.md present"
else
  warn "no AGENTS.md (optional for non-lab projects)"
fi

if [[ -f "${PROJECT_DIR}/README.md" ]]; then
  ok "README.md present"
else
  warn "no README.md"
fi

# Lab monorepo markers when PROJECT_DIR is the lab root
if [[ -d "${PROJECT_DIR}/bin" && -d "${PROJECT_DIR}/modules" ]]; then
  for f in bin/lab bin/doctor lib/lab_paths.py; do
    if [[ -e "${PROJECT_DIR}/${f}" ]]; then
      ok "lab file ${f}"
    else
      bad "missing lab file ${f}"
    fi
  done
fi

# --- 3. Optional doctor (lab root only; skip if --no-doctor) ---
if [[ "$NO_DOCTOR" -eq 0 && -x "${ROOT}/bin/doctor" ]]; then
  if [[ "$(cd "$PROJECT_DIR" && pwd)" == "$(cd "$ROOT" && pwd)" ]] || \
     [[ -f "${PROJECT_DIR}/bin/doctor" ]]; then
    set +e
    "${ROOT}/bin/doctor" >/dev/null 2>&1
    doc_code=$?
    set -e
    if [[ "$doc_code" -eq 0 ]]; then
      ok "doctor exit 0"
    else
      warn "doctor exit ${doc_code} (non-blocking for shipcheck stub)"
    fi
  fi
fi

# --- 4. Detect & run tests; skip cleanly if none ---
run_tests() {
  local dir="$1"
  # Prefer project-local test scripts under tests/
  if [[ -d "${dir}/tests" ]]; then
    local scripts=()
    local s
    # Portable: no GNU sort -z; collect then sort by name via newline list.
    while IFS= read -r s; do
      [[ -n "$s" ]] && scripts+=("$s")
    done < <(find "${dir}/tests" -maxdepth 1 -type f \( -name 'test_*.sh' -o -name 'test-*.sh' \) 2>/dev/null | LC_ALL=C sort)
    if [[ ${#scripts[@]} -gt 0 ]]; then
      local sc
      for sc in "${scripts[@]}"; do
        echo "  run: bash ${sc}"
        set +e
        bash "$sc"
        local code=$?
        set -e
        if [[ "$code" -eq 0 ]]; then
          ok "tests $(basename "$sc")"
        else
          bad "tests $(basename "$sc") exit ${code}"
        fi
        tests_ran=1
      done
      return 0
    fi
  fi

  if [[ -f "${dir}/package.json" ]] && command -v npm >/dev/null 2>&1; then
    if grep -Eq '"test"[[:space:]]*:' "${dir}/package.json" 2>/dev/null; then
      echo "  run: npm test"
      set +e
      (cd "$dir" && npm test)
      local code=$?
      set -e
      tests_ran=1
      if [[ "$code" -eq 0 ]]; then ok "npm test"; else bad "npm test exit ${code}"; fi
      return 0
    fi
  fi

  if command -v python3 >/dev/null 2>&1; then
    if [[ -f "${dir}/pytest.ini" || -f "${dir}/pyproject.toml" ]] || \
       compgen -G "${dir}/test_*.py" >/dev/null 2>&1 || \
       compgen -G "${dir}/tests/test_*.py" >/dev/null 2>&1; then
      if python3 -c "import pytest" 2>/dev/null; then
        echo "  run: python3 -m pytest"
        set +e
        (cd "$dir" && python3 -m pytest -q)
        local code=$?
        set -e
        tests_ran=1
        if [[ "$code" -eq 0 ]]; then ok "pytest"; else bad "pytest exit ${code}"; fi
        return 0
      fi
    fi
  fi

  if [[ -f "${dir}/Makefile" ]] && grep -Eq '^test:' "${dir}/Makefile" 2>/dev/null; then
    echo "  run: make test"
    set +e
    (cd "$dir" && make test)
    local code=$?
    set -e
    tests_ran=1
    if [[ "$code" -eq 0 ]]; then ok "make test"; else bad "make test exit ${code}"; fi
    return 0
  fi

  # No harness detected
  tests_skipped=1
  ok "no tests detected — skip (not a failure)"
  return 0
}

run_tests "$PROJECT_DIR"

# --- 5. Diffstat (informational) ---
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo
  echo "${DIM:-}diffstat:${RST:-}"
  git -C "$PROJECT_DIR" diff --stat HEAD 2>/dev/null | sed 's/^/  /' || true
  dirty="$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  echo "  dirty_paths: ${dirty}"
fi

# --- 6. Lightweight secrets scan on diff (capture skip only) ---
if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  diff_txt="$(git -C "$PROJECT_DIR" diff HEAD 2>/dev/null || true)"
  if echo "$diff_txt" | grep -Eq 'API_KEY=|BEGIN (RSA |OPENSSH )?PRIVATE KEY|api[_-]?key[[:space:]]*='; then
    warn "secrets-like pattern in diff — auto-capture will skip"
    capture_skip_reasons+=("secrets_in_diff")
  fi
  if git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null | grep -Eq '(^|/)\.env($|\.)'; then
    warn ".env path in diff — auto-capture will skip"
    capture_skip_reasons+=("env_path_in_diff")
  fi
fi

echo
echo "────────────────────────────────────"
echo "pass=${pass} warn=${warn} fail=${fail} tests_ran=${tests_ran} tests_skipped=${tests_skipped}"
if [[ ${#capture_skip_reasons[@]} -gt 0 ]]; then
  echo "capture_skip=${capture_skip_reasons[*]}"
fi

if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
exit 0

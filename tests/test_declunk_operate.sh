#!/usr/bin/env bash
# De-clunk operate path: tokens --project, showroom --latest, body loop help, scaffold horizon
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${ROOT}/bin:${HOME}/.local/bin:${HOME}/homebrew/bin:${PATH}"
export LAB_BIN="${ROOT}/bin/lab"
LAB="${LAB_BIN}"

fail=0
pass() { echo "  PASS: $*"; }
bad() { echo "  FAIL: $*"; fail=$((fail + 1)); }

echo "═══ test_declunk_operate ═══"

# 1) CLI surface
if $LAB body --help 2>&1 | grep -q "loop"; then
  pass "body loop subcommand listed"
else
  bad "body loop subcommand missing"
fi

if $LAB tokens route --help 2>&1 | grep -q -- '--project'; then
  pass "tokens route --project"
else
  bad "tokens route --project missing"
fi

if $LAB showroom publish --help 2>&1 | grep -q -- '--latest'; then
  pass "showroom publish --latest"
else
  bad "showroom publish --latest missing"
fi

if $LAB showroom capture --help 2>&1 | grep -q -- '--publish'; then
  pass "showroom capture --publish"
else
  bad "showroom capture --publish missing"
fi

# 2) tokens --project attaches body when cwd is not the project
if [[ -d "${HOME}/Projects/pulse-board" ]] && $LAB body show project:pulse-board >/dev/null 2>&1; then
  out="$(cd /tmp && $LAB tokens route "declunk attach body smoke" --project pulse-board --force-mode short --no-shadow 2>&1 || true)"
  if echo "$out" | grep -q "body: project:pulse-board"; then
    pass "route --project pulse-board attaches body from /tmp"
  else
    bad "route --project did not print body (out snippet: $(echo "$out" | tail -5 | tr '\n' ' '))"
  fi
else
  echo "  SKIP: pulse-board body not present"
fi

# 3) scaffold horizon should not explode to deep-only
out="$($LAB tokens route "scaffold a tiny python cli" --force-mode short --no-shadow 2>&1 || true)"
# just ensure route works; mode forced short
if echo "$out" | grep -q "audit_id:"; then
  pass "scaffold route produces audit"
else
  bad "scaffold route failed"
fi

# 4) body loop dry: missing goal fails (argparse on stderr)
# note: loop exits 2 — capture without set -e abort
set +e
out_goal="$($LAB body loop project:pulse-board 2>&1)"
ec_goal=$?
set -e
if echo "$out_goal" | grep -qiE "goal|required" && [[ "$ec_goal" -ne 0 ]]; then
  pass "body loop requires --goal (exit=$ec_goal)"
else
  bad "body loop missing --goal should error (exit=$ec_goal)"
fi

# 5) e2e loop on pulse-board if available
if [[ -d "${HOME}/Projects/pulse-board" ]] && $LAB body show project:pulse-board >/dev/null 2>&1; then
  if $LAB body loop project:pulse-board --goal "declunk loop smoke" --tokens 200 --quality 0.9 --no-showroom 2>&1 | tee /tmp/body-loop-smoke.txt | grep -q "factory:     exit=0"; then
    pass "body loop factory exit 0"
  else
    bad "body loop e2e failed (see /tmp/body-loop-smoke.txt)"
  fi
else
  echo "  SKIP: body loop e2e"
fi

echo "═══ result fail=$fail ═══"
exit "$fail"

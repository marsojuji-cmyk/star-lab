#!/usr/bin/env bash
# SessionStart: activate Token-Aware Control Plane automatically.
set -euo pipefail

export PATH="${HOME}/.local/bin:${HOME}/homebrew/bin:${HOME}/.grok/bin:${PATH}"
LAB_REPO="${GROK_LAB_REPO:-${HOME}/Projects/grok-home}"
LAB_BIN="${HOME}/.local/bin/lab"

# Keep symlink pointed at the live lab tree (not a stale worktree).
if [[ -x "${LAB_REPO}/bin/lab" ]]; then
  mkdir -p "${HOME}/.local/bin"
  ln -sfn "${LAB_REPO}/bin/lab" "${LAB_BIN}" 2>/dev/null || true
fi

mkdir -p "${HOME}/.grok/lab"
export GROK_LAB_DATA="${GROK_LAB_DATA:-${HOME}/.grok/lab}"
export GROK_TOKEN_POLICY=1
export GROK_TOKEN_AUTO=1

BOOT_JSON="${GROK_LAB_DATA}/session_token_boot.json"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
MODE_LINE="unknown"

if [[ -x "${LAB_BIN}" ]] || [[ -x "${LAB_REPO}/bin/lab" ]]; then
  LAB="${LAB_BIN}"
  [[ -x "${LAB}" ]] || LAB="${LAB_REPO}/bin/lab"
  # Default session posture: short until a hard task is routed.
  ROUTE_OUT="$("${LAB}" tokens route --json "session boot: prefer local tools; escalate only when EV justifies" 2>/dev/null || true)"
  if [[ -n "${ROUTE_OUT}" ]]; then
    MODE_LINE="$(printf '%s' "${ROUTE_OUT}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("mode","?"), d.get("budget_tokens",0), d.get("audit_id",""))' 2>/dev/null || echo "parse-fail")"
    printf '%s\n' "${ROUTE_OUT}" > "${GROK_LAB_DATA}/session_token_last_route.json" 2>/dev/null || true
  fi
else
  MODE_LINE="lab-missing"
fi

export BOOT_JSON ROUTE_MODE="${MODE_LINE}" TS LAB_REPO
python3 - << 'PY'
import json, os
path = os.environ["BOOT_JSON"]
mode_line = os.environ.get("ROUTE_MODE", "")
parts = mode_line.split()
mode = parts[0] if parts else "unknown"
budget = parts[1] if len(parts) > 1 else "0"
audit = parts[2] if len(parts) > 2 else ""
doc = {
    "schema_version": 1,
    "ts": os.environ.get("TS"),
    "token_policy": "active",
    "default_mode": mode,
    "budget_tokens": int(budget) if str(budget).isdigit() else 0,
    "audit_id": audit,
    "lab_repo": os.environ.get("LAB_REPO"),
    "doctrine": (
        "Token awareness is the operating policy. "
        "Route every non-trivial user task with `lab tokens route` before deep/multi-agent work. "
        "Never burn deep budget on ops/cheap tasks. Escalation must beat local EV."
    ),
    "commands": {
        "route": "lab tokens route \"<task>\"",
        "complete": "lab tokens complete --audit-id ID --actual-tokens N --quality 0.0-1.0",
        "stats": "lab tokens audit --stats",
        "policy": "lab tokens policy",
    },
}
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
try:
    os.chmod(path, 0o600)
except OSError:
    pass
print(json.dumps(doc))
PY

echo ""
echo "[token-policy] ACTIVE · session boot"
echo "[token-policy] default_route: ${MODE_LINE}"
echo "[token-policy] marker: ${BOOT_JSON}"
echo "[token-policy] doctrine: every non-trivial task → lab tokens route before deep work"
echo "[token-policy] ops/cheap → local|short only; escalate only if EV > local"
echo "[grok-home] lab=${LAB_REPO}/bin/lab · Projects=${HOME}/Projects"

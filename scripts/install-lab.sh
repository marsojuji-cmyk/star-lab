#!/usr/bin/env bash
# install-lab.sh — idempotent Grok Star Lab bootstrap
# Creates ~/.grok/lab (0700), reads packaging/VERSION, symlinks ~/.local/bin/lab.
# Does NOT clobber safety hooks, deny rules, or user skills outside packaging install.
set -euo pipefail

# Resolve repo root (script lives in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export ROOT

# shellcheck disable=SC1091
if [[ -f "${ROOT}/lib/common.sh" ]]; then
  # shellcheck source=../lib/common.sh
  source "${ROOT}/lib/common.sh"
fi

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      cat << EOF
Usage: install-lab.sh [--dry-run]

  Create ~/.grok/lab (mode 0700) and standard subdirs
  Record packaging/VERSION as skills_version pin
  Symlink ~/.local/bin/lab -> repo bin/lab

Does not modify safety hooks, deny lists, or permission_mode.
EOF
      exit 0
      ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

LAB_DATA="${GROK_LAB_DATA:-${HOME}/.grok/lab}"
LOCAL_BIN="${HOME}/.local/bin"
LAB_BIN="${ROOT}/bin/lab"
VERSION_FILE="${ROOT}/packaging/VERSION"
VERSION="0.1.0"
if [[ -f "$VERSION_FILE" ]]; then
  VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
fi

echo "Grok Star Lab install"
echo "  repo:    ${ROOT}"
echo "  data:    ${LAB_DATA}"
echo "  version: ${VERSION}"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "  mode:    dry-run"
fi

# 1. Lab data directories (0700). Never touch hooks under ~/.grok/hooks.
SUBDIRS=(
  "${LAB_DATA}"
  "${LAB_DATA}/experiments"
  "${LAB_DATA}/metrics/daily"
  "${LAB_DATA}/knowledge"
  "${LAB_DATA}/knowledge/embeddings"
  "${LAB_DATA}/showroom/inbox"
  "${LAB_DATA}/imagine/runs"
  "${LAB_DATA}/gym/results"
)

for d in "${SUBDIRS[@]}"; do
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] mkdir -p -m 0700 ${d}"
  else
    mkdir -p -m 0700 "$d"
  fi
done
# Force 0700 on entire lab tree (mkdir -p may leave intermediate dirs at umask).
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] chmod -R u=rwX,go= ${LAB_DATA}"
else
  if [[ -d "$LAB_DATA" ]]; then
    find "$LAB_DATA" -type d -exec chmod 0700 {} + 2>/dev/null || true
    find "$LAB_DATA" -type f -exec chmod 0600 {} + 2>/dev/null || true
  fi
fi

# 2. Pin skills_version from packaging/VERSION (idempotent write)
PIN_FILE="${LAB_DATA}/.skills_version"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] write ${PIN_FILE} = ${VERSION}"
else
  printf '%s\n' "$VERSION" > "$PIN_FILE"
  chmod 0600 "$PIN_FILE" 2>/dev/null || true
fi

# 3. Minimal lab config if missing (do not overwrite existing)
LAB_CFG="${LAB_DATA}/config.toml"
if [[ ! -f "$LAB_CFG" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] write ${LAB_CFG}"
  else
    cat > "$LAB_CFG" << EOF
# Grok Star Lab — local config (created by install-lab.sh)
[lab]
skills_version = "${VERSION}"
default_model = "dolphin3:latest"
showroom_auto_capture = true
EOF
    chmod 0600 "$LAB_CFG" 2>/dev/null || true
  fi
else
  echo "  config:  keep existing ${LAB_CFG}"
fi

# 4. Symlink ~/.local/bin/lab -> bin/lab (idempotent; replace only if wrong link)
if [[ ! -x "$LAB_BIN" && ! -f "$LAB_BIN" ]]; then
  echo "error: lab binary missing: ${LAB_BIN}" >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] mkdir -p ${LOCAL_BIN}"
  echo "[dry-run] ln -sfn ${LAB_BIN} ${LOCAL_BIN}/lab"
else
  mkdir -p "$LOCAL_BIN"
  target="${LOCAL_BIN}/lab"
  if [[ -L "$target" ]]; then
    current="$(readlink "$target" 2>/dev/null || true)"
    if [[ "$current" == "$LAB_BIN" ]]; then
      echo "  symlink: already ${target} -> ${LAB_BIN}"
    else
      ln -sfn "$LAB_BIN" "$target"
      echo "  symlink: updated ${target} -> ${LAB_BIN}"
    fi
  elif [[ -e "$target" ]]; then
    echo "error: ${target} exists and is not a symlink; refuse to clobber" >&2
    exit 1
  else
    ln -sfn "$LAB_BIN" "$target"
    echo "  symlink: ${target} -> ${LAB_BIN}"
  fi
fi

# Explicit non-goals: never touch safety hooks
# ~/.grok/hooks/safety-guard.json and scripts/safety_guard.py are left alone.

echo "Install complete."
echo "  Try: lab help"
echo "       lab doctor"
echo "       lab status"

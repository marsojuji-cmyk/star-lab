#!/usr/bin/env bash
# Run after: gh auth login
# Needs scopes: repo (+ workflow if .github/workflows exists)
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh not on PATH" >&2
  exit 1
fi

gh auth status
# Ensure git can push over HTTPS without interactive username prompts
gh auth setup-git

USER=$(gh api user --jq .login)
if ! gh repo view "$USER/grok-home" >/dev/null 2>&1; then
  # Create may need workflow scope when repo contains Actions YAML
  if ! gh repo create grok-home --private --description "Grok Star Lab — free local agent laboratory" --source=. --remote=github --push; then
    echo "hint: if create/push failed on workflows, run:" >&2
    echo "  gh auth refresh -h github.com -s workflow" >&2
    echo "  gh auth setup-git && git push -u github main" >&2
    exit 1
  fi
else
  git remote remove github 2>/dev/null || true
  git remote add github "https://github.com/${USER}/grok-home.git"
  if ! git push -u github main; then
    echo "hint: OAuth missing workflow scope is common. Run:" >&2
    echo "  gh auth refresh -h github.com -s workflow" >&2
    echo "  gh auth setup-git && git push -u github main" >&2
    exit 1
  fi
fi
git remote -v
echo "Done. GitHub: https://github.com/${USER}/grok-home"

#!/usr/bin/env bash
# Run after: gh auth login
set -euo pipefail
cd "$(dirname "$0")/.."
gh auth status
USER=$(gh api user --jq .login)
if ! gh repo view "$USER/grok-home" >/dev/null 2>&1; then
  gh repo create grok-home --private --description "Grok Star Lab — free local agent laboratory" --source=. --remote=github --push
else
  git remote remove github 2>/dev/null || true
  git remote add github "https://github.com/${USER}/grok-home.git"
  git push -u github main
fi
git remote -v
echo "Done. GitHub: https://github.com/${USER}/grok-home"

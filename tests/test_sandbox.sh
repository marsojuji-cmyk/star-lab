#!/usr/bin/env bash
# tests/test_sandbox.sh — PR11 Sandbox Range smoke
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${HOME}/.grok/bin:${HOME}/.local/bin:${HOME}/homebrew/bin:/usr/local/bin:${PATH}"

echo "test_sandbox.sh  root=${ROOT}"
python3 "${ROOT}/tests/test_sandbox.py"
echo "test_sandbox.sh  OK"

#!/usr/bin/env bash
# Prove token savings vs Claude-style unbounded baseline.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${ROOT}/bin:${HOME}/.local/bin:${PATH}"
export GROK_TOKEN_PACK="${GROK_TOKEN_PACK:-aggressive}"

echo "=== Star Lab token savings (pack=${GROK_TOKEN_PACK}) ==="
lab tokens savings vs-claude --pack aggressive "$@"
echo
echo "Doc: ${ROOT}/docs/TOKEN-SAVINGS-100X.md"
echo "Compare: ${ROOT}/docs/COMPARE-WITH-CLAUDE.md"

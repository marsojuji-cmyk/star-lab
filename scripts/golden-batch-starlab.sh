#!/usr/bin/env bash
# Run a small golden-workflow batch on starlab-demo (judgment default).
set -euo pipefail
export PATH="$HOME/.local/bin:$HOME/homebrew/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
lab sqc loop --file <(python3 -c 'import json;print(json.dumps([{"id":str(i),"text":"clean %d"%i,"is_correct":True} for i in range(50)]))') --plan single >/dev/null || true
# single real path
lab tokens route --json "Run starlab-demo unit tests" > /tmp/gbr.json
lab research start "Run starlab-demo unit tests" --repo starlab-demo --route-json /tmp/gbr.json
ID=$(lab research list --json | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["id"])')
python3 -m unittest discover -s "$HOME/Projects/starlab-demo/tests" -q
lab research action "$ID" --type validate --name unittest
lab research complete "$ID" --success yes --actual-tokens 500 --tests-passed yes --sqc-quality-ok yes
lab research kpi

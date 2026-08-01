# 10× Research Sprint — implemented

Implements the three build items from the 10× research plan.

## 1. Golden workflow logger

```bash
# After routing
lab tokens route --json "Fix tests in starlab-demo" > /tmp/route.json
lab research start "Fix tests in starlab-demo" --repo starlab-demo --route-json /tmp/route.json

# During work
lab research action <id> --type validate --name unittest

# Finish
lab research complete <id> --success yes --actual-tokens 2000 --tests-passed yes \
  --sqc-quality-ok yes --sqc-loop-id <loop>

lab research list
lab research kpi
```

DB: `~/.grok/lab/research_log.db`  
Schema: `modules/research/schema.py`

## 2. Hard SQC gate on distill

```bash
lab tokens distill          # exit 2 if last lab sqc loop not quality_sufficient
lab tokens distill --ungated   # bootstrap only
# or: GROK_SQC_DISTILL_UNGATED=1
```

Loop 3: annotate → `lab sqc loop` → only then distill.

## 3. KPI board

```bash
lab research kpi
# opens data at:
#   ~/.grok/lab/research_kpi.json
#   portal/kpi.html  (http://127.0.0.1:8765/portal/kpi.html)
```

Metrics: accepted_patch_rate, test_pass_rate, avg_tokens_per_success, recovery_rate,
latency, human interruptions, SQC pass rates, token audit MAE.

## Paper alignment

| Paper | This sprint |
|-------|-------------|
| Phase 1 logging | `lab research start/complete` |
| Loop 3 quality | SQC gate on distill |
| Loop 4 measure | `lab research kpi` + portal board |
| Token-aware policy | still `lab tokens route` |

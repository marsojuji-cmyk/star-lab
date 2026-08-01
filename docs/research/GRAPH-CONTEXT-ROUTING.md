# Graph context routing (L2) — token-constrained multi-agent carriage

**Status:** v1 heuristic (free offline)  
**CLI:** `lab graph …`  
**DB:** `~/.grok/lab/graph_routes.db`  
**Paper map:** RCR-Router role-aware context routing under hard token budgets

---

## Doctrine

Do **not** treat multi-agent work as a fixed workflow that dumps full memory at every node.

Treat the graph as a **token-constrained routing problem**:

| Element | Meaning |
|---------|---------|
| Node | Agent role + task stage |
| Edge | Context slice carried forward (cost = tokens) |
| Budget \(B_i\) | Per-node cap: \(\beta_{base}+\beta_{role}\) under L1 envelope |
| Decision | **pass** / **summarize** / **drop** per slice |

**North-star metric:** **cost per successful end-to-end task** (not raw token cuts).

Objective shape (aligned with RCR + lab EV):

```text
max_π  E[ TaskSuccess − λ · Σ tokens carried across nodes ]
```

---

## Two layers

| Layer | CLI | Serves |
|-------|-----|--------|
| L1 mode | `lab tokens route` (+ shadow dual-log) | local \| short \| medium \| deep |
| L2 context | `lab graph route-context` | which memory each role receives |

L1 packing emits `role_budgets` + `context_routing` hints for L2.

---

## Three gates (heuristic scorer)

1. **Role relevance** — keywords + item.role match  
2. **Task-stage priority** — plan / implement / validate / recover / …  
3. **Recency / importance** — half-life + failure/packet boost  

Then greedy fill under \(B_i\); overflow → summarize stub or drop.

| Policy | Behavior |
|--------|----------|
| `full` | Carry everything (baseline A) |
| `budgeted` | Cap by recency only (baseline B) |
| `role_aware` | 3-gate + budget (baseline C) |

---

## Commands

```bash
lab graph budget --role validator --stage validate --parent-budget 2000

lab graph route-context --role implementer --stage implement \
  --budget 400 --policy role_aware --memory /tmp/mem.json --log

lab graph ablate --role implementer --memory /tmp/mem.json --log

lab graph log-node --role planner --stage plan --in-tokens 100 --out-tokens 50
lab graph stats
lab graph list
```

Memory item shape:

```json
{
  "id": "fail1",
  "role": "validator",
  "stage": "validate",
  "kind": "failure",
  "text": "…",
  "ts": 1710000000.0,
  "importance": 0.9,
  "tokens": 80
}
```

---

## Expected gains (literature, not lab promises)

- RCR-style: often **~25–47%** fewer tokens vs full-context on multi-hop multi-agent setups.  
- Broader production stacks (routing + cache + budgets): **40–80%** is multi-lever — attribute carefully.

Always pair with **cost/success**.

---

## Ablation

```text
A full-context graph
B budgeted (recency only)
C budgeted + role-aware (this v1)
D learned routing (after logs + SQC gate)
```

---

## Related

| Piece | Role |
|-------|------|
| `lab research packet` | Structured escalate / edge payload |
| `lab research recover` | LEAD short-horizon on fail |
| `lab tokens shadow` | L1 dual-log (serve baseline) |
| `lab research kpi` | End-to-end cost/success |

## Open problems

1. Calibrated edge-cost under distribution shift  
2. Session-aware locks mid tool-loop  
3. Role budgets in multi-agent DAGs  
4. Multi-tenant KV isolation vs reuse  

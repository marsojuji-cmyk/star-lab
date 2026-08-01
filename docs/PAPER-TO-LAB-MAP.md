# Paper → Star Lab map

**Source:** `docs/research/grok_research_paper.pdf`  
**Extract:** `docs/research/GROK-OS-PAPER.md`  
**Title:** Architecting a Frontier-Leaning Grok Operating System

---

## Thesis (paper)

Grok becomes the **cloud frontier tier** of a Mac-local multi-agent OS. Local controllers + compression + token-aware orchestration + evaluation invoke Grok only when high-capability reasoning is worth the cost.

## What we already built vs paper

| Paper concept | Lab implementation |
|---------------|-------------------|
| Tier 1 control plane | `lab tokens` + SessionStart boot + home rules (heuristic ForgeRNN stand-in) |
| Routing skill | `lab tokens route` (local/short/medium/deep by EV) |
| Token budget skill (LenVM) | `modules/tokens/horizon.py` + policy λ·kilotokens |
| Loop 1 observe/compress/route | tokens route + knowledge FTS + packing + **context packets** + **lab graph** role-aware carriage |
| Loop 2 propose/validate/recover | forge run (`--recover`) + research recover + ship + gym + arena |
| Loop 3 annotate/audit/distill | **`lab sqc`** + `lab tokens complete` + `lab tokens distill` |
| Loop 4 measure/compare/redeploy | forge experiments, showroom, doctor, checklists |
| Annotation quality skill | **`modules/sqc`** risk scorer + acceptance sampling + quality loop |
| Distillation skill | tokens distill rules from audits (labels must pass SQC gate) |
| Grok Build as Cloud Pro | external TUI; lab optimizes *when* to escalate |
| 1000× system multiplier | product of fewer wasteful calls + cleaner context + recovery |
| Local model heads / MLX | **safetensors interchange** — `lab weights`; train anywhere, publish safetensors only |

## SQC figures → CLI

| Figure | Meaning | Command |
|--------|---------|---------|
| Fig 1 Iterative quality loop | Annotate → evaluate → improve or end | `lab sqc loop --file items.json` |
| Fig 2a Single sampling | Fixed n, accept if d ≤ c | `lab sqc sample --plan single` |
| Fig 2b Sequential / SPRT | Continue until accept/reject bounds | `lab sqc sample --plan sequential` |
| Fig 2c Double sampling | n1 then optional n2 | `lab sqc sample --plan double` |
| Fig 3 ASN curves | Expected inspections vs true error rate | `lab sqc asn` |
| Error modeling prioritization | Score likely bad labels | `lab sqc risk --file items.json` |
| Loop diagram | Mermaid of Fig 1 | `lab sqc diagram` |

## Loop 3 gate (operational rule)

```text
usage stream / annotations
    → lab sqc risk (prioritize)
    → lab sqc loop|sample (accept/reject/improve)
    → only if quality_sufficient:
         lab tokens distill  / promote traces
```

Do **not** distill training or routing data from rejected batches without corrections.

## Near-term paper roadmap alignment

| Phase (paper) | Status on this Mac |
|---------------|--------------------|
| Phase 1 logging/schema | forge + tokens audit DB + sqc loop log |
| Phase 2 local modeling | heuristic experts (LenVM-like, risk); real MLX models later |
| Phase 3 structured Grok orchestration | lab CLI + packing + validation hooks |
| Phase 4 distillation + A/B discipline | tokens distill; A/B sample-size still manual |

## Four highest-payoff moves (paper conclusion)

1. Compressed retrieval → `lab knowledge` (FTS V1; latent CLaRa later)  
2. Token-aware routing → `lab tokens`  
3. LEAD-style recovery → **`lab research recover`** + `forge --recover`  
4. Annotation auditing → **`lab sqc`**  
5. Role-aware context routing → **`lab graph`** (RCR-style L2; heuristic v1) 

---

*Local portal:* http://127.0.0.1:8765/portal/  
*Paper PDF:* `docs/research/grok_research_paper.pdf`

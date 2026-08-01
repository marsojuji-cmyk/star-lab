# Embedding expansion drift (before/after anchor tests)

**Status:** Lab rule (v1)  
**CLI:** `lab weights drift …`  
**Module:** `modules/weights/embedding_drift.py`

After tokenizer/vocab expansion and embedding remapping, **do not** rely on a single aggregate score. Use **before/after anchors** and **three task/representation slices**.

---

## Practical loop

1. **Baseline:** old tokenizer + old embeddings (pre-expansion)  
2. **Expanded:** new tokenizer + expanded embeddings  
3. Run the **same prompts** through both; record embeddings and optional task preds  
4. Score by slice → apply gate  

Pairs with:

- `docs/TOKENIZER-VERSIONING.md` (tokenizer-major, freeze-by-default)  
- `embedding_remap` on model `manifest.json`  

---

## Three slices

| Slice | Content | How to read drift |
|-------|---------|-------------------|
| **legacy** | Untouched old-vocab text | Drift here ⇒ disturbed embedding geometry (bad) |
| **new_token** | Text dominated by new tokens | Drift usually **expected** adaptation |
| **mixed** | New tokens + old vocab | Interaction / calibration effects |

If drift appears **only** on `new_token` → expected.  
If **legacy** also moves a lot → likely harmful geometry change.

---

## What to measure

| Metric | Meaning |
|--------|---------|
| **Cosine shift** | `1 - cos(emb_base, emb_exp)` per item; mean/max/p95 by slice |
| **Mean L2 displacement** | Representation move magnitude by slice |
| **NN stability** | Jaccard of top-k nearest neighbors before vs after |
| **Task slices** | Accuracy / score delta on legacy vs new vs mixed |

Optional prediction-error drift: when `score_*` present, track score delta by slice.

---

## Gate rule

| Verdict | When |
|---------|------|
| **expected** | Legacy shift low; new_token carries the displacement |
| **warning** | Legacy shift elevated **or** NN instability, but task metrics still flat → **watch**, do not hard-block |
| **harmful** | Stable lexical setup but **high legacy displacement + measurable task hit** (retrieval/class/routing quality) |
| **insufficient_data** | Missing paired embeddings |

Defaults (override via JSON config):

- legacy cosine-shift warn `0.05` / harm `0.12`  
- legacy task acc drop warn `1pp` / harm `3pp`  
- NN jaccard warn `< 0.5`  

---

## Input format (JSONL)

```json
{"id":"L1","text":"the cat sat","slice":"legacy","emb_baseline":[...],"emb_expanded":[...],"label":"A","pred_baseline":"A","pred_expanded":"A"}
{"id":"N1","text":"<NEW>","slice":"new_token","emb_baseline":[...],"emb_expanded":[...]}
{"id":"M1","text":"hi <NEW> there","slice":"mixed","emb_baseline":[...],"emb_expanded":[...]}
```

Embeddings can come from any runtime (MLX/PyTorch adapters); this module only scores pairs.

---

## Commands

```bash
lab weights drift example /tmp/slices.jsonl
lab weights drift eval /tmp/slices.jsonl
lab weights drift eval /tmp/slices.jsonl --json
lab weights drift eval /tmp/slices.jsonl --config gate.json
```

Exit codes: `0` expected · `1` warning · `2` harmful · `3` insufficient_data

---

## Promote / remap checklist

1. Tokenizer sealed (`lab weights tokenizer seal`)  
2. Model `embedding_remap=retrained` after fix  
3. Drift eval **expected** or **warning** (not harmful) on frozen slices  
4. Then `lab weights publish-check --strict`  

# Tokenizer-major versioning (Grok / MLX stack)

**Status:** Lab rule (v1)  
**Schema:** `modules/weights/schema/tokenizer_manifest.schema.json`  
**CLI:** `lab weights tokenizer …`  
**Model bind:** `lab weights manifest bind-tokenizer`

---

## Rule (one line)

**Freeze the tokenizer by default. Any change that can alter tokenization is a tokenizer major + new artifact; the model records that exact revision and loaders refuse mismatched hashes.**

---

## Why

Silent tokenizer edits corrupt:

- Token-aware routing / horizon prediction  
- Eval reproducibility  
- Embedding alignment (vocab size / id map)

Treat the tokenizer as its **own package**: `semver + content hash + parent lineage`.

---

## Versioning matrix

| Change | Tokenizer | Model |
|--------|-----------|--------|
| Vocab, merges, special-token **behavior** | **MAJOR** + new artifact | Point at new `tokenizer_version` + hash; **MAJOR** if embeddings not remapped (`embedding_remap=required_unmet` until fixed) |
| Controlled **append-only** tokens/merges | **MINOR** only if `tokenizer_mode=append_only` + provenance | **MINOR** after retrain/retrofit embeddings; else incompatible |
| Metadata-only | **PATCH** | PATCH if only re-pointing hash |

**In-place edit of a published tokenizer is forbidden.**

---

## Tokenizer package layout

```text
tokenizer_package/
  tokenizer_manifest.json   # required
  tokenizer.json            # and/or vocab.json, merges.txt, …
  special_tokens_map.json   # optional
  provenance.jsonl          # optional append-only history
```

### Required manifest fields

`schema_version`, `tokenizer_id`, `version`, `tokenizer_hash`, `base_vocab_size`, `tokenizer_mode`, `created_at`

Plus: `special_tokens`, `merge_file_hash`, `added_tokens`, `added_merges`, `parent_version`, `compatibility_with_model`.

### Modes

| Mode | Meaning |
|------|---------|
| **frozen** | Default after training starts — no silent growth |
| **append_only** | Controlled extension with provenance |
| **dynamic** | Discouraged; loaders refuse unless `allow_dynamic` |

---

## Model manifest (schema 1.1.0)

When a model uses a tokenizer, set **all** of:

- `tokenizer_id`  
- `tokenizer_version`  
- `tokenizer_hash`  
- `tokenizer_uri` (e.g. `tokenizer/`)  
- `tokenizer_mode`  
- `embedding_remap`: `none` | `retrained` | `required_unmet`  

Loader API: `assert_tokenizer_compatible(model_manifest, tokenizer_manifest)` **before** `load_weights`.

---

## Commands

```bash
# Create frozen tokenizer artifact
lab weights tokenizer init ./tok --tokenizer-id lab.bpe --mode frozen --seal
lab weights tokenizer validate ./tok

# Breaking vocab change → new major (default part=major)
lab weights tokenizer bump ./tok --part major

# Bind into model package
lab weights manifest bind-tokenizer ./model --tokenizer ./tok --uri tokenizer
lab weights publish-check ./model --strict
```

---

## Dynamic growth (only if justified)

1. Set `tokenizer_mode=append_only`  
2. Record `added_tokens` / `added_merges` and `parent_version`  
3. Publish **new** version; do not overwrite  
4. Retrain or retrofit embeddings → `embedding_remap=retrained` on model  

---

## Related

- `docs/MODEL-MANIFEST.md`  
- `docs/SAFETENSORS-STANDARD.md`  
- `docs/EMBEDDING-DRIFT.md` — before/after anchor tests after embedding expansion 

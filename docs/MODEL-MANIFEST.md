# Model manifest + schema (versioning metadata)

**Status:** Lab rule (v1)  
**Schema:** `modules/weights/schema/model_manifest.schema.json` (`schema_version: 1.0.0`)  
**File:** `manifest.json` inside each model package  
**CLI:** `lab weights manifest …`

Weights stay in **safetensors**. Versioning, lineage, and deploy metadata stay in the **manifest**. Do not encode identity only in filenames.

---

## Separation

| Artifact | Role |
|----------|------|
| `*.safetensors` (+ optional index) | Tensor bytes only |
| `config.json` | Architecture hyperparams |
| `tokenizer/` | Tokenizer bundle |
| **`manifest.json`** | **Single source of truth** for version, lineage, hashes, compatibility |

Cross-platform loaders (PyTorch, MLX, serve stacks) read the same manifest; only thin adapters load weights.

---

## Required fields

| Field | Meaning |
|-------|---------|
| `schema_version` | Manifest **schema** semver (currently `1.0.0`) — independent of model version |
| `model_id` | Stable identity |
| `version` | Model `major.minor.patch` |
| `arch` | Architecture name |
| `framework` | `pytorch` \| `mlx` \| `jax` \| `numpy` \| `other` |
| `weights_uri` | Path inside package (`model.safetensors` or index) |
| `weights_format` | `safetensors` \| `safetensors_sharded` |
| `weights_sha256` | Integrity hash (see below) |
| `created_at` | ISO-8601 UTC |

## Strongly recommended

`parent_version`, `framework_version`, `tokenizer_id` + `tokenizer_version`, `tokenizer_uri`, `data_version`, `code_commit`, `env_hash`, `body_id`, `metrics`, `license`, `compatibility` (device, memory_mb_min, quantization, runtimes, notes).

---

## Versioning rule

| Bump | When |
|------|------|
| **major** | Breaking architecture or schema meaning change for consumers |
| **minor** | Backward-compatible capability / weight additions |
| **patch** | Metadata-only or non-breaking tweaks |

**Schema version** (`schema_version`) is versioned **separately** from **model version** (`version`).

```bash
lab weights manifest bump DIR --part minor
# sets parent_version to previous version
```

---

## Hash policy

| `weights_uri` | `weights_sha256` |
|---------------|------------------|
| Single `.safetensors` | SHA-256 of that file |
| `model.safetensors.index.json` | SHA-256 of sorted lines `shard:sha256(shard)` |

Mismatch → **publish blocker**.

---

## Validation / CI

```bash
lab weights manifest init DIR --model-id lab.example --arch tiny --framework mlx --seal
lab weights manifest validate DIR
lab weights publish-check DIR --strict   # requires valid manifest + no pickle
```

Release blockers:

- Missing required fields  
- Hash mismatch  
- Non-safetensors weights format  
- `tokenizer_id` without `tokenizer_version` (or reverse)

Optional: `pip install jsonschema` for full Draft 2020-12 checks; builtin required-field checks always run.

---

## Practical template

See schema file and `lab weights manifest schema`. Enough for reproducibility, rollback, canaries (`lab tokens rollout`), and cross-runtime loading.

---

## Related

- Weights format: `docs/SAFETENSORS-STANDARD.md`  
- Body ownership: `docs/design/2026-08-01-mind-and-body.md`  
- Progressive delivery: `docs/research/CLOSED-LOOP-GATES.md`  

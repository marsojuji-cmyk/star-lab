# Safetensors as lab interchange standard

**Status:** Lab rule (v1)  
**Date:** 2026-08-01  
**CLI:** `lab weights …`  
**Module:** `modules/weights/`

---

## Rule

| Phase | Format |
|-------|--------|
| **Train** | Whatever is convenient (PyTorch, MLX, JAX, …) |
| **Publish / promote** | **safetensors only** (`.safetensors` or sharded + index) |
| **Load** | Thin adapters → MLX / PyTorch / other runtimes |

**Never** use pickle / `torch.save` whole-module pickles as production or shared checkpoints.

---

## Why safetensors

- **Security:** no arbitrary code execution on load (unlike pickle)  
- **Speed:** memory-map friendly, zero-copy where supported  
- **Portability:** same tensors work across PyTorch, MLX (`load_weights` accepts `.safetensors`), and other runtimes via adapters  

---

## Canonical layout (one model package)

```text
model_package/
  config.json           # architecture + hyperparams (no weights)
  tokenizer/            # or tokenizer.json + merges/vocab (framework-agnostic bundle)
  model.safetensors     # single-file small models
  # OR sharded large models:
  model-00001-of-00003.safetensors
  model-00002-of-00003.safetensors
  model-00003-of-00003.safetensors
  model.safetensors.index.json   # weight_map: tensor_name → shard file
  manifest.json         # REQUIRED for publish: versioning metadata (JSON Schema)
```

See also: **`docs/MODEL-MANIFEST.md`** — schema fields, semver rules, hash policy.

### Separation of concerns

| Artifact | Contents |
|----------|----------|
| **Weights** | Tensors only (+ tensor names, shapes, dtypes in the safetensors header) |
| **Config** | JSON model architecture; no code, no weights |
| **Tokenizer** | Vocab/merges/special tokens; not embedded in the weight file |
| **Code** | Repo / package; never inside the checkpoint |

---

## MLX note

MLX 0.32+ can load `.safetensors` via `Module.load_weights(path)`. Local Apple Silicon workflows should stay **safetensors end-to-end** without a mandatory conversion detour after publish.

---

## Migration (PyTorch → standard)

```bash
# When torch + safetensors installed:
lab weights convert --input checkpoint.pt --output model.safetensors
lab weights validate model.safetensors
# Then load in each target runtime before promoting as lab standard
```

Validate **round-trip** in every runtime you care about before declaring a package “published.”

---

## Lab enforcement (soft → hard)

| Mode | Behavior |
|------|----------|
| Default | `lab weights validate` / `publish-check` warn on `.pt`/`.pkl` |
| `GROK_WEIGHTS_STRICT=1` | refuse to register packages that include pickle checkpoints |

Gym / future ForgeRNN heads: publish only packages that pass `lab weights publish-check`.

---

## Relationship to Star Lab

| Lab concept | Weights role |
|-------------|--------------|
| **Mind** | Inference runtime (Grok cloud / local MLX) |
| **Body** | May *own* paths to published weight packages under property maps |
| **Rollout / breakers** | Gate *serving* of a package; format is orthogonal but required for local heads |

---

## Commands

```bash
lab weights layout              # print canonical layout
lab weights validate PATH       # header / index checks
lab weights convert --input a.pt --output b.safetensors
lab weights publish-check DIR   # package completeness
lab weights metadata PATH       # dump tensor names/shapes if backend present
```

---

## References

- [Safetensors (PyTorch project)](https://pytorch.org/projects/safetensors/)  
- [MLX `Module.load_weights`](https://ml-explore.github.io/mlx/build/html/python/nn/_autosummary/mlx.nn.Module.load_weights.html)  
- Hugging Face sharded index conventions (`model.safetensors.index.json`)  

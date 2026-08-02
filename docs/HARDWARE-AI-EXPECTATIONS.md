# AI performance expectations — this machine

**Host:** Intel Mac (x86_64), 32 GB system RAM  
**GPU:** Radeon Pro Vega 20 — **4 GB HBM2** (discrete, PCIe)  
**iGPU:** Intel UHD Graphics 630 (~1.5 GB dynamic)  
**Date:** 2026-08-01  

This note turns hardware reality into **lab policy**: what to run locally, what to escalate to Grok, and how Star Lab fits.

---

## Bottom line

| Verdict | Detail |
|---------|--------|
| **Light local AI** | Yes — tiny quantized models, classical ML, experiments |
| **Serious local LLMs (7B–70B usable)** | No — VRAM + Metal-on-Intel+AMD are the wall |
| **Star Lab strategy** | **Correct for this box:** control plane + small local heads + **Grok as frontier mind** |

The Vega 20 is not a failed choice for *this lab*. The lab was designed so the expensive mind lives in the cloud and the Mac runs **policy, records, budgets, and small offline work**.

---

## Core limitations

1. **VRAM (~4 GB, usable often &lt; 3.5–3.8 GB after OS)** — Biggest bottleneck. Many 7B+ models do not fully fit even heavily quantized without RAM offload.  
2. **No CUDA** — Most NVIDIA-centric training/inference stacks are second-class or CPU-only.  
3. **Metal on Intel + discrete AMD** — Supported in places, optimized for Apple Silicon unified memory; PCIe copies add latency. Community patches help; not first-class.  
4. **Thermals** — Sustained AI = heat + throttling on a 15″ chassis (same as heavy edit/3D).

---

## What works reasonably well

| Workload | Expectation |
|----------|-------------|
| **Classical ML / small nets** | `tensorflow-metal` can accelerate small CNNs/dense nets (~1.5–2× CPU in favorable cases) until VRAM fills |
| **Tiny LLMs (1B–3B, quantized)** | Best local interactive case via `llama.cpp` Metal/Vulkan, Ollama where supported |
| **7B heavily quantized + offload** | Possible, often slow/frustrating; system RAM becomes the real workspace |
| **Core ML conversions** | Convenient Apple path; still 4 GB ceiling |
| **Star Lab control plane** | Fully local, CPU-friendly (Python CLIs, SQLite, heuristics) |
| **Ollama / gym smoke (e.g. dolphin3)** | Offline eval path already used by lab — keep models small |

## What does not work well

- Modern 7B–70B+ at usable quality *and* speed fully on GPU  
- Fine-tuning / training beyond small models  
- CUDA-only Hugging Face recipes without rewrite  
- High-res diffusion / large context / multi-model GPU stacks  
- Production daily AI solely on this dGPU  

---

## Realistic 2026 matrix (this host)

| Use case | Feasibility | Experience |
|----------|-------------|------------|
| 1B–3B quantized inference | Good | Usable if backends are solid |
| 7B heavily quantized | Marginal | Offload + slow; VRAM-bound |
| 13B+ interactive | Poor | Prefer CPU-only or cloud |
| Small classical training | Decent | TF Metal possible |
| Large fine-tune | Poor | Cloud / better GPU |
| SD-class image gen | Limited | Tiny/low-res only |
| Heavy daily local AI | Not recommended | M-series, NVIDIA, or cloud |

---

## How this maps to Star Lab (why our design fits)

| Lab layer | Role on Vega 20 host |
|-----------|----------------------|
| **Mind (Grok cloud)** | Hard reasoning, deep multi-file, long horizon — **default for serious work** |
| **Token EV / gates / rollout** | Decide when cloud is worth it; never burn deep budget on ops |
| **Graph context routing** | Cut context size so even *cloud* calls stay lean |
| **Body doctrine** | Persist records/limits offline without needing a local 70B |
| **lab weights (safetensors, manifest, tokenizer, drift)** | Package **small** local heads correctly when you train them |
| **gym / Ollama** | Smoke offline models that *fit*; not a substitute for Grok |

**Policy implication:** treat the Vega 20 as an **accelerator for layers/models that fit**, and system RAM (32 GB) as the overflow pool — not as an 8–24 GB local-LLM workstation.

---

## Practical tips on this machine

1. Prefer **llama.cpp** with AMD-friendly Metal patches or Vulkan/MoltenVK; keep Ollama models tiny.  
2. Quantize hard (Q3/Q4-class) and offload layers to RAM when needed.  
3. Close other GPU apps; watch Activity Monitor GPU memory.  
4. For classical ML: TensorFlow + `tensorflow-metal` (macOS 12+).  
5. Elevate laptop / cool ambient for sustained runs.  
6. **Do not** plan local training of large heads on-device; train elsewhere, **publish safetensors**, evaluate drift/gates on this Mac if the *artifact* is small enough to load.

---

## Star Lab operator rules (hardware-aware)

```text
IF task is ops/status/doctor          → local (no model)
IF task is tiny offline smoke         → Ollama / small quant / CPU OK
IF task needs real reasoning          → lab tokens route → Grok (short/medium/deep)
IF local head is published            → must fit RAM/VRAM plan; weights safetensors + manifest
NEVER assume CUDA or 12+ GB VRAM
```

---

## Upgrade paths (when AI work outgrows this box)

1. **Cloud GPUs** for train/fine-tune and large inference  
2. **Apple Silicon Mac** (unified memory + first-class Metal)  
3. **External / remote NVIDIA** for CUDA ecosystems  

Until then: this lab’s **control plane + cloud mind** design is the rational architecture for a Vega 20 + 32 GB Intel Mac.

---

## Sources / provenance

Operator brief (2026): Radeon Pro Vega 20 AI expectations (VRAM, Metal-on-Intel+AMD, llama.cpp/Ollama, TF Metal, thermal limits). Confirmed on-box via `system_profiler` (Vega 20 4 GB, UHD 630, 32 GB RAM, x86_64).

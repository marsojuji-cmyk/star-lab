"""Convert framework checkpoints → safetensors (optional torch/safetensors deps)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def convert_torch_to_safetensors(
    input_path: Path,
    output_path: Path,
    *,
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Load a PyTorch checkpoint (state_dict or {'state_dict': ...}) and write safetensors.

    Requires: torch, safetensors
    """
    try:
        import torch
    except ImportError as e:
        raise RuntimeError(
            "torch not installed; install torch to convert .pt checkpoints"
        ) from e
    try:
        from safetensors.torch import save_file
    except ImportError as e:
        raise RuntimeError(
            "safetensors not installed; pip/uv install safetensors"
        ) from e

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    obj = torch.load(str(input_path), map_location="cpu", weights_only=True)
    if isinstance(obj, dict) and "state_dict" in obj:
        state = obj["state_dict"]
    elif isinstance(obj, dict) and all(hasattr(v, "shape") for v in obj.values()):
        state = obj
    else:
        raise ValueError(
            "unsupported checkpoint shape; expected state_dict or dict of tensors"
        )

    # tensors only; drop non-tensor entries
    tensors = {}
    skipped = []
    for k, v in state.items():
        if hasattr(v, "detach"):
            tensors[k] = v.detach().cpu().contiguous()
        else:
            skipped.append(k)

    meta = {k: str(v) for k, v in (metadata or {}).items()}
    meta.setdefault("format", "pt")
    meta.setdefault("lab", "grok-home")
    save_file(tensors, str(output_path), metadata=meta)

    return {
        "ok": True,
        "input": str(input_path),
        "output": str(output_path),
        "n_tensors": len(tensors),
        "skipped_keys": skipped,
    }


def write_index(
    package_dir: Path,
    weight_map: Dict[str, str],
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write HuggingFace-style model.safetensors.index.json."""
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    path = package_dir / "model.safetensors.index.json"
    payload = {
        "metadata": metadata or {},
        "weight_map": weight_map,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path

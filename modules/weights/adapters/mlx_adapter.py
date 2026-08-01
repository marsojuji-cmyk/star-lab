"""MLX adapter: load .safetensors into an mlx.nn.Module via load_weights."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_mlx_weights(module: Any, path: Path, *, strict: bool = True) -> Any:
    """
    MLX 0.32+ Module.load_weights accepts .safetensors paths directly.

    module: mlx.nn.Module instance
    """
    path = Path(path)
    if not hasattr(module, "load_weights"):
        raise TypeError("module must be mlx.nn.Module with load_weights")
    # MLX API: load_weights(path) or load_weights(list of (name, array))
    module.load_weights(str(path), strict=strict)
    return module

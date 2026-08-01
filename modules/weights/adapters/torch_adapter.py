"""PyTorch adapter: load safetensors → state_dict."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def load_torch_state_dict(path: Path) -> Dict[str, Any]:
    path = Path(path)
    try:
        from safetensors.torch import load_file
    except ImportError as e:
        raise RuntimeError("requires safetensors[torch] or safetensors + torch") from e
    return load_file(str(path))

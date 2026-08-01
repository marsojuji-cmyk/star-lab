"""Thin load adapters — optional framework deps."""

from .torch_adapter import load_torch_state_dict
from .mlx_adapter import load_mlx_weights

__all__ = ["load_torch_state_dict", "load_mlx_weights"]

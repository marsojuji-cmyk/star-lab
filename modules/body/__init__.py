"""Body registry — identity, property, contact, limits for lab/project agents."""

from .schema import Body, BodyLimits, MODE_RANK, min_mode, apply_mode_caps
from .store import BodyStore
from .resolve import resolve_body

__all__ = [
    "Body",
    "BodyLimits",
    "BodyStore",
    "MODE_RANK",
    "min_mode",
    "apply_mode_caps",
    "resolve_body",
]

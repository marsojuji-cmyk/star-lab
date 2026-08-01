# Model Gym — offline-first eval harness (Ollama dolphin3 + optional remote Grok).
"""Public API for suite eval and model selection policy (K15, K20)."""

from .harness import (  # noqa: F401
    DEFAULT_MODEL,
    BEST_WORK_MODEL,
    EvalResult,
    load_suite,
    resolve_model,
    run_suite,
    score_case,
)

__all__ = [
    "DEFAULT_MODEL",
    "BEST_WORK_MODEL",
    "EvalResult",
    "load_suite",
    "resolve_model",
    "run_suite",
    "score_case",
]

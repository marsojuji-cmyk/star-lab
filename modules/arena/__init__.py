# Agent Arena — offline script pipelines + session-tier workflow handoff.
"""Catalog and run lab pipelines (K16, K19). No headless Rhai in v1."""

from .runner import (  # noqa: F401
    describe_pipeline,
    list_pipelines,
    load_pipeline,
    run_pipeline,
)

__all__ = [
    "describe_pipeline",
    "list_pipelines",
    "load_pipeline",
    "run_pipeline",
]

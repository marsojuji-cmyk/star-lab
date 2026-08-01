"""Canonical model package layout (framework-agnostic)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

# Files considered unsafe / non-standard for production publish
PICKLE_SUFFIXES = {".pt", ".pth", ".pkl", ".pickle", ".bin"}  # .bin often torch; still warn
SAFE_WEIGHT_SUFFIXES = {".safetensors"}

LAYOUT_DOC = """
model_package/
  manifest.json               # REQUIRED for publish: versioning metadata (JSON Schema)
  config.json                 # architecture hyperparams (no weights)
  tokenizer/                  # or tokenizer.json + related files
  model.safetensors           # small models
  # OR sharded:
  model-00001-of-NNNNN.safetensors
  model.safetensors.index.json
""".strip()

INDEX_NAME = "model.safetensors.index.json"
SINGLE_NAME = "model.safetensors"
CONFIG_NAME = "config.json"
META_NAME = "metadata.json"  # legacy optional; prefer manifest.json
MANIFEST_NAME = "manifest.json"


def is_pickle_checkpoint(path: Path) -> bool:
    return path.suffix.lower() in PICKLE_SUFFIXES


def is_safetensors_file(path: Path) -> bool:
    return path.suffix.lower() == ".safetensors"


def package_paths(root: Path) -> Dict[str, Optional[Path]]:
    """Locate standard artifacts under a package directory."""
    root = Path(root)
    index = root / INDEX_NAME
    single = root / SINGLE_NAME
    # also accept any *.safetensors if single missing
    shards = sorted(root.glob("*.safetensors")) if root.is_dir() else []
    return {
        "root": root if root.is_dir() else root.parent,
        "config": (root / CONFIG_NAME) if root.is_dir() else None,
        "index": index if index.is_file() else None,
        "single": single if single.is_file() else None,
        "shards": shards,
        "metadata": (root / META_NAME) if root.is_dir() and (root / META_NAME).is_file() else None,
        "manifest": (root / MANIFEST_NAME) if root.is_dir() and (root / MANIFEST_NAME).is_file() else None,
        "tokenizer_dir": (root / "tokenizer") if root.is_dir() and (root / "tokenizer").is_dir() else None,
        "tokenizer_json": (root / "tokenizer.json") if root.is_dir() and (root / "tokenizer.json").is_file() else None,
    }


def list_pickle_files(root: Path) -> List[Path]:
    root = Path(root)
    if not root.is_dir():
        return [root] if root.is_file() and is_pickle_checkpoint(root) else []
    out = []
    for p in root.rglob("*"):
        if p.is_file() and is_pickle_checkpoint(p):
            out.append(p)
    return out

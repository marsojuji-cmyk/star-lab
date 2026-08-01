# Python 3.9+ path helpers for Grok Star Lab.
"""Resolve monorepo root, ~/.grok, and ~/.grok/lab data paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


def grok_home() -> Path:
    """Grok runtime home (config, skills, hooks). Default: ~/.grok."""
    return Path(os.environ.get("GROK_HOME", str(Path.home() / ".grok")))


def lab_data_root() -> Path:
    """Mutable lab state root. Default: ~/.grok/lab."""
    override = os.environ.get("GROK_LAB_DATA")
    if override:
        return Path(override)
    return grok_home() / "lab"


def repo_root() -> Path:
    """
    Monorepo root (bin/, lib/, modules/, packaging/).

    Order:
      1. GROK_LAB_REPO if set
      2. Walk up from this file (lib/lab_paths.py -> repo root)
      3. ~/Projects/grok-home
    """
    env = os.environ.get("GROK_LAB_REPO")
    if env:
        return Path(env).resolve()

    here = Path(__file__).resolve()
    # lib/lab_paths.py -> parent is lib/, grandparent is repo root
    candidate = here.parent.parent
    if (candidate / "bin").is_dir() and (candidate / "lib").is_dir():
        return candidate

    return Path(os.environ.get("PROJECTS", str(Path.home() / "Projects"))) / "grok-home"


def ensure_lab_dirs() -> List[Path]:
    """
    Create ~/.grok/lab and standard subdirs with mode 0o700.
    Idempotent. Returns list of paths ensured.
    Does not touch safety hooks or other ~/.grok content outside lab/.
    """
    root = lab_data_root()
    subdirs = [
        root,
        root / "experiments",
        root / "metrics" / "daily",
        root / "knowledge",
        root / "knowledge" / "embeddings",
        root / "showroom" / "inbox",
        root / "imagine" / "runs",
        root / "gym" / "results",
    ]
    ensured: List[Path] = []
    for path in subdirs:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        ensured.append(path)
    # Force 0700 on whole tree (mkdir parents may use umask for intermediates).
    if root.is_dir():
        for dirpath, dirnames, filenames in os.walk(root):
            try:
                os.chmod(dirpath, 0o700)
            except OSError:
                pass
            for name in filenames:
                fpath = Path(dirpath) / name
                try:
                    os.chmod(fpath, 0o600)
                except OSError:
                    pass
    return ensured


# Convenience aliases matching design doc names
HOME = Path.home()
LAB_REPO = repo_root()
GROK_HOME = grok_home()
LAB_DATA = lab_data_root()
PROJECTS = Path(os.environ.get("PROJECTS", str(HOME / "Projects")))

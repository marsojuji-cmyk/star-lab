# Python 3.9+ Agent Arena runner
"""Load YAML pipeline registry; dispatch kind:script | kind:workflow.

v1 rules (K16, K19):
  - kind: script  → offline bash/python under lab arena run (optional forge wrap)
  - kind: workflow → print session-tier /workflow handoff only; no headless Rhai
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_LIB = _REPO / "lib"
for p in (str(_LIB), str(_HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from lab_paths import ensure_lab_dirs, grok_home, lab_data_root, repo_root  # noqa: E402

# Exit when workflow source file is missing (session handoff)
EXIT_WORKFLOW_MISSING = 2
# GNU timeout convention (align with forge)
EXIT_TIMEOUT = 124


def pipelines_dir(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "modules" / "arena" / "pipelines"


def scripts_dir(root: Optional[Path] = None) -> Path:
    return (root or repo_root()) / "modules" / "arena" / "scripts"


def load_simple_yaml(path: Path) -> Dict[str, Any]:
    """
    Minimal flat YAML loader (stdlib only — no PyYAML).

    Supports key: value scalars (str/bool/int/float), # comments, blank lines.
    Sufficient for arena pipeline registry files.
    """
    data: Dict[str, Any] = {}
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # strip trailing inline comment when not inside quotes
        if " #" in line and not (line.startswith("'") or line.startswith('"')):
            # only strip if key: value # comment form
            m = re.match(r"^([^:]+):\s*(.*?)\s+#.*$", line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
            else:
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
        else:
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
        if not key:
            continue
        data[key] = _coerce_scalar(val)
    return data


def _coerce_scalar(val: str) -> Any:
    if val == "":
        return ""
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        return val[1:-1]
    low = val.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", "~"):
        return None
    # int
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    # float
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    return val


def list_pipeline_files(root: Optional[Path] = None) -> List[Path]:
    d = pipelines_dir(root)
    if not d.is_dir():
        return []
    return sorted(d.glob("*.yaml")) + sorted(
        p for p in d.glob("*.yml") if p.suffix == ".yml"
    )


def load_pipeline(name: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """Load pipeline by name (stem) or path. Raises FileNotFoundError."""
    root = root or repo_root()
    # explicit path
    cand = Path(name)
    if cand.suffix in (".yaml", ".yml") and cand.is_file():
        data = load_simple_yaml(cand)
        data["_path"] = str(cand.resolve())
        data.setdefault("name", cand.stem)
        return data

    stem = name
    if stem.endswith(".yaml") or stem.endswith(".yml"):
        stem = Path(stem).stem

    for path in list_pipeline_files(root):
        if path.stem == stem:
            data = load_simple_yaml(path)
            data["_path"] = str(path.resolve())
            data.setdefault("name", path.stem)
            return data

    raise FileNotFoundError("pipeline not found: %s (looked in %s)" % (name, pipelines_dir(root)))


def list_pipelines(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in list_pipeline_files(root):
        try:
            data = load_simple_yaml(path)
        except OSError:
            continue
        data["_path"] = str(path.resolve())
        data.setdefault("name", path.stem)
        out.append(data)
    # stable by name
    out.sort(key=lambda p: str(p.get("name") or ""))
    return out


def describe_pipeline(pipe: Dict[str, Any]) -> str:
    lines = [
        "name:        %s" % pipe.get("name", "?"),
        "kind:        %s" % pipe.get("kind", "?"),
        "description: %s" % (pipe.get("description") or "—"),
        "path:        %s" % (pipe.get("_path") or "—"),
    ]
    kind = str(pipe.get("kind") or "").lower()
    if kind == "script":
        lines.append("script:      %s" % (pipe.get("script") or "—"))
        lines.append("forge:       %s" % pipe.get("forge", False))
        lines.append("timeout:     %s" % (pipe.get("timeout_secs") or "—"))
    elif kind == "workflow":
        lines.append("workflow_src:          %s" % (pipe.get("workflow_src") or "—"))
        lines.append(
            "workflow_install_name: %s" % (pipe.get("workflow_install_name") or "—")
        )
        lines.append("forge:                 %s" % pipe.get("forge", False))
        lines.append("note:        session-tier only (no headless Rhai in v1)")
    return "\n".join(lines)


def _resolve_script(pipe: Dict[str, Any], root: Path) -> Path:
    rel = pipe.get("script")
    if not rel:
        raise ValueError("pipeline %s: missing script:" % pipe.get("name"))
    p = Path(str(rel))
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def _child_env(root: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["GROK_LAB_REPO"] = str(root)
    env["GROK_LAB_DATA"] = str(lab_data_root())
    env["GROK_HOME"] = str(grok_home())
    env["ROOT"] = str(root)
    # Prefer lab PATH contract
    prepend = [
        str(root / "bin"),
        str(Path.home() / ".grok" / "bin"),
        str(Path.home() / ".local" / "bin"),
    ]
    env["PATH"] = os.pathsep.join(prepend + [env.get("PATH", "")])
    # PYTHONPATH for optional Forge logging from scripts
    py_pre = [str(root / "modules"), str(root / "lib")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        os.pathsep.join(py_pre + [existing]) if existing else os.pathsep.join(py_pre)
    )
    return env


def _run_script_direct(
    script: Path,
    root: Path,
    timeout: Optional[float],
    extra_args: Sequence[str] = (),
) -> int:
    if not script.is_file():
        print("error: script missing: %s" % script, file=sys.stderr)
        return 1
    cmd = ["bash", str(script)] + list(extra_args)
    env = _child_env(root)
    print("arena: kind=script script=%s" % script, file=sys.stderr)
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=str(root),
            timeout=timeout,
            check=False,
        )
        return int(proc.returncode)
    except subprocess.TimeoutExpired:
        print("arena: aborted (timeout %ss)" % timeout, file=sys.stderr)
        return EXIT_TIMEOUT
    except OSError as exc:
        print("arena: failed to start: %s" % exc, file=sys.stderr)
        return 126


def _run_script_with_forge(
    pipe: Dict[str, Any],
    script: Path,
    root: Path,
    timeout: Optional[float],
    extra_args: Sequence[str] = (),
) -> int:
    """Wrap via forge.run_command when forge: true. Falls back to direct on import error."""
    try:
        from forge.forge import ForgeStore, run_command  # type: ignore
    except ImportError as exc:
        print(
            "arena: forge unavailable (%s); running script without wrap" % exc,
            file=sys.stderr,
        )
        return _run_script_direct(script, root, timeout, extra_args)

    name = str(pipe.get("name") or "pipeline")
    cmd = ["bash", str(script)] + list(extra_args)
    tags = ["arena", name]
    store = ForgeStore()
    print("arena: kind=script forge=true exp=arena-%s" % name, file=sys.stderr)
    # forge.run_command sets GROK_LAB_RUN_ID and dual-writes
    return int(
        run_command(
            store,
            exp_name="arena-%s" % name,
            command=cmd,
            project="grok-home",
            tags=tags,
            timeout=timeout,
        )
    )


def run_script_pipeline(
    pipe: Dict[str, Any],
    root: Optional[Path] = None,
    extra_args: Sequence[str] = (),
    no_forge: bool = False,
) -> int:
    root = root or repo_root()
    ensure_lab_dirs()
    script = _resolve_script(pipe, root)
    timeout_raw = pipe.get("timeout_secs")
    timeout: Optional[float] = float(timeout_raw) if timeout_raw is not None else None
    use_forge = bool(pipe.get("forge")) and not no_forge
    if use_forge:
        return _run_script_with_forge(pipe, script, root, timeout, extra_args)
    return _run_script_direct(script, root, timeout, extra_args)


def _workflow_paths(pipe: Dict[str, Any], root: Path) -> Tuple[Optional[Path], Path, str]:
    """Return (source_path or None, install_path, install_name)."""
    install_name = str(
        pipe.get("workflow_install_name") or pipe.get("name") or "workflow"
    )
    install_path = grok_home() / "workflows" / ("%s.rhai" % install_name)
    src_rel = pipe.get("workflow_src")
    src: Optional[Path] = None
    if src_rel:
        p = Path(str(src_rel))
        if not p.is_absolute():
            p = root / p
        src = p
    return src, install_path, install_name


def handoff_prompt_text(pipe: Dict[str, Any], install_name: str) -> str:
    desc = pipe.get("description") or "Lab multi-agent workflow"
    return (
        "Please launch the Grok workflow named `%s` "
        "(or run `/workflow %s` in this session).\n"
        "Goal: %s\n"
        "Stay read-only unless the workflow explicitly requires writes. "
        "Summarize findings when done.\n"
    ) % (install_name, install_name, desc)


def run_workflow_handoff(
    pipe: Dict[str, Any],
    root: Optional[Path] = None,
    handoff_prompt_path: Optional[Path] = None,
) -> int:
    """
    Session-tier only (K19). Print install + /workflow instructions.
    Exit 0 if source or installed workflow present; exit 2 if both missing.
    Never executes Rhai headlessly.
    """
    root = root or repo_root()
    name = str(pipe.get("name") or "?")
    src, install_path, install_name = _workflow_paths(pipe, root)

    src_ok = bool(src and src.is_file())
    install_ok = install_path.is_file()

    print("=== Agent Arena: session-tier handoff ===")
    print("pipeline:     %s" % name)
    print("kind:         workflow")
    print("description:  %s" % (pipe.get("description") or "—"))
    print("")
    print("This pipeline requires a Grok session.")
    print("v1 does not run Rhai headlessly (K19). No --try-headless.")
    print("")
    print("1) Ensure workflow source / install")
    if src is not None:
        print("   source:     %s  [%s]" % (src, "ok" if src_ok else "MISSING"))
    else:
        print("   source:     (not specified in pipeline YAML)")
    print(
        "   installed:  %s  [%s]"
        % (install_path, "ok" if install_ok else "not installed")
    )
    if not install_ok:
        print("   Install tip: copy packaging workflow into ~/.grok/workflows/")
        print("     mkdir -p ~/.grok/workflows")
        if src is not None:
            print("     cp %s ~/.grok/workflows/%s.rhai" % (src, install_name))
        print("     # or re-run lab install when packaging install is wired")
    print("")
    print("2) In a Grok session started from the lab/repo, run:")
    print("     /workflow %s" % install_name)
    print("   Or ask the agent to launch the named workflow \"%s\"." % install_name)
    print("")

    prompt = handoff_prompt_text(pipe, install_name)
    if handoff_prompt_path is not None:
        handoff_prompt_path = Path(handoff_prompt_path)
        handoff_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        handoff_prompt_path.write_text(prompt, encoding="utf-8")
        print("3) Handoff prompt written to:")
        print("     %s" % handoff_prompt_path)
        print("   Paste that file into the session if /workflow is unavailable.")
    else:
        print("3) Optional paste prompt (use --handoff-prompt FILE to save):")
        for line in prompt.strip().splitlines():
            print("   | %s" % line)
    print("")
    print("arena: handoff complete (no headless execution)")

    if not src_ok and not install_ok:
        print(
            "error: workflow file missing (source and install both absent)",
            file=sys.stderr,
        )
        return EXIT_WORKFLOW_MISSING
    return 0


def run_pipeline(
    name: str,
    root: Optional[Path] = None,
    extra_args: Sequence[str] = (),
    no_forge: bool = False,
    handoff_prompt: Optional[Path] = None,
) -> int:
    """Dispatch by kind. Returns process exit code."""
    root = root or repo_root()
    try:
        pipe = load_pipeline(name, root=root)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    kind = str(pipe.get("kind") or "").lower().strip()
    if kind == "script":
        return run_script_pipeline(
            pipe, root=root, extra_args=extra_args, no_forge=no_forge
        )
    if kind == "workflow":
        return run_workflow_handoff(pipe, root=root, handoff_prompt_path=handoff_prompt)
    print(
        "error: unknown pipeline kind %r (expected script|workflow)" % kind,
        file=sys.stderr,
    )
    return 2

# Python 3.9+ Model Gym harness — offline Ollama + optional remote Grok (K15, K20).
"""
Eval harness for JSONL prompt suites.

Offline core (default / smoke):
  model  = dolphin3:latest
  backend = Ollama HTTP  http://127.0.0.1:11434

Best-work track (`--track best`):
  Prefer remote Grok when XAI_API_KEY or GROK is set in the environment;
  otherwise fall back to dolphin3:latest and log model_fallback=true.

No paid SaaS required for offline core. Unit tests mock HTTP (no network).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── defaults (K15 / K20) ─────────────────────────────────────────────

DEFAULT_MODEL = "dolphin3:latest"
BEST_WORK_MODEL = "grok-4"  # remote id when authed; adjust via env GROK_LAB_BEST_MODEL
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
XAI_API_BASE = os.environ.get("XAI_API_BASE", "https://api.x.ai/v1").rstrip("/")
DEFAULT_TIMEOUT_SECS = 120.0

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
SUITES_DIR = _HERE / "suites"


# ── data ─────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    id: str
    prompt: str
    response: str
    passed: bool
    reason: str = ""


@dataclass
class EvalResult:
    suite: str
    model: str
    backend: str  # "ollama" | "xai" | "skip"
    track: str
    model_fallback: bool
    n_total: int
    n_pass: int
    pass_rate: float
    cases: List[CaseResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        if self.skipped:
            return True
        if self.error:
            return False
        return self.n_total > 0 and self.n_pass == self.n_total


# ── suite I/O ────────────────────────────────────────────────────────


def suites_dir() -> Path:
    return SUITES_DIR


def resolve_suite_path(name_or_path: str) -> Path:
    """Resolve suite name (smoke) or filesystem path to a .jsonl file."""
    p = Path(name_or_path)
    if p.is_file():
        return p.resolve()
    # bare name → suites/<name>.jsonl
    base = name_or_path
    if base.endswith(".jsonl"):
        base = base[: -len(".jsonl")]
    candidate = SUITES_DIR / ("%s.jsonl" % base)
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        "suite not found: %s (looked at %s and %s)" % (name_or_path, p, candidate)
    )


def load_suite(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL suite; one object per non-empty non-# line."""
    cases: List[Dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("suite %s line %d: %s" % (path, lineno, exc)) from exc
        if not isinstance(obj, dict):
            raise ValueError("suite %s line %d: expected object" % (path, lineno))
        if "prompt" not in obj:
            raise ValueError("suite %s line %d: missing prompt" % (path, lineno))
        if "id" not in obj:
            obj["id"] = "case-%d" % lineno
        cases.append(obj)
    return cases


# ── scoring ──────────────────────────────────────────────────────────


def score_case(case: Dict[str, Any], response: str) -> Tuple[bool, str]:
    """
    Score a single response.

    Rules (in order):
      1. Empty / whitespace-only → fail
      2. expect_contains (case-insensitive substring) if set
      3. expect_regex if set
      4. else non-empty → pass
    """
    text = response if response is not None else ""
    if not str(text).strip():
        return False, "empty response"

    needle = case.get("expect_contains")
    if needle is not None and str(needle) != "":
        if str(needle).lower() not in str(text).lower():
            return False, "missing expect_contains=%r" % (needle,)

    pattern = case.get("expect_regex")
    if pattern is not None and str(pattern) != "":
        if re.search(str(pattern), str(text), flags=re.IGNORECASE | re.DOTALL) is None:
            return False, "expect_regex %r did not match" % (pattern,)

    return True, "ok"


# ── model selection (K15 / K20) ──────────────────────────────────────


def remote_grok_available() -> bool:
    """True when remote Grok can be attempted (XAI_API_KEY or GROK env set)."""
    if os.environ.get("XAI_API_KEY", "").strip():
        return True
    grok = os.environ.get("GROK", "").strip()
    if grok and grok.lower() not in ("0", "false", "no", "off"):
        return True
    return False


def best_work_model_name() -> str:
    return os.environ.get("GROK_LAB_BEST_MODEL", BEST_WORK_MODEL).strip() or BEST_WORK_MODEL


def default_model_name() -> str:
    return os.environ.get("GROK_LAB_DEFAULT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def resolve_model(
    track: str = "smoke",
    explicit_model: Optional[str] = None,
) -> Tuple[str, str, bool]:
    """
    Return (model, backend, model_fallback).

    Policy:
      --model always wins → backend inferred (grok* → xai if remote avail else ollama)
      track=smoke / offline → dolphin3 + ollama, no fallback flag
      track=best → remote Grok (xai) when auth env present; else dolphin3 + fallback
    """
    track = (track or "smoke").lower().strip()
    if explicit_model:
        model = explicit_model
        # Heuristic: names starting with grok → prefer xai when remote available
        if model.lower().startswith("grok") and remote_grok_available():
            return model, "xai", False
        return model, "ollama", False

    if track in ("best", "best-work", "best_work"):
        if remote_grok_available():
            return best_work_model_name(), "xai", False
        return default_model_name(), "ollama", True

    # smoke / default / anything else → offline dolphin3
    return default_model_name(), "ollama", False


# ── HTTP clients (injectable for tests) ──────────────────────────────


def _http_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECS,
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def ollama_reachable(timeout: float = 2.0) -> bool:
    """Probe Ollama tags endpoint; False if down / unreachable."""
    url = "%s/api/tags" % OLLAMA_HOST
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(64)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return False


def ollama_generate(
    model: str,
    prompt: str,
    max_tokens: int = 128,
    timeout: float = DEFAULT_TIMEOUT_SECS,
    http_json: Optional[Callable[..., Dict[str, Any]]] = None,
) -> str:
    """Call Ollama /api/chat; return assistant text."""
    do_http = http_json or _http_json
    url = "%s/api/chat" % OLLAMA_HOST
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": int(max_tokens)},
    }
    data = do_http(url, payload, timeout=timeout)
    # chat API
    msg = data.get("message") or {}
    if isinstance(msg, dict) and msg.get("content") is not None:
        return str(msg["content"])
    # generate API fallback shape
    if data.get("response") is not None:
        return str(data["response"])
    return ""


def xai_generate(
    model: str,
    prompt: str,
    max_tokens: int = 128,
    timeout: float = DEFAULT_TIMEOUT_SECS,
    http_json: Optional[Callable[..., Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
) -> str:
    """Call xAI OpenAI-compatible chat completions; return assistant text."""
    key = (api_key if api_key is not None else os.environ.get("XAI_API_KEY", "")).strip()
    if not key:
        raise RuntimeError(
            "XAI_API_KEY is not set; cannot call remote Grok "
            "(set XAI_API_KEY or use offline dolphin3)"
        )
    do_http = http_json or _http_json
    url = "%s/chat/completions" % XAI_API_BASE
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(max_tokens),
        "temperature": 0.2,
    }
    headers = {"Authorization": "Bearer %s" % key}
    data = do_http(url, payload, headers=headers, timeout=timeout)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    return str(content) if content is not None else ""


# ── forge integration ────────────────────────────────────────────────


def log_to_forge(
    model: str,
    pass_rate: float,
    n_pass: int,
    n_total: int,
    backend: str,
    model_fallback: bool,
    track: str,
) -> bool:
    """
    If GROK_LAB_RUN_ID is set, log params/metrics via Forge.
    Returns True if logged, False if no run id / forge unavailable.
    Never raises for missing forge (best-effort).
    """
    run_id = os.environ.get("GROK_LAB_RUN_ID", "").strip()
    if not run_id:
        return False
    try:
        # Prefer package import (forge run injects modules/ on PYTHONPATH).
        try:
            from forge import Forge  # type: ignore
        except ImportError:
            modules = str(_REPO / "modules")
            if modules not in sys.path:
                sys.path.insert(0, modules)
            from forge import Forge  # type: ignore

        f = Forge(run_id)
        f.log_param("model", model)
        f.log_param("backend", backend)
        f.log_param("track", track)
        f.log_param("model_fallback", model_fallback)
        f.log_metric("pass_rate", float(pass_rate))
        f.log_metric("n_pass", float(n_pass))
        f.log_metric("n_total", float(n_total))
        return True
    except Exception as exc:  # noqa: BLE001 — never break eval on forge noise
        print("gym: forge log failed: %s" % exc, file=sys.stderr)
        return False


# ── run ──────────────────────────────────────────────────────────────


def _skip_ollama_env() -> bool:
    v = os.environ.get("GROK_LAB_SKIP_OLLAMA", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def run_suite(
    suite: str = "smoke",
    track: str = "smoke",
    model: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECS,
    http_json: Optional[Callable[..., Dict[str, Any]]] = None,
    ollama_probe: Optional[Callable[[], bool]] = None,
    generate_fn: Optional[Callable[..., str]] = None,
) -> EvalResult:
    """
    Load suite, resolve model, run cases, score, optionally log to forge.

    When Ollama is required but down:
      GROK_LAB_SKIP_OLLAMA=1 → skipped=True (caller should exit 0)
      else → error set (caller should exit 1)
    """
    suite_name = suite
    try:
        path = resolve_suite_path(suite)
        cases = load_suite(path)
        suite_name = path.stem
    except (OSError, ValueError) as exc:
        return EvalResult(
            suite=suite,
            model=model or default_model_name(),
            backend="ollama",
            track=track,
            model_fallback=False,
            n_total=0,
            n_pass=0,
            pass_rate=0.0,
            error=str(exc),
        )

    chosen_model, backend, model_fallback = resolve_model(track, explicit_model=model)

    # Probe / skip for ollama backend
    if backend == "ollama":
        probe = ollama_probe if ollama_probe is not None else ollama_reachable
        if not probe():
            reason = "ollama unreachable at %s" % OLLAMA_HOST
            if _skip_ollama_env():
                return EvalResult(
                    suite=suite_name,
                    model=chosen_model,
                    backend="skip",
                    track=track,
                    model_fallback=model_fallback,
                    n_total=0,
                    n_pass=0,
                    pass_rate=0.0,
                    skipped=True,
                    skip_reason=reason,
                )
            return EvalResult(
                suite=suite_name,
                model=chosen_model,
                backend="ollama",
                track=track,
                model_fallback=model_fallback,
                n_total=0,
                n_pass=0,
                pass_rate=0.0,
                error=reason
                + " (set GROK_LAB_SKIP_OLLAMA=1 to skip gracefully in CI)",
            )

    # Remote without API key → fall back to ollama dolphin3
    if backend == "xai" and not os.environ.get("XAI_API_KEY", "").strip():
        # GROK set but no key — cannot call API; fall back offline
        chosen_model = default_model_name()
        backend = "ollama"
        model_fallback = True
        probe = ollama_probe if ollama_probe is not None else ollama_reachable
        if not probe():
            reason = (
                "remote Grok requested but XAI_API_KEY missing and ollama unreachable"
            )
            if _skip_ollama_env():
                return EvalResult(
                    suite=suite_name,
                    model=chosen_model,
                    backend="skip",
                    track=track,
                    model_fallback=True,
                    n_total=0,
                    n_pass=0,
                    pass_rate=0.0,
                    skipped=True,
                    skip_reason=reason,
                )
            return EvalResult(
                suite=suite_name,
                model=chosen_model,
                backend="ollama",
                track=track,
                model_fallback=True,
                n_total=0,
                n_pass=0,
                pass_rate=0.0,
                error=reason,
            )

    # Mutable holders so first-case remote failure can flip model for remaining + log
    state_fallback = [model_fallback]
    state_backend = [backend]
    state_model = [chosen_model]

    def _gen(prompt: str, max_tokens: int) -> str:
        if generate_fn is not None:
            return generate_fn(
                model=state_model[0],
                prompt=prompt,
                max_tokens=max_tokens,
                backend=state_backend[0],
            )
        if state_backend[0] == "xai":
            try:
                return xai_generate(
                    state_model[0],
                    prompt,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    http_json=http_json,
                )
            except Exception as exc:  # remote fail → ollama fallback (K20)
                print(
                    "gym: remote Grok failed (%s); falling back to %s"
                    % (exc, default_model_name()),
                    file=sys.stderr,
                )
                state_fallback[0] = True
                state_backend[0] = "ollama"
                state_model[0] = default_model_name()
                return ollama_generate(
                    state_model[0],
                    prompt,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    http_json=http_json,
                )
        return ollama_generate(
            state_model[0],
            prompt,
            max_tokens=max_tokens,
            timeout=timeout,
            http_json=http_json,
        )

    results: List[CaseResult] = []
    n_pass = 0
    run_error: Optional[str] = None

    for case in cases:
        cid = str(case.get("id", "?"))
        prompt = str(case["prompt"])
        max_tokens = int(case.get("max_tokens") or 128)
        try:
            response = _gen(prompt, max_tokens)
        except Exception as exc:  # noqa: BLE001
            run_error = "generate failed on %s: %s" % (cid, exc)
            results.append(
                CaseResult(
                    id=cid,
                    prompt=prompt,
                    response="",
                    passed=False,
                    reason=str(exc),
                )
            )
            continue
        passed, reason = score_case(case, response)
        if passed:
            n_pass += 1
        results.append(
            CaseResult(
                id=cid,
                prompt=prompt,
                response=response,
                passed=passed,
                reason=reason,
            )
        )

    n_total = len(cases)
    pass_rate = float(n_pass) / float(n_total) if n_total else 0.0
    final_model = state_model[0]
    final_backend = state_backend[0]
    final_fallback = bool(state_fallback[0])

    # Forge dual-write metrics when under lab forge run
    log_to_forge(
        model=final_model,
        pass_rate=pass_rate,
        n_pass=n_pass,
        n_total=n_total,
        backend=final_backend,
        model_fallback=final_fallback,
        track=track,
    )

    return EvalResult(
        suite=suite_name,
        model=final_model,
        backend=final_backend,
        track=track,
        model_fallback=final_fallback,
        n_total=n_total,
        n_pass=n_pass,
        pass_rate=pass_rate,
        cases=results,
        error=run_error,
    )


def format_result(result: EvalResult, verbose: bool = False) -> str:
    lines: List[str] = []
    if result.skipped:
        lines.append("gym: SKIP — %s" % (result.skip_reason or "skipped"))
        lines.append(
            "gym: suite=%s track=%s model=%s (set GROK_LAB_SKIP_OLLAMA=1 → exit 0)"
            % (result.suite, result.track, result.model)
        )
        return "\n".join(lines)

    if result.error and result.n_total == 0:
        lines.append("gym: ERROR — %s" % result.error)
        return "\n".join(lines)

    lines.append(
        "gym: suite=%s track=%s model=%s backend=%s fallback=%s"
        % (
            result.suite,
            result.track,
            result.model,
            result.backend,
            result.model_fallback,
        )
    )
    lines.append(
        "gym: pass_rate=%.4f  n_pass=%d  n_total=%d"
        % (result.pass_rate, result.n_pass, result.n_total)
    )
    if result.error:
        lines.append("gym: note: %s" % result.error)
    for c in result.cases:
        mark = "PASS" if c.passed else "FAIL"
        lines.append("  [%s] %s  (%s)" % (mark, c.id, c.reason))
        if verbose:
            resp = c.response.replace("\n", "\\n")
            if len(resp) > 200:
                resp = resp[:200] + "…"
            lines.append("         response: %s" % resp)
    return "\n".join(lines)


def exit_code_for(result: EvalResult) -> int:
    """
    CI-friendly exit codes:
      skipped (GROK_LAB_SKIP_OLLAMA) → 0
      all pass → 0
      else → 1
    """
    if result.skipped:
        return 0
    if result.ok:
        return 0
    return 1

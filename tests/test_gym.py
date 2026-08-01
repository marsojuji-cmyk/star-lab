#!/usr/bin/env python3
# tests/test_gym.py — Model Gym unit tests (PR4)
"""Mocked Ollama/xAI HTTP; no network required. Python 3.9+."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
GYM_DIR = ROOT / "modules" / "gym"
LIB_DIR = ROOT / "lib"
LAB = ROOT / "bin" / "lab"
SMOKE_SUITE = GYM_DIR / "suites" / "smoke.jsonl"


def _prep_env(lab_data: Path) -> dict:
    env = os.environ.copy()
    env["GROK_LAB_DATA"] = str(lab_data)
    env["GROK_LAB_REPO"] = str(ROOT)
    env["GROK_HOME"] = str(lab_data.parent)
    # Isolate remote auth from host
    env.pop("XAI_API_KEY", None)
    env.pop("GROK", None)
    env.pop("GROK_LAB_SKIP_OLLAMA", None)
    env.pop("GROK_LAB_RUN_ID", None)
    return env


class GymTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="gym-test-")
        self.lab_data = Path(self._tmpdir) / "lab"
        self.lab_data.mkdir(parents=True)
        self.env = _prep_env(self.lab_data)

        for p in (str(LIB_DIR), str(GYM_DIR.parent)):
            if p in sys.path:
                sys.path.remove(p)
            sys.path.insert(0, p)
        if str(GYM_DIR) in sys.path:
            sys.path.remove(str(GYM_DIR))

        os.environ["GROK_LAB_DATA"] = str(self.lab_data)
        os.environ["GROK_LAB_REPO"] = str(ROOT)
        for key in ("XAI_API_KEY", "GROK", "GROK_LAB_SKIP_OLLAMA", "GROK_LAB_RUN_ID"):
            os.environ.pop(key, None)

        for mod in list(sys.modules):
            if (
                mod == "lab_paths"
                or mod == "gym"
                or mod.startswith("gym.")
                or mod == "forge"
                or mod.startswith("forge.")
            ):
                del sys.modules[mod]

        import gym.harness as harness  # noqa: F401

        self.harness = harness

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── suite / scoring ──────────────────────────────────────────

    def test_smoke_suite_exists_and_loads(self) -> None:
        self.assertTrue(SMOKE_SUITE.is_file())
        cases = self.harness.load_suite(SMOKE_SUITE)
        self.assertGreaterEqual(len(cases), 2)
        for c in cases:
            self.assertIn("prompt", c)
            self.assertIn("id", c)

    def test_score_nonempty_pass(self) -> None:
        ok, reason = self.harness.score_case({"id": "a", "prompt": "x"}, "hello")
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_score_empty_fail(self) -> None:
        ok, reason = self.harness.score_case({"id": "a", "prompt": "x"}, "   ")
        self.assertFalse(ok)
        self.assertIn("empty", reason)

    def test_score_expect_contains(self) -> None:
        case = {"id": "s1", "prompt": "p", "expect_contains": "pong"}
        self.assertTrue(self.harness.score_case(case, "…pong…")[0])
        self.assertTrue(self.harness.score_case(case, "PONG")[0])  # case-insensitive
        self.assertFalse(self.harness.score_case(case, "ping")[0])

    def test_score_expect_regex(self) -> None:
        case = {"id": "s2", "prompt": "p", "expect_regex": r"\b4\b"}
        self.assertTrue(self.harness.score_case(case, "answer is 4")[0])
        self.assertFalse(self.harness.score_case(case, "forty")[0])

    # ── model policy K15 / K20 ───────────────────────────────────

    def test_resolve_smoke_is_dolphin3_ollama(self) -> None:
        model, backend, fb = self.harness.resolve_model("smoke")
        self.assertEqual(model, "dolphin3:latest")
        self.assertEqual(backend, "ollama")
        self.assertFalse(fb)

    def test_resolve_best_falls_back_without_auth(self) -> None:
        model, backend, fb = self.harness.resolve_model("best")
        self.assertEqual(model, "dolphin3:latest")
        self.assertEqual(backend, "ollama")
        self.assertTrue(fb)

    def test_resolve_best_prefers_remote_with_xai_key(self) -> None:
        os.environ["XAI_API_KEY"] = "test-key-not-real"
        model, backend, fb = self.harness.resolve_model("best")
        self.assertEqual(backend, "xai")
        self.assertTrue(model.startswith("grok") or "grok" in model.lower())
        self.assertFalse(fb)

    def test_resolve_best_prefers_remote_with_grok_env(self) -> None:
        os.environ["GROK"] = "1"
        model, backend, fb = self.harness.resolve_model("best")
        self.assertEqual(backend, "xai")
        self.assertFalse(fb)

    def test_explicit_model_wins(self) -> None:
        model, backend, fb = self.harness.resolve_model(
            "best", explicit_model="llama3:8b"
        )
        self.assertEqual(model, "llama3:8b")
        self.assertEqual(backend, "ollama")
        self.assertFalse(fb)

    # ── run_suite with mocks ─────────────────────────────────────

    def _mock_ollama_chat(self, responses: Dict[str, str]):
        """Return http_json that serves Ollama chat replies by prompt substring."""

        def http_json(
            url: str,
            payload: Dict[str, Any],
            headers: Optional[Dict[str, str]] = None,
            timeout: float = 30,
        ) -> Dict[str, Any]:
            messages = payload.get("messages") or []
            content = messages[0]["content"] if messages else ""
            reply = "ok"
            for needle, text in responses.items():
                if needle.lower() in content.lower():
                    reply = text
                    break
            else:
                # default: echo something non-empty for free-form prompts
                reply = responses.get("*", "hello from mock model")
            return {"message": {"role": "assistant", "content": reply}}

        return http_json

    def test_run_smoke_all_pass_mocked(self) -> None:
        http = self._mock_ollama_chat(
            {
                "pong": "pong",
                "2+2": "4",
                "*": "Hello there.",
            }
        )
        result = self.harness.run_suite(
            suite="smoke",
            track="smoke",
            http_json=http,
            ollama_probe=lambda: True,
        )
        self.assertFalse(result.skipped)
        self.assertIsNone(result.error)
        self.assertEqual(result.model, "dolphin3:latest")
        self.assertEqual(result.backend, "ollama")
        self.assertEqual(result.n_pass, result.n_total)
        self.assertEqual(result.pass_rate, 1.0)
        self.assertTrue(result.ok)
        self.assertEqual(self.harness.exit_code_for(result), 0)

    def test_run_smoke_keyword_fail(self) -> None:
        http = self._mock_ollama_chat(
            {
                "pong": "ping",  # wrong
                "2+2": "4",
                "*": "Hello",
            }
        )
        result = self.harness.run_suite(
            suite="smoke",
            track="smoke",
            http_json=http,
            ollama_probe=lambda: True,
        )
        self.assertLess(result.n_pass, result.n_total)
        self.assertFalse(result.ok)
        self.assertEqual(self.harness.exit_code_for(result), 1)
        failed = [c for c in result.cases if not c.passed]
        self.assertTrue(any(c.id == "s1" for c in failed))

    def test_ollama_down_exit_1_without_skip(self) -> None:
        result = self.harness.run_suite(
            suite="smoke",
            track="smoke",
            ollama_probe=lambda: False,
        )
        self.assertFalse(result.skipped)
        self.assertIsNotNone(result.error)
        self.assertIn("ollama", result.error.lower())
        self.assertEqual(self.harness.exit_code_for(result), 1)

    def test_ollama_down_skip_with_env(self) -> None:
        os.environ["GROK_LAB_SKIP_OLLAMA"] = "1"
        result = self.harness.run_suite(
            suite="smoke",
            track="smoke",
            ollama_probe=lambda: False,
        )
        self.assertTrue(result.skipped)
        self.assertEqual(result.backend, "skip")
        self.assertEqual(self.harness.exit_code_for(result), 0)
        out = self.harness.format_result(result)
        self.assertIn("SKIP", out)

    def test_track_best_without_auth_uses_dolphin3(self) -> None:
        http = self._mock_ollama_chat({"*": "pong", "pong": "pong", "2+2": "4"})
        # Fix responses for all smoke cases
        http = self._mock_ollama_chat(
            {"pong": "pong", "2+2": "4", "*": "Hello world"}
        )
        result = self.harness.run_suite(
            suite="smoke",
            track="best",
            http_json=http,
            ollama_probe=lambda: True,
        )
        self.assertEqual(result.model, "dolphin3:latest")
        self.assertEqual(result.backend, "ollama")
        self.assertTrue(result.model_fallback)
        self.assertTrue(result.ok)

    def test_track_best_with_xai_uses_remote(self) -> None:
        os.environ["XAI_API_KEY"] = "sk-test"

        calls: List[str] = []

        def http_json(
            url: str,
            payload: Dict[str, Any],
            headers: Optional[Dict[str, str]] = None,
            timeout: float = 30,
        ) -> Dict[str, Any]:
            calls.append(url)
            self.assertIn("Authorization", headers or {})
            messages = payload.get("messages") or []
            content = messages[0]["content"] if messages else ""
            if "pong" in content.lower():
                text = "pong"
            elif "2+2" in content:
                text = "4"
            else:
                text = "Hello from Grok"
            return {
                "choices": [{"message": {"role": "assistant", "content": text}}]
            }

        result = self.harness.run_suite(
            suite="smoke",
            track="best",
            http_json=http_json,
            ollama_probe=lambda: False,  # ollama down OK when remote works
        )
        self.assertEqual(result.backend, "xai")
        self.assertFalse(result.model_fallback)
        self.assertTrue(result.ok)
        self.assertTrue(any("chat/completions" in u for u in calls))

    def test_track_best_grok_env_without_key_falls_back(self) -> None:
        os.environ["GROK"] = "1"  # signal remote preferred, but no API key
        http = self._mock_ollama_chat(
            {"pong": "pong", "2+2": "4", "*": "Hello"}
        )
        result = self.harness.run_suite(
            suite="smoke",
            track="best",
            http_json=http,
            ollama_probe=lambda: True,
        )
        self.assertEqual(result.backend, "ollama")
        self.assertEqual(result.model, "dolphin3:latest")
        self.assertTrue(result.model_fallback)
        self.assertTrue(result.ok)

    def test_remote_fail_falls_back_to_ollama(self) -> None:
        os.environ["XAI_API_KEY"] = "sk-test"

        def http_json(
            url: str,
            payload: Dict[str, Any],
            headers: Optional[Dict[str, str]] = None,
            timeout: float = 30,
        ) -> Dict[str, Any]:
            if "api.x.ai" in url or "chat/completions" in url:
                raise OSError("simulated remote outage")
            # ollama path
            messages = payload.get("messages") or []
            content = messages[0]["content"] if messages else ""
            if "pong" in content.lower():
                text = "pong"
            elif "2+2" in content:
                text = "4"
            else:
                text = "Hello"
            return {"message": {"role": "assistant", "content": text}}

        result = self.harness.run_suite(
            suite="smoke",
            track="best",
            http_json=http_json,
            ollama_probe=lambda: True,
        )
        self.assertEqual(result.backend, "ollama")
        self.assertTrue(result.model_fallback)
        self.assertEqual(result.model, "dolphin3:latest")
        self.assertTrue(result.ok)

    # ── forge integration ────────────────────────────────────────

    def test_forge_logging_when_run_id_set(self) -> None:
        # Bring up forge store + create a run shell
        for p in (str(LIB_DIR), str(GYM_DIR.parent)):
            if p not in sys.path:
                sys.path.insert(0, p)
        import forge.forge as forge_mod

        store = forge_mod.ForgeStore()
        exp = store.get_or_create_experiment("gym-unit", project="test")
        run = store.create_run(exp["id"], ["lab", "gym", "smoke"], tags=["gym"])
        os.environ["GROK_LAB_RUN_ID"] = run["id"]

        http = self._mock_ollama_chat(
            {"pong": "pong", "2+2": "4", "*": "Hello"}
        )
        result = self.harness.run_suite(
            suite="smoke",
            track="smoke",
            http_json=http,
            ollama_probe=lambda: True,
        )
        self.assertTrue(result.ok)

        # Finish run so dual-write merges params/metrics
        store.finish_run(run["id"], "completed", 0, 1)
        row = store.get_run(run["id"])
        assert row is not None
        params = json.loads(row["params"])
        metrics = json.loads(row["metrics"])
        self.assertEqual(params.get("model"), "dolphin3:latest")
        self.assertEqual(metrics.get("pass_rate"), 1.0)
        self.assertEqual(metrics.get("n_pass"), float(result.n_pass))
        self.assertEqual(metrics.get("n_total"), float(result.n_total))

    def test_no_forge_without_run_id(self) -> None:
        os.environ.pop("GROK_LAB_RUN_ID", None)
        logged = self.harness.log_to_forge(
            model="dolphin3:latest",
            pass_rate=1.0,
            n_pass=3,
            n_total=3,
            backend="ollama",
            model_fallback=False,
            track="smoke",
        )
        self.assertFalse(logged)

    # ── CLI facade ───────────────────────────────────────────────

    def test_cli_help_via_lab(self) -> None:
        proc = subprocess.run(
            [str(LAB), "gym", "help"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("smoke", proc.stdout)
        self.assertIn("dolphin3", proc.stdout)
        self.assertIn("track best", proc.stdout.lower() or "best")

    def test_cli_list_suites(self) -> None:
        proc = subprocess.run(
            [str(LAB), "gym", "list"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("smoke", proc.stdout)

    def test_cli_smoke_skip_when_ollama_down(self) -> None:
        env = dict(self.env)
        env["GROK_LAB_SKIP_OLLAMA"] = "1"
        # Force unreachable host so probe fails without needing mock injection
        env["OLLAMA_HOST"] = "http://127.0.0.1:9"
        proc = subprocess.run(
            [str(LAB), "gym", "smoke"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("SKIP", combined)

    def test_cli_smoke_fail_when_ollama_down_no_skip(self) -> None:
        env = dict(self.env)
        env.pop("GROK_LAB_SKIP_OLLAMA", None)
        env["OLLAMA_HOST"] = "http://127.0.0.1:9"
        proc = subprocess.run(
            [str(LAB), "gym", "smoke"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 1, msg=proc.stdout + proc.stderr)

    def test_lab_help_lists_gym(self) -> None:
        proc = subprocess.run(
            [str(LAB), "help"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("gym", proc.stdout)

    def test_ollama_generate_parses_chat_shape(self) -> None:
        def http_json(url, payload, headers=None, timeout=30):
            return {"message": {"role": "assistant", "content": "pong"}}

        text = self.harness.ollama_generate(
            "dolphin3:latest", "ping", http_json=http_json
        )
        self.assertEqual(text, "pong")

    def test_xai_generate_parses_choices(self) -> None:
        def http_json(url, payload, headers=None, timeout=30):
            self.assertTrue(headers and "Bearer" in headers.get("Authorization", ""))
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": "pong"}}
                ]
            }

        text = self.harness.xai_generate(
            "grok-4", "ping", http_json=http_json, api_key="k"
        )
        self.assertEqual(text, "pong")

    def test_xai_generate_requires_key(self) -> None:
        with self.assertRaises(RuntimeError):
            self.harness.xai_generate("grok-4", "ping", api_key="")


if __name__ == "__main__":
    unittest.main()

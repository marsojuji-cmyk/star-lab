#!/usr/bin/env python3
# Python 3.9+ — Imagine Atelier offline verify tests (temp GROK_LAB_DATA only)
"""
Hermetic coverage for lab imagine verify:
  - assets/hero.jpg proof path (ok + dimensions + mime)
  - empty file fail
  - credential basename refuse
  - non-image body with image extension fails MIME (content magic only)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib"
IMAGINE = ROOT / "modules" / "imagine"
HERO = ROOT / "assets" / "hero.jpg"
LAB_BIN = ROOT / "bin" / "lab"

sys.path.insert(0, str(LIB))
sys.path.insert(0, str(IMAGINE))


class ImagineVerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="lab-imagine-test."))
        self.lab = self.tmpdir / "lab"
        self.lab.mkdir(parents=True)
        self._env_backup = {
            k: os.environ.get(k)
            for k in ("GROK_HOME", "GROK_LAB_DATA", "GROK_LAB_REPO", "PROJECTS")
        }
        os.environ["GROK_LAB_DATA"] = str(self.lab)
        os.environ["GROK_LAB_REPO"] = str(ROOT)
        os.environ.setdefault("GROK_HOME", str(self.tmpdir / "grok"))

        # Reload modules against isolated env
        for mod in list(sys.modules):
            if mod in ("lab_paths", "cli") or mod.startswith("modules.imagine"):
                del sys.modules[mod]

        import cli as imagine_cli  # noqa: E402

        self.cli = imagine_cli

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_hero_jpg_ok(self) -> None:
        """PR10 proof: assets/hero.jpg verifies with content MIME + dimensions."""
        self.assertTrue(HERO.is_file(), f"missing fixture {HERO}")
        result = self.cli.verify_image(HERO.resolve())
        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual(result["mime"], "image/jpeg")
        self.assertEqual(result["width"], 1280)
        self.assertEqual(result["height"], 720)
        self.assertGreater(result["size_bytes"], 0)
        self.assertEqual(result["size_bytes"], HERO.stat().st_size)
        self.assertEqual(result["checks"].get("mime"), "ok")
        self.assertEqual(result["checks"].get("dimensions"), "ok")
        self.assertEqual(result["checks"].get("filesize"), "ok")

    def test_hero_via_cli_writes_run(self) -> None:
        code = self.cli.main(["verify", str(HERO)])
        self.assertEqual(code, 0)
        runs = list((self.lab / "imagine" / "runs").glob("*.json"))
        self.assertGreaterEqual(len(runs), 1)
        payload = json.loads(runs[-1].read_text(encoding="utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["width"], 1280)
        self.assertEqual(payload["height"], 720)
        self.assertEqual(payload["mime"], "image/jpeg")
        self.assertEqual(payload["command"], "verify")

    def test_empty_file_fails(self) -> None:
        empty = self.tmpdir / "empty.jpg"
        empty.write_bytes(b"")
        result = self.cli.verify_image(empty)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"].get("non_empty"), "fail")
        self.assertTrue(any("empty" in e.lower() for e in result["errors"]))

    def test_credential_env_refused(self) -> None:
        env_path = self.tmpdir / ".env"
        env_path.write_bytes(b"SECRET=1\n")
        result = self.cli.verify_image(env_path)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"].get("credentials"), "fail")
        self.assertTrue(any("refused" in e.lower() for e in result["errors"]))

    def test_credential_pem_refused(self) -> None:
        pem = self.tmpdir / "cert.pem"
        pem.write_bytes(b"-----BEGIN CERTIFICATE-----\n")
        result = self.cli.verify_image(pem)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"].get("credentials"), "fail")

    def test_extension_only_image_fails_mime(self) -> None:
        """Issue 1: non-image body with .png extension must not pass MIME."""
        evil = self.tmpdir / "evil.png"
        # PE/MZ-ish header — not an image by content
        evil.write_bytes(b"MZ\x90\x00not-an-image-payload")
        result = self.cli.verify_image(evil)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"].get("mime"), "fail")
        self.assertIsNone(result.get("mime"))
        self.assertEqual(result.get("mime_guess"), "image/png")
        self.assertTrue(
            any("content" in e.lower() or "magic" in e.lower() for e in result["errors"])
        )

    def test_missing_path_fails(self) -> None:
        missing = self.tmpdir / "nope.jpg"
        result = self.cli.verify_image(missing)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"].get("exists"), "fail")

    def test_lab_bin_dispatch(self) -> None:
        """bin/lab imagine verify reaches the module (integration smoke)."""
        if not LAB_BIN.is_file():
            self.skipTest("bin/lab missing")
        env = os.environ.copy()
        env["GROK_LAB_DATA"] = str(self.lab)
        env["GROK_LAB_REPO"] = str(ROOT)
        proc = subprocess.run(
            [str(LAB_BIN), "imagine", "verify", str(HERO)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("imagine verify: ok", proc.stdout)
        self.assertIn("1280x720", proc.stdout)


if __name__ == "__main__":
    unittest.main()

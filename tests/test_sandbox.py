#!/usr/bin/env python3
# Python 3.9+ — Sandbox Range unit tests (PR11)
"""Missing-key-only merge + CLI smoke with temp GROK_HOME."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT / "modules" / "sandbox"
sys.path.insert(0, str(SANDBOX))
sys.path.insert(0, str(ROOT / "lib"))

from merge import (  # noqa: E402
    LAB_PROFILE_NAMES,
    install_profiles,
    merge_sandbox_toml,
    parse_fragment_profiles,
    parse_toml_doc,
)


FRAGMENT = (SANDBOX / "profiles.fragment.toml").read_text(encoding="utf-8")


class TestFragment(unittest.TestCase):
    def test_fragment_has_lab_workspace_extends_workspace(self):
        profiles = parse_fragment_profiles(FRAGMENT)
        self.assertIn("lab-workspace", profiles)
        self.assertEqual(profiles["lab-workspace"].get("extends"), "workspace")
        self.assertIn("lab-readonly-review", profiles)
        self.assertIn("lab-untrusted", profiles)
        self.assertEqual(profiles["lab-untrusted"].get("extends"), "strict")
        self.assertEqual(profiles["lab-readonly-review"].get("extends"), "read-only")
        for name in LAB_PROFILE_NAMES:
            self.assertIn(name, profiles)


class TestMerge(unittest.TestCase):
    def test_merge_into_empty_adds_all_profiles(self):
        text, result = merge_sandbox_toml(FRAGMENT, "")
        self.assertFalse(result.unchanged)
        self.assertEqual(set(result.added_profiles), set(LAB_PROFILE_NAMES))
        doc = parse_toml_doc(text)
        for name in LAB_PROFILE_NAMES:
            sec = doc.profile_section(name)
            self.assertIsNotNone(sec, name)
            self.assertIn("extends", sec.keys)

    def test_idempotent_second_merge(self):
        text1, r1 = merge_sandbox_toml(FRAGMENT, "")
        text2, r2 = merge_sandbox_toml(FRAGMENT, text1)
        self.assertTrue(r2.unchanged)
        self.assertEqual(r2.added_profiles, [])
        self.assertEqual(r2.added_keys, [])
        self.assertEqual(r2.conflicts, [])
        # skipped_same should mention keys
        self.assertTrue(any(s.startswith("lab-workspace.") for s in r2.skipped_same))
        self.assertEqual(text1.strip(), text2.strip())

    def test_preserves_user_preamble_and_custom_profile(self):
        existing = (
            "# my sandbox\n"
            "\n"
            "[profiles.custom]\n"
            'extends = "workspace"\n'
            'read_write = ["/tmp/scratch"]\n'
            "\n"
        )
        text, result = merge_sandbox_toml(FRAGMENT, existing)
        self.assertIn("# my sandbox", text)
        self.assertIn("[profiles.custom]", text)
        self.assertIn('read_write = ["/tmp/scratch"]', text)
        self.assertIn("[profiles.lab-workspace]", text)
        self.assertIn("lab-workspace", result.added_profiles)

    def test_missing_key_only_no_overwrite(self):
        existing = (
            "[profiles.lab-workspace]\n"
            'extends = "strict"\n'  # user customized — conflict with fragment
            'deny = ["**/.env"]\n'
            "\n"
        )
        text, result = merge_sandbox_toml(FRAGMENT, existing)
        # extends conflicts; deny may conflict or match subset — fragment deny is longer list
        self.assertTrue(any(c.startswith("lab-workspace.extends") for c in result.conflicts))
        # User value preserved
        doc = parse_toml_doc(text)
        sec = doc.profile_section("lab-workspace")
        self.assertEqual(sec.keys["extends"], "strict")
        # Other lab profiles still added
        self.assertIn("lab-untrusted", result.added_profiles)

    def test_adds_only_missing_key_inside_profile(self):
        existing = (
            "[profiles.lab-workspace]\n"
            'extends = "workspace"\n'
            "# keep this comment\n"
            "\n"
        )
        text, result = merge_sandbox_toml(FRAGMENT, existing)
        self.assertIn("lab-workspace.deny", result.added_keys)
        self.assertNotIn("lab-workspace", result.added_profiles)
        self.assertIn("# keep this comment", text)
        self.assertIn("deny = ", text)
        # extends skipped as same
        self.assertIn("lab-workspace.extends", result.skipped_same)


class TestInstallProfiles(unittest.TestCase):
    def test_install_writes_and_chmod(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sandbox.toml"
            frag = SANDBOX / "profiles.fragment.toml"
            r = install_profiles(frag, target)
            self.assertTrue(target.is_file())
            self.assertTrue(r.created_file)
            self.assertTrue(set(LAB_PROFILE_NAMES).issubset(set(r.added_profiles)))
            # second install no-op write content-wise
            body1 = target.read_text(encoding="utf-8")
            r2 = install_profiles(frag, target)
            body2 = target.read_text(encoding="utf-8")
            self.assertEqual(body1, body2)
            self.assertEqual(r2.added_profiles, [])
            self.assertFalse(r2.created_file)


class TestCLI(unittest.TestCase):
    def _env(self, grok_home: Path) -> dict:
        env = os.environ.copy()
        env["GROK_HOME"] = str(grok_home)
        env["GROK_LAB_REPO"] = str(ROOT)
        # Ensure we don't pick up a different python path issue
        env["PYTHONPATH"] = str(ROOT / "lib")
        return env

    def _run(self, args, grok_home: Path, check: bool = False):
        cmd = [sys.executable, str(SANDBOX / "cli.py")] + list(args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=self._env(grok_home),
            check=check,
        )

    def test_cli_install_list_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            gh = Path(tmp) / "grok"
            gh.mkdir()
            r = self._run(["install"], gh)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue((gh / "sandbox.toml").is_file())
            self.assertIn("lab-workspace", r.stdout)

            r2 = self._run(["list"], gh)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("installed", r2.stdout)
            self.assertIn("lab-workspace", r2.stdout)

            r3 = self._run(["use", "lab-workspace"], gh)
            self.assertEqual(r3.returncode, 0, r3.stderr)
            self.assertIn("grok --sandbox lab-workspace", r3.stdout)

            # idempotent
            r4 = self._run(["install"], gh)
            self.assertEqual(r4.returncode, 0)
            self.assertIn("already present", r4.stdout)

    def test_cli_test_skip_without_grok(self):
        with tempfile.TemporaryDirectory() as tmp:
            gh = Path(tmp) / "grok"
            gh.mkdir()
            env = self._env(gh)
            # Remove grok from PATH
            env["PATH"] = "/usr/bin:/bin"
            cmd = [sys.executable, str(SANDBOX / "cli.py"), "test"]
            r = subprocess.run(cmd, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertIn("SKIP", r.stdout)

    def test_lab_facade_dispatch(self):
        lab = ROOT / "bin" / "lab"
        with tempfile.TemporaryDirectory() as tmp:
            gh = Path(tmp) / "grok"
            gh.mkdir()
            env = os.environ.copy()
            env["GROK_HOME"] = str(gh)
            env["GROK_LAB_REPO"] = str(ROOT)
            r = subprocess.run(
                ["bash", str(lab), "sandbox", "install"],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue((gh / "sandbox.toml").is_file())
            body = (gh / "sandbox.toml").read_text(encoding="utf-8")
            self.assertIn("[profiles.lab-workspace]", body)
            self.assertIn('extends = "workspace"', body)


if __name__ == "__main__":
    unittest.main()

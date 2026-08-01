#!/usr/bin/env python3
# Python 3.9+ — Integration Dock unit tests (PR12)
"""MCP optional; offline fallbacks always; never doctor-fail."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
DOCK = ROOT / "modules" / "dock"
sys.path.insert(0, str(DOCK))
sys.path.insert(0, str(ROOT / "lib"))

from cli import (  # noqa: E402
    build_report,
    check_fallback_cli,
    check_fallback_local_docs,
    check_fallback_skip,
    match_mcp,
    parse_mcp_server_names_from_toml,
    report_to_dict,
    _normalize_mcp_list_json,
    main,
)


class TestParseConfig(unittest.TestCase):
    def test_parse_mcp_section_headers(self):
        text = """
[cli]
auto_update = true

[mcp_servers.github]
command = "npx"
enabled = true

[mcp_servers.notion]
url = "https://example.com"
# comment

[permission]
deny = []
"""
        names = parse_mcp_server_names_from_toml(text)
        self.assertEqual(names, ["github", "notion"])

    def test_parse_empty(self):
        self.assertEqual(parse_mcp_server_names_from_toml(""), [])
        self.assertEqual(parse_mcp_server_names_from_toml("[cli]\nx=1\n"), [])


class TestMatchMcp(unittest.TestCase):
    def test_exact_and_managed_aliases(self):
        present, hits = match_mcp(
            ("github", "grok_com_github"),
            ["grok_com_github", "other"],
        )
        self.assertTrue(present)
        self.assertIn("grok_com_github", hits)

    def test_absent(self):
        present, hits = match_mcp(("github",), ["notion", "calendar"])
        self.assertFalse(present)
        self.assertEqual(hits, [])


class TestNormalizeListJson(unittest.TestCase):
    def test_list_of_strings(self):
        self.assertEqual(_normalize_mcp_list_json(["a", "b"]), ["a", "b"])

    def test_list_of_objects(self):
        self.assertEqual(
            _normalize_mcp_list_json([{"name": "github"}, {"id": "notion"}]),
            ["github", "notion"],
        )

    def test_servers_key(self):
        self.assertEqual(
            _normalize_mcp_list_json({"servers": [{"name": "x"}]}),
            ["x"],
        )


class TestFallbacks(unittest.TestCase):
    def test_skip_always_ok(self):
        r = check_fallback_skip("optional")
        self.assertTrue(r.ok)
        self.assertEqual(r.kind, "skip")

    def test_cli_which(self):
        # python3 is always present for these tests
        r = check_fallback_cli("python3")
        self.assertTrue(r.ok)
        self.assertTrue(r.path)

        r2 = check_fallback_cli("definitely-not-a-real-bin-zzzx")
        self.assertFalse(r2.ok)

    def test_local_docs(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".grok"
            repo = Path(td) / "repo"
            home.mkdir()
            repo.mkdir()
            mem = home / "memory"
            mem.mkdir()
            (mem / "MEMORY.md").write_text("# mem\n", encoding="utf-8")
            r = check_fallback_local_docs(repo, home)
            self.assertTrue(r.ok)


class TestBuildReport(unittest.TestCase):
    def test_offline_ok_without_mcp(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".grok"
            repo = Path(td) / "repo"
            home.mkdir()
            (home / "config.toml").write_text("[cli]\nx=1\n", encoding="utf-8")
            mem = home / "memory"
            mem.mkdir()
            (mem / "MEMORY.md").write_text("x\n", encoding="utf-8")
            repo.mkdir()
            (repo / "docs").mkdir()
            (repo / "docs" / "GROK-STAR-LAB-DESIGN.md").write_text("d\n", encoding="utf-8")

            # Ensure gh-like fallback: put a fake gh on PATH
            bindir = Path(td) / "bin"
            bindir.mkdir()
            gh = bindir / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            gh.chmod(0o755)
            env_path = str(bindir) + os.pathsep + os.environ.get("PATH", "")

            with mock.patch.dict(os.environ, {"PATH": env_path}):
                report = build_report(
                    "status", do_probe=False, home=home, repo=repo
                )

            self.assertTrue(report.offline_ok)
            self.assertIn(report.module_status, ("ok", "off"))
            # never fail
            self.assertNotEqual(report.module_status, "fail")
            by_id = {i.id: i for i in report.integrations}
            self.assertIn("github", by_id)
            self.assertFalse(by_id["github"].mcp_present)
            self.assertTrue(by_id["github"].fallback.ok)
            self.assertEqual(by_id["github"].status, "ok")
            self.assertTrue(by_id["calendar"].fallback.ok)
            self.assertEqual(by_id["calendar"].fallback.kind, "skip")

    def test_mcp_present_from_config(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".grok"
            repo = Path(td) / "repo"
            home.mkdir()
            repo.mkdir()
            (home / "config.toml").write_text(
                "[mcp_servers.github]\ncommand = \"npx\"\n",
                encoding="utf-8",
            )
            mem = home / "memory"
            mem.mkdir()
            (mem / "MEMORY.md").write_text("x\n", encoding="utf-8")
            bindir = Path(td) / "bin"
            bindir.mkdir()
            gh = bindir / "gh"
            gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            gh.chmod(0o755)
            with mock.patch.dict(
                os.environ,
                {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")},
            ):
                report = build_report(
                    "status", do_probe=False, home=home, repo=repo
                )
            by_id = {i.id: i for i in report.integrations}
            self.assertTrue(by_id["github"].mcp_present)
            self.assertEqual(by_id["github"].status, "ok")


class TestCLI(unittest.TestCase):
    def test_help_exit_0(self):
        rc = main(["help"])
        self.assertEqual(rc, 0)

    def test_status_json_exit_0(self):
        # Live status against real host — must exit 0 (never doctor-fail)
        rc = main(["status", "--json"])
        self.assertEqual(rc, 0)

    def test_bin_lab_dock_status(self):
        lab = ROOT / "bin" / "lab"
        env = os.environ.copy()
        env["PATH"] = (
            str(Path.home() / "homebrew" / "bin")
            + os.pathsep
            + env.get("PATH", "")
        )
        env["GROK_LAB_REPO"] = str(ROOT)
        proc = subprocess.run(
            [str(lab), "dock", "status", "--json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["schema_version"], 1)
        self.assertIn("integrations", data)
        self.assertTrue(data.get("offline_ok") is True or data.get("offline_ok") is False)
        # policy: module_status never fail
        self.assertNotEqual(data["module_status"], "fail")
        ids = {i["id"] for i in data["integrations"]}
        self.assertEqual(ids, {"github", "docs", "calendar"})

    def test_bin_lab_dock_probe_exit_0(self):
        lab = ROOT / "bin" / "lab"
        env = os.environ.copy()
        env["PATH"] = (
            str(Path.home() / ".grok" / "bin")
            + os.pathsep
            + str(Path.home() / "homebrew" / "bin")
            + os.pathsep
            + env.get("PATH", "")
        )
        env["GROK_LAB_REPO"] = str(ROOT)
        proc = subprocess.run(
            [str(lab), "dock", "probe"],
            capture_output=True,
            text=True,
            env=env,
            timeout=45,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("Integration Dock", proc.stdout)
        self.assertIn("never fails core doctor", proc.stdout)


class TestReportDict(unittest.TestCase):
    def test_roundtrip_keys(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".grok"
            repo = Path(td) / "repo"
            home.mkdir()
            repo.mkdir()
            (home / "memory").mkdir()
            (home / "memory" / "MEMORY.md").write_text("m\n", encoding="utf-8")
            report = build_report("status", do_probe=False, home=home, repo=repo)
            d = report_to_dict(report)
            self.assertEqual(d["schema_version"], 1)
            self.assertEqual(len(d["integrations"]), 3)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# tests/test_showroom.py — publish, secrets gate, index regen (PR9)
"""Offline unit tests for showroom capture → publish → regen."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "modules" / "showroom"))


class ShowroomSecretsTest(unittest.TestCase):
    def test_private_key_refused(self) -> None:
        from secrets_gate import scan_payload

        hits = scan_payload(
            body="pem:\n-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n"
        )
        self.assertTrue(hits)
        self.assertTrue(any("private_key" in h for h in hits))

    def test_clean_payload(self) -> None:
        from secrets_gate import scan_payload

        hits = scan_payload(
            title="Demo",
            summary="offline doctor proof",
            body="# Demo\n\nlab doctor\n",
            paths=["docs/PROOF.txt"],
            proof_commands=["lab doctor"],
        )
        self.assertEqual(hits, [])

    def test_env_path_refused(self) -> None:
        from secrets_gate import path_looks_secret

        self.assertIsNotNone(path_looks_secret("/tmp/project/.env"))
        self.assertIsNotNone(path_looks_secret("id_rsa"))
        self.assertIsNone(path_looks_secret("docs/PROOF.txt"))


class ShowroomPublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="showroom-test-"))
        self.lab = self.tmp / "lab"
        self.repo = self.tmp / "repo"
        (self.repo / "showroom" / "entries").mkdir(parents=True)
        (self.lab / "showroom" / "inbox").mkdir(parents=True)
        self._old_lab = os.environ.get("GROK_LAB_DATA")
        self._old_repo = os.environ.get("GROK_LAB_REPO")
        os.environ["GROK_LAB_DATA"] = str(self.lab)
        os.environ["GROK_LAB_REPO"] = str(self.repo)
        # Reload path-sensitive modules
        for name in list(sys.modules):
            if name in (
                "lab_paths",
                "capture",
                "publish",
                "regen_index",
                "secrets_gate",
            ):
                del sys.modules[name]

    def tearDown(self) -> None:
        if self._old_lab is None:
            os.environ.pop("GROK_LAB_DATA", None)
        else:
            os.environ["GROK_LAB_DATA"] = self._old_lab
        if self._old_repo is None:
            os.environ.pop("GROK_LAB_REPO", None)
        else:
            os.environ["GROK_LAB_REPO"] = self._old_repo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_capture_publish_regen(self) -> None:
        from capture import capture
        from publish import publish_inbox_item
        from regen_index import load_entries

        out = capture(
            title="Unit Publish Demo",
            kind="demo",
            project="test",
            source="manual",
            summary="round-trip smoke",
            paths=[],
            proof_commands=["echo ok"],
        )
        self.assertTrue(out.is_file())
        result = publish_inbox_item(out.stem, root=self.repo)
        eid = result["entry_id"]
        entry = self.repo / "showroom" / "entries" / eid
        self.assertTrue((entry / "meta.json").is_file())
        self.assertTrue((entry / "body.md").is_file())
        self.assertTrue(result["index_path"].is_file())
        entries = load_entries(self.repo)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Unit Publish Demo")
        # inbox moved to done
        done = list((self.lab / "showroom" / "inbox" / "done").glob("*.json"))
        self.assertEqual(len(done), 1)

    def test_secrets_block_publish(self) -> None:
        from capture import capture
        from publish import publish_inbox_item

        out = capture(
            title="Leaked Key",
            kind="manual",
            summary="bad",
            paths=[],
            proof_commands=[],
        )
        # inject private key into inbox body fields
        data = json.loads(out.read_text(encoding="utf-8"))
        data["summary"] = "-----BEGIN OPENSSH PRIVATE KEY-----\nxxx"
        out.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            publish_inbox_item(out.stem, root=self.repo)
        self.assertIn("secrets gate", str(ctx.exception).lower())


class ShowroomIndexTest(unittest.TestCase):
    def test_seed_entries_present(self) -> None:
        entries_root = ROOT / "showroom" / "entries"
        metas = list(entries_root.glob("*/meta.json"))
        self.assertGreaterEqual(len(metas), 2)
        index = ROOT / "showroom" / "index.html"
        self.assertTrue(index.is_file())
        text = index.read_text(encoding="utf-8")
        self.assertIn("Showroom", text)
        self.assertIn("claude-compare", text.lower())


if __name__ == "__main__":
    unittest.main()

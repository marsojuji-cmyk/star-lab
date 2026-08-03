#!/usr/bin/env python3
"""Body registry PR-B1–B2 hermetic tests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))
sys.path.insert(0, str(ROOT / "lib"))


class TestBody(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GROK_LAB_DATA"] = self.tmp.name
        # reload modules that cache paths
        for mod in list(sys.modules):
            if mod.startswith("body"):
                del sys.modules[mod]
        from body.store import BodyStore
        from body.resolve import resolve_body
        from body.events import ingest, list_events
        from body.ledger import list_obligations

        self.BodyStore = BodyStore
        self.resolve_body = resolve_body
        self.ingest = ingest
        self.list_events = list_events
        self.list_obligations = list_obligations

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("GROK_LAB_DATA", None)

    def test_init_list_resolve(self):
        store = self.BodyStore()
        b = store.init_body(
            kind="project",
            name="claude-compare-demo",
            repo=str(Path.home() / "Projects" / "claude-compare-demo"),
        )
        self.assertEqual(b.body_id, "project:claude-compare-demo")
        self.assertTrue(store.exists(b.body_id))
        rows = store.list()
        self.assertEqual(len(rows), 1)
        resolved = self.resolve_body(project="claude-compare-demo")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.body_id, b.body_id)

    def test_forge_exit_ledger(self):
        store = self.BodyStore()
        b = store.init_body(kind="project", name="demo-x", repo="/tmp/demo-x")
        ev = self.ingest(
            b.body_id,
            channel="forge_exit",
            type_="nonzero",
            payload={"exit_code": 1, "exp": "demo-x", "run_id": "abc"},
        )
        self.assertIn("id", ev)
        events = self.list_events(b.body_id)
        self.assertTrue(any(e.get("channel") == "forge_exit" for e in events))
        open_obl = self.list_obligations(b.body_id, status="open")
        self.assertGreaterEqual(len(open_obl), 1)

    def test_min_mode(self):
        from body.schema import min_mode, apply_mode_caps

        self.assertEqual(min_mode("deep", "short"), "short")
        self.assertEqual(
            apply_mode_caps("deep", locked=False, body_cap="medium", breaker_cap="short"),
            "short",
        )
        pref = {}
        self.assertEqual(
            apply_mode_caps("deep", locked=True, body_cap="short", breaker_cap=None, preferred_store=pref),
            "deep",
        )
        self.assertEqual(pref.get("preferred_mode_cap"), "short")

    def test_organs_grow_and_kpi(self):
        from body.organs import ensure_default_organs, dispatch_procedures
        from body.kpis import body_kpis
        from body.outcomes import scorecard

        store = self.BodyStore()
        b = store.init_body(kind="project", name="kpi-demo", repo="/tmp/kpi-demo")
        organs = ensure_default_organs(b.body_id, store)
        self.assertIn("research", organs)
        self.assertIn("tokens", organs)
        ran = dispatch_procedures(
            b.body_id,
            trigger="forge_exit.completed",
            payload={"exit_code": 0, "exp": "x"},
            store=store,
        )
        self.assertTrue(any(r.get("action") == "note_success" for r in ran))
        k = body_kpis(b.body_id, store=store)
        self.assertEqual(k["body_id"], b.body_id)
        sc = scorecard(b.body_id, store=store)
        self.assertIn("grade", sc)
        self.assertIn("score", sc)


if __name__ == "__main__":
    unittest.main()


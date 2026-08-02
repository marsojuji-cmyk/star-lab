#!/usr/bin/env python3
"""Breaker FSM PR1 tests."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))
sys.path.insert(0, str(ROOT / "lib"))


class TestBreakerFSM(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GROK_LAB_DATA"] = self.tmp.name
        for mod in list(sys.modules):
            if mod.startswith("graph") or mod.startswith("resilience"):
                del sys.modules[mod]
        from graph import breaker as br

        self.br = br

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("GROK_LAB_DATA", None)

    def test_trip_reset_compat(self):
        self.br.trip("implementer", reason="test")
        self.assertTrue(self.br.is_tripped("implementer"))
        self.assertEqual(self.br.apply_to_policy("implementer", "full"), "budgeted")
        self.br.reset("implementer")
        self.assertFalse(self.br.is_tripped("implementer"))
        self.assertEqual(self.br.apply_to_policy("implementer", "full"), "full")

    def test_degraded_not_tripped(self):
        self.br.set_state("role:searcher", self.br.STATE_DEGRADED, reason="soft")
        self.assertFalse(self.br.is_tripped("searcher"))
        self.assertTrue(self.br.is_constrained("searcher"))
        bundle = self.br.apply_bundle("searcher", policy="full", budget=1000)
        self.assertEqual(bundle["policy"], "budgeted")
        self.assertEqual(bundle["budget"], 500.0)
        self.assertFalse(bundle["fail_fast"])

    def test_open_fail_fast(self):
        self.br.set_state("role:bad", self.br.STATE_OPEN, reason="hard")
        bundle = self.br.apply_bundle("bad", policy="full", budget=1000)
        self.assertTrue(bundle["fail_fast"])
        self.assertTrue(self.br.is_tripped("bad"))

    def test_record_hard_open(self):
        for _ in range(3):
            self.br.record("role:flaky", success=False, class_="hard", reason="boom")
        entry = (self.br.load_breakers().get("keys") or {}).get("role:flaky")
        self.assertEqual(entry.get("state"), self.br.STATE_OPEN)

    def test_tick_half_open(self):
        self.br.trip("probe", reason="x")
        data = self.br.load_breakers()
        key = "role:probe"
        data["keys"][key]["opened_ts"] = time.time() - 120
        data["config"] = {**self.br.DEFAULT_CONFIG, "reset_timeout_s": 30}
        self.br.save_breakers(data)
        self.br.tick("role:probe")
        entry = (self.br.load_breakers().get("keys") or {}).get("role:probe")
        self.assertEqual(entry.get("state"), self.br.STATE_HALF_OPEN)

    def test_v1_migration(self):
        # write v1 shape
        import json
        from pathlib import Path

        p = Path(os.environ["GROK_LAB_DATA"]) / "graph_breakers.json"
        p.write_text(
            json.dumps(
                {
                    "roles": {
                        "old": {
                            "tripped": True,
                            "reason": "legacy",
                            "fallback_policy": "budgeted",
                            "tripped_ts": 1.0,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        data = self.br.load_breakers()
        self.assertEqual(data.get("schema_version"), 2)
        self.assertEqual(data["keys"]["role:old"]["state"], self.br.STATE_OPEN)
        self.assertTrue(self.br.is_tripped("old"))


if __name__ == "__main__":
    unittest.main()

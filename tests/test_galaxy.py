#!/usr/bin/env python3
"""tests/test_galaxy.py — Astro Galaxy harvest + store (offline)."""

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

from galaxy.collector import collect_and_persist, harvest, health_score  # noqa: E402
from galaxy.store import GalaxyStore  # noqa: E402


class GalaxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.lab = Path(self._td.name) / "lab"
        self.lab.mkdir(parents=True)
        self._prev = os.environ.get("GROK_LAB_DATA")
        os.environ["GROK_LAB_DATA"] = str(self.lab)
        # Minimal token DB
        import sqlite3

        db = self.lab / "token_policy.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            """
            CREATE TABLE audits (
              id TEXT PRIMARY KEY, ts REAL, task TEXT, mode TEXT,
              predicted_horizon INTEGER, budget_tokens INTEGER,
              actual_tokens INTEGER, outcome_quality REAL,
              expected_value REAL, success INTEGER,
              drivers_json TEXT, notes TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("a1", 1.0, "t", "short", 100, 50, 80, 0.9, 0.5, 1, "[]", ""),
        )
        conn.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("a2", 2.0, "t2", "local", 40, 40, None, None, 0.4, None, "[]", ""),
        )
        conn.commit()
        conn.close()
        (self.lab / "research_kpi.json").write_text(
            json.dumps(
                {
                    "n_completed_logs": 5,
                    "accepted_patch_rate": 0.8,
                    "test_pass_rate": 0.9,
                    "average_tokens_per_success": 500,
                }
            ),
            encoding="utf-8",
        )
        (self.lab / "session_token_boot.json").write_text(
            json.dumps(
                {
                    "token_policy": "active",
                    "default_mode": "short",
                    "budget_tokens": 512,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("GROK_LAB_DATA", None)
        else:
            os.environ["GROK_LAB_DATA"] = self._prev
        self._td.cleanup()

    def test_harvest_stars(self) -> None:
        payload = harvest(root=self.lab, repo=ROOT)
        self.assertEqual(payload["system"], "astro-galaxy")
        self.assertIn("tokens", payload["stars"])
        self.assertIn("research", payload["stars"])
        self.assertIn("session", payload["stars"])
        self.assertEqual(payload["stars"]["tokens"]["metrics"]["n_audits"], 2)
        self.assertEqual(payload["stars"]["session"]["status"], "bright")
        self.assertGreater(payload["health_score"], 0.0)

    def test_persist_and_events(self) -> None:
        payload = collect_and_persist(root=self.lab, repo=ROOT, source="test")
        self.assertTrue(payload.get("snapshot_id"))
        store = GalaxyStore()
        latest = store.latest_snapshot()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["id"], payload["snapshot_id"])
        eid = store.log_event("tokens", "manual_check", 42, note="unit")
        self.assertTrue(eid)
        ev = store.recent_events(limit=5)
        self.assertTrue(any(e.get("key") == "manual_check" for e in ev))
        daily = self.lab / "metrics" / "daily"
        self.assertTrue(daily.is_dir())
        self.assertTrue(list(daily.glob("galaxy-*.json")))
        self.assertTrue((self.lab / "galaxy" / "latest.json").is_file())

    def test_health_score_weights(self) -> None:
        stars = {
            "tokens": {"status": "bright", "magnitude": 1.0},
            "health": {"status": "alert", "magnitude": 1.0},
        }
        s = health_score(stars)
        self.assertLess(s, 1.0)
        self.assertGreater(s, 0.0)


if __name__ == "__main__":
    unittest.main()

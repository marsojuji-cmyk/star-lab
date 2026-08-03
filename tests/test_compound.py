#!/usr/bin/env python3
"""Compounding rounds engine tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))
sys.path.insert(0, str(ROOT / "lib"))


class TestCompound(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["GROK_LAB_DATA"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("GROK_LAB_DATA", None)

    def test_next_steps_evolve(self):
        from compound.engine import next_steps_evolved

        s0 = next_steps_evolved("0x", 1.0, {}, {})
        s10 = next_steps_evolved("10x", 12.0, {}, {"ready_for_canary": True})
        s20 = next_steps_evolved("20x", 22.0, {}, {})
        s30 = next_steps_evolved("30x", 35.0, {}, {"ready_for_online": False})
        self.assertNotEqual(s0[0]["id"], s10[0]["id"])
        self.assertNotEqual(s10[0]["id"], s20[0]["id"])
        self.assertNotEqual(s20[0]["id"], s30[0]["id"])
        # 30× should talk about velocity / organs, not join rate
        titles = " ".join(s.get("title", "") for s in s30).lower()
        self.assertTrue("body" in titles or "velocity" in titles or "standing" in titles)

    def test_bridge_no_advance(self):
        from resilience.rollout_bridge import maybe_rollback_from_breaker

        # stage none → skip, never error hard
        out = maybe_rollback_from_breaker(key="policy:x", state="open", reason="test")
        self.assertIn(out.get("skipped") or out.get("acted"), (True, False, "stage_not_armed_for_rollback", "auto_rollback_not_armed", True))
        # acted is bool; skipped is string when present
        self.assertTrue(out.get("acted") is False or out.get("skipped"))

    def test_1000x_scorecard_shape(self):
        from compound.thousandx import estimate_lever_mults, evaluate_1000x

        levers = estimate_lever_mults(
            compound_product=65.0,
            savings_ratio=90.0,
            body={"n_bodies": 3, "avg_outcome_score": 90.0, "deep_waste_ops": 0},
            recovery={"retry_ok_rate": 0.9, "recovered_tasks": 5, "retry_n": 8},
            gates={"ready_for_canary": True, "ready_for_online": True, "golden": 1.0},
        )
        self.assertEqual(set(levers.keys()), {
            "waste_kill", "context", "recovery", "eval", "body", "reuse",
        })
        # evaluate_1000x with empty lab data should not crash
        x = evaluate_1000x(compound={
            "product": 1.0,
            "highest_round": "0x",
            "gates": {},
        })
        self.assertIn("system_product", x)
        self.assertIn("levers", x)
        self.assertIn("blockers", x)
        self.assertEqual(x.get("target"), 1000.0)


if __name__ == "__main__":
    unittest.main()

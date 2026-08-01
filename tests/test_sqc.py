#!/usr/bin/env python3
"""Tests for SQC sampling + quality loop."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from sqc.sampling import single_sample, double_sample, sequential_sprt_step, SequentialState, asn_curve
from sqc.risk import score_item_risk, prioritize_for_audit
from sqc.loop import QualityLoop


class TestSampling(unittest.TestCase):
    def test_single_accept(self):
        outcomes = [True] * 40
        d = single_sample(outcomes, n=40, c=2)
        self.assertEqual(d.decision, "accept")
        self.assertEqual(d.defects, 0)

    def test_single_reject(self):
        outcomes = [False] * 5 + [True] * 35
        d = single_sample(outcomes, n=40, c=2)
        self.assertEqual(d.decision, "reject")

    def test_double_second_stage(self):
        # d1 = 2 → need second sample if c1=0 c2=3
        outcomes = [False, False] + [True] * 48
        d = double_sample(outcomes, n1=25, c1=0, c2=3, n2=25)
        self.assertIn(d.decision, ("accept", "reject", "need_second_sample"))
        self.assertGreaterEqual(d.inspected, 25)

    def test_sprt_accepts_good_stream(self):
        st = SequentialState(p0=0.02, p1=0.15, alpha=0.05, beta=0.1)
        dec = None
        for _ in range(200):
            st, dec = sequential_sprt_step(st, True)
            if dec.decision != "continue":
                break
        self.assertIsNotNone(dec)
        self.assertEqual(dec.decision, "accept")

    def test_asn_curve_shape(self):
        asn = asn_curve(trials=40, n=30, n1=20, n2=20)
        self.assertIn("curves", asn)
        self.assertEqual(len(asn["curves"]["p_pct"]), len(asn["curves"]["SPRT"]))
        # SPRT avg should be below CI budget on average at low p
        self.assertLess(asn["curves"]["SPRT"][0], asn["curves"]["CI"][0])


class TestRisk(unittest.TestCase):
    def test_empty_high_risk(self):
        r = score_item_risk("")
        self.assertGreaterEqual(r.score, 0.9)
        self.assertTrue(r.recommend_audit)

    def test_clean_low_risk(self):
        r = score_item_risk("The unit test passed and the patch is complete.")
        self.assertLess(r.score, 0.45)

    def test_prioritize(self):
        items = [
            {"id": "a", "text": "ok result"},
            {"id": "b", "text": ""},
            {"id": "c", "text": "maybe this is wrong idk"},
        ]
        ranked = prioritize_for_audit(items)
        self.assertEqual(ranked[0]["id"], "b")


class TestLoop(unittest.TestCase):
    def test_loop_accept(self):
        with tempfile.TemporaryDirectory() as td:
            loop = QualityLoop(db_dir=Path(td))
            items = [{"id": str(i), "text": f"good annotation {i}", "is_correct": True} for i in range(60)]
            res = loop.evaluate_batch(items, plan="single", n=40, c=2)
            self.assertTrue(res.quality_sufficient)
            self.assertEqual(res.decision, "accept_batch")

    def test_loop_improve(self):
        with tempfile.TemporaryDirectory() as td:
            loop = QualityLoop(db_dir=Path(td))
            items = [{"id": str(i), "text": "bad", "is_correct": False} for i in range(40)]
            res = loop.evaluate_batch(items, plan="single", n=40, c=1)
            self.assertFalse(res.quality_sufficient)
            self.assertIn(res.decision, ("improve", "reject_batch", "continue_sampling"))
            self.assertTrue(res.interventions)


if __name__ == "__main__":
    unittest.main()

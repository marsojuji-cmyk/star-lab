#!/usr/bin/env python3
"""Tests for research golden log + SQC distill gate."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from research.logstore import ResearchLog
from tokens.distill import distill_rules, SQCGateError, assert_sqc_gate
from tokens.audit import AuditStore
from sqc.loop import QualityLoop


class TestResearchLog(unittest.TestCase):
    def test_start_complete_kpi(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            log = ResearchLog(db_path=Path(td) / "research_log.db")
            tid = log.start("demo goal", repo="starlab-demo", mode="short", predicted_horizon=500)
            log.action(tid, type="tool", name="unittest", ok=True)
            p = log.complete(
                tid,
                success=True,
                actual_tokens=1200,
                tests_passed=True,
                sqc_quality_ok=True,
            )
            self.assertEqual(p["status"], "completed")
            self.assertEqual(p["metrics"]["tokens_per_success"], 1200)
            k = log.kpi()
            self.assertEqual(k["n_completed_logs"], 1)
            self.assertEqual(k["accepted_patch_rate"], 1.0)
            self.assertEqual(k["average_tokens_per_success"], 1200.0)


class TestSQCGate(unittest.TestCase):
    def test_distill_blocked_without_loop(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            store = AuditStore(db_path=Path(td) / "token_policy.db")
            with self.assertRaises(SQCGateError):
                distill_rules(store, min_support=1, require_sqc=True)

    def test_distill_allowed_after_accept(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            # pass SQC loop
            loop = QualityLoop(db_dir=Path(td) / "sqc")
            items = [
                {"id": str(i), "text": f"good {i}", "is_correct": True} for i in range(50)
            ]
            res = loop.evaluate_batch(items, plan="single", n=40, c=2)
            self.assertTrue(res.quality_sufficient)
            store = AuditStore(db_path=Path(td) / "token_policy.db")
            # seed short hi quality audits
            for i in range(5):
                aid = store.log_route(
                    task="quick",
                    mode="short",
                    predicted_horizon=200,
                    budget_tokens=512,
                    expected_value=0.7,
                    drivers=[],
                )
                store.complete(aid, actual_tokens=180, outcome_quality=0.9, success=True)
            rules, gate = distill_rules(store, min_support=3, require_sqc=True)
            self.assertTrue(gate.get("gated"))
            self.assertIsInstance(rules, list)

    def test_ungated_override(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            store = AuditStore(db_path=Path(td) / "token_policy.db")
            rules, gate = distill_rules(
                store, min_support=99, require_sqc=True, allow_ungated=True
            )
            self.assertFalse(gate.get("gated"))
            self.assertEqual(rules, [])


if __name__ == "__main__":
    unittest.main()

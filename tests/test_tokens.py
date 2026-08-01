#!/usr/bin/env python3
"""Unit tests for Token-Aware Control Plane (no network)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))
sys.path.insert(0, str(ROOT / "lib"))

from tokens.horizon import estimate_horizon, estimate_tokens_from_text
from tokens.policy import route_task, MODE_LOCAL, MODE_SHORT, MODE_MEDIUM, MODE_DEEP
from tokens.audit import AuditStore
from tokens.distill import distill_rules


class TestHorizon(unittest.TestCase):
    def test_empty(self):
        h = estimate_horizon("")
        self.assertEqual(h.predicted_tokens, 0)

    def test_ops_shorter_than_agentic(self):
        short = estimate_horizon("lab status")
        deep = estimate_horizon(
            "Design and implement a multi-agent workflow to refactor the entire monorepo step by step"
        )
        self.assertLess(short.predicted_tokens, deep.predicted_tokens)
        self.assertTrue(any(d.get("regime") == "long" for d in deep.drivers))

    def test_chars_per_token(self):
        self.assertGreaterEqual(estimate_tokens_from_text("abcd"), 1)


class TestRoute(unittest.TestCase):
    def test_ops_local(self):
        d = route_task("lab doctor health check status")
        self.assertEqual(d.mode, MODE_LOCAL)
        self.assertFalse(d.escalate)
        self.assertEqual(d.budget_tokens, 0)

    def test_cheap_never_deep(self):
        d = route_task("quick typo rename variable foo to bar")
        self.assertNotEqual(d.mode, MODE_DEEP)

    def test_agentic_prefers_escalation(self):
        d = route_task(
            "Build a multi-agent parallel workflow to debug and implement a full design system"
        )
        self.assertIn(d.mode, (MODE_MEDIUM, MODE_DEEP, MODE_SHORT))
        self.assertTrue(d.escalate)
        self.assertGreater(d.expected_value, d.local_expected_value)

    def test_force_mode(self):
        d = route_task("anything", force_mode=MODE_SHORT)
        self.assertEqual(d.mode, MODE_SHORT)
        self.assertEqual(d.budget_tokens, 512)

    def test_packing_present(self):
        d = route_task("implement a feature with tests")
        self.assertIn("max_context_tokens", d.packing)
        self.assertIn("retrieval_k", d.packing)


class TestAuditDistill(unittest.TestCase):
    def test_audit_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            store = AuditStore(db_path=Path(td) / "token_policy.db")
            aid = store.log_route(
                task="lab status",
                mode="local",
                predicted_horizon=100,
                budget_tokens=0,
                expected_value=0.9,
                drivers=[],
            )
            store.complete(aid, actual_tokens=0, outcome_quality=1.0, success=True)
            # seed more for distill
            for i in range(5):
                a = store.log_route(
                    task="status check",
                    mode="local",
                    predicted_horizon=50,
                    budget_tokens=0,
                    expected_value=0.9,
                    drivers=[],
                )
                store.complete(a, actual_tokens=0, outcome_quality=0.95, success=True)
            for i in range(5):
                a = store.log_route(
                    task="quick",
                    mode="short",
                    predicted_horizon=200,
                    budget_tokens=512,
                    expected_value=0.7,
                    drivers=[],
                )
                store.complete(a, actual_tokens=180, outcome_quality=0.9, success=True)
            stats = store.error_stats()
            self.assertGreaterEqual(stats["n"], 5)
            rules = distill_rules(store, min_support=3)
            self.assertIsInstance(rules, list)
            recent = store.recent(5)
            self.assertTrue(recent)


if __name__ == "__main__":
    unittest.main()

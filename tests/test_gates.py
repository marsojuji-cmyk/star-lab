#!/usr/bin/env python3
"""Tests for graduation gates, frozen eval, session lock, canary."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))


class TestFrozenEval(unittest.TestCase):
    def test_suite_loads_and_scores(self):
        from tokens.eval_router import eval_frozen, load_suite

        suite = load_suite()
        self.assertGreaterEqual(len(suite), 8)
        r = eval_frozen()
        self.assertEqual(r["n"], len(suite))
        self.assertIsNotNone(r["agreement"])
        self.assertGreaterEqual(r["agreement"], 0.0)


class TestSessionLock(unittest.TestCase):
    def test_lock_unlock(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            from tokens.session_lock import acquire_lock, release_lock, get_lock, apply_lock_to_route

            self.assertIsNone(get_lock())
            acquire_lock(reason="tool_loop", mode="medium")
            lock = get_lock()
            self.assertTrue(lock["active"])
            info = apply_lock_to_route("short", force_mode=None)
            self.assertTrue(info["locked"])
            self.assertEqual(info["mode"], "medium")
            release_lock(force=True)
            self.assertIsNone(get_lock())


class TestCanaryAndGates(unittest.TestCase):
    def test_canary_propose_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            from tokens.gates import canary_propose, canary_rollback, load_canary, evaluate_graduation

            canary_propose("rules_test_v1", notes="unit")
            st = load_canary()
            self.assertEqual(st["status"], "proposed")
            canary_rollback(reason="test")
            self.assertEqual(load_canary()["status"], "rolled_back")
            rep = evaluate_graduation(golden_agreement=0.5)
            self.assertFalse(rep.ready_for_online)
            self.assertIn("drop_rules", rep.to_dict())


if __name__ == "__main__":
    unittest.main()

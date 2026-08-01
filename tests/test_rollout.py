#!/usr/bin/env python3
"""Four-stage rollout + graph circuit breaker tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))


class TestStickyCohort(unittest.TestCase):
    def test_sticky(self):
        from tokens.rollout import sticky_in_cohort

        a = sticky_in_cohort("sess-1", 0.5, salt="t")
        b = sticky_in_cohort("sess-1", 0.5, salt="t")
        self.assertEqual(a, b)
        self.assertFalse(sticky_in_cohort("x", 0.0))
        self.assertTrue(sticky_in_cohort("x", 1.0))


class TestRolloutMachine(unittest.TestCase):
    def test_propose_drill_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            os.environ["GROK_ROLLOUT_FAST"] = "1"
            from tokens import rollout as R

            R.propose("candidate_test")
            st = R.load_state()
            self.assertEqual(st["stage"], "proposed")
            drill = R.drill()
            self.assertTrue(drill["ok"])
            self.assertEqual(drill["state"]["stage"], "rolled_back")
            self.assertEqual(drill["state"]["traffic_frac"], 0.0)

    def test_hard_stop_triggers_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            os.environ["GROK_ROLLOUT_FAST"] = "1"
            from tokens import rollout as R

            R.propose("cand")
            st = R.load_state()
            st["stage"] = "canary"
            st["traffic_frac"] = 0.01
            st["baseline_metrics"] = {
                "task_success_rate": 0.9,
                "human_interrupt_avg": 0.0,
                "p95_latency_s": 1.0,
                "cost_per_success": 1000,
                "hard_safety_violations": 0,
                "validate_fail_rate": 0.0,
                "n_samples": 10,
            }
            st["window_started_ts"] = 0  # ancient → window duration ok with fast? need elapsed
            import time

            st["window_started_ts"] = time.time() - 10
            R.save_state(st)
            bad = {
                "task_success_rate": 0.9,
                "human_interrupt_avg": 0.0,
                "p95_latency_s": 1.0,
                "cost_per_success": 1000,
                "hard_safety_violations": 1,  # hard stop
                "validate_fail_rate": 0.0,
                "n_samples": 10,
            }
            res = R.check_and_maybe_rollback(force_metrics=bad)
            self.assertTrue(res.get("rolled_back"))
            self.assertEqual(R.load_state()["stage"], "rolled_back")


class TestGraphBreaker(unittest.TestCase):
    def test_trip_forces_budgeted(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            from graph.breaker import trip, reset, apply_to_policy
            from graph.router import route_context

            trip("implementer", reason="cascade", fallback_policy="budgeted")
            self.assertEqual(apply_to_policy("implementer", "role_aware"), "budgeted")
            mem = [
                {
                    "id": "1",
                    "text": "code implement patch",
                    "role": "implementer",
                    "tokens": 100,
                    "ts": 1e9,
                }
            ]
            r = route_context(mem, "implementer", "implement", budget=50, policy="role_aware")
            self.assertEqual(r.policy, "budgeted")
            reset("implementer")
            self.assertEqual(apply_to_policy("implementer", "role_aware"), "role_aware")


if __name__ == "__main__":
    unittest.main()

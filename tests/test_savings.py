#!/usr/bin/env python3
"""Token savings suite vs claude_unbounded."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from tokens.savings import compare_task, run_suite, predicted_spend, unbounded_pack
from tokens.policy import route_task, MODE_LOCAL, MODE_DEEP


class TestSavings(unittest.TestCase):
    def test_ops_local_zero_lab_spend(self):
        os.environ["GROK_TOKEN_PACK"] = "aggressive"
        row = compare_task("lab doctor", baseline_id="claude_unbounded")
        self.assertEqual(row["lab_mode"], MODE_LOCAL)
        self.assertEqual(row["lab_spend"], 0)
        self.assertGreater(row["base_spend"], 10000)
        self.assertTrue(row.get("ratio_inf") or (row.get("ratio") or 0) > 100)

    def test_unbounded_is_fat(self):
        p = unbounded_pack()
        self.assertEqual(p["max_context_tokens"], 24000)
        self.assertEqual(p["subagents"], 2)
        s = predicted_spend(MODE_DEEP, p)
        # 8192 + 24000*3 = 80192
        self.assertEqual(s, 8192 + 24000 * 3)

    def test_suite_hits_100x(self):
        os.environ["GROK_TOKEN_PACK"] = "aggressive"
        out = run_suite(baseline_id="claude_unbounded", persist=False)
        self.assertTrue(out["n_tasks"] >= 20)
        self.assertTrue(
            out.get("hit_100x") or (out.get("total_ratio") or 0) >= 50,
            msg=f"ratio={out.get('total_ratio')} lab={out.get('sum_lab_spend')} base={out.get('sum_base_spend')}",
        )
        # Prefer hard 100x on default suite
        self.assertTrue(
            out.get("hit_100x"),
            msg=f"expected >=100×, got {out.get('total_ratio')}",
        )


if __name__ == "__main__":
    unittest.main()

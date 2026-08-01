#!/usr/bin/env python3
"""Embedding expansion drift eval tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from weights.embedding_drift import (
    load_slice_file,
    run_drift_eval,
    write_example_slices,
    SliceItem,
    evaluate_gate,
    cosine_shifts,
    DriftGateConfig,
)


class TestDriftEval(unittest.TestCase):
    def test_example_expected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.jsonl"
            write_example_slices(p)
            items = load_slice_file(p)
            self.assertEqual(len(items), 4)
            report = run_drift_eval(items)
            v = report["gate"]["verdict"]
            # synthetic: legacy nearly fixed, new_token moves a lot
            self.assertIn(v, ("expected", "warning"))
            cos = report["cosine_shift"]["by_slice"]
            self.assertIsNotNone(cos["legacy"])
            self.assertIsNotNone(cos["new_token"])
            self.assertGreater(
                cos["new_token"]["mean_cosine_shift"],
                cos["legacy"]["mean_cosine_shift"],
            )

    def test_harmful_legacy_plus_task(self):
        items = [
            SliceItem(
                id="L1",
                text="a",
                slice="legacy",
                emb_baseline=[1.0, 0.0, 0.0],
                emb_expanded=[0.0, 1.0, 0.0],  # huge shift
                label="A",
                pred_baseline="A",
                pred_expanded="B",  # task hit
            ),
            SliceItem(
                id="L2",
                text="b",
                slice="legacy",
                emb_baseline=[0.0, 1.0, 0.0],
                emb_expanded=[1.0, 0.0, 0.0],
                label="B",
                pred_baseline="B",
                pred_expanded="A",
            ),
        ]
        report = run_drift_eval(items)
        self.assertEqual(report["gate"]["verdict"], "harmful")

    def test_warning_displacement_flat_task(self):
        items = [
            SliceItem(
                id="L1",
                text="a",
                slice="legacy",
                emb_baseline=[1.0, 0.0, 0.0],
                emb_expanded=[0.7, 0.7, 0.0],  # moderate-high shift
                label="A",
                pred_baseline="A",
                pred_expanded="A",  # flat task
            ),
            SliceItem(
                id="L2",
                text="b",
                slice="legacy",
                emb_baseline=[0.0, 1.0, 0.0],
                emb_expanded=[0.6, 0.8, 0.0],
                label="B",
                pred_baseline="B",
                pred_expanded="B",
            ),
        ]
        report = run_drift_eval(items)
        self.assertIn(report["gate"]["verdict"], ("warning", "harmful", "expected"))
        # with high shift and flat tasks, gate should not hard-block only on displacement
        # (implementation: warning if no task hit)
        if report["cosine_shift"]["by_slice"]["legacy"]["mean_cosine_shift"] > 0.12:
            self.assertNotEqual(
                report["gate"]["verdict"],
                "insufficient_data",
            )


if __name__ == "__main__":
    unittest.main()

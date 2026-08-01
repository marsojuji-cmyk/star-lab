#!/usr/bin/env python3
"""Tests for L2 graph context routing (RCR-style) + packet attach."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from graph.router import route_context, ablate
from graph.allocator import allocate_budget
from graph.logstore import GraphLog


def _mem():
    now = time.time()
    return [
        {
            "id": "goal",
            "role": "main",
            "stage": "plan",
            "kind": "goal",
            "text": "Fix failing unit tests in starlab-demo and keep the patch minimal",
            "ts": now,
            "importance": 0.9,
            "tokens": 40,
        },
        {
            "id": "fail",
            "role": "validator",
            "stage": "validate",
            "kind": "failure",
            "text": "unittest failed: AssertionError in test_hello",
            "ts": now - 60,
            "importance": 0.95,
            "tokens": 80,
        },
        {
            "id": "code",
            "role": "implementer",
            "stage": "implement",
            "kind": "code",
            "text": "def hello(): return 'world'  # implementation detail " * 20,
            "ts": now - 120,
            "tokens": 400,
        },
        {
            "id": "stale",
            "role": "planner",
            "stage": "plan",
            "kind": "notes",
            "text": "old brainstorm about redesigning architecture from scratch",
            "ts": now - 86400 * 3,
            "tokens": 300,
        },
        {
            "id": "docs",
            "role": "searcher",
            "stage": "execute",
            "kind": "docs",
            "text": "knowledge search hit about unittest discover patterns",
            "ts": now - 300,
            "tokens": 150,
        },
    ]


class TestGraphRouter(unittest.TestCase):
    def test_allocate_budget(self):
        b = allocate_budget("planner", parent_context_budget=2000, stage="plan")
        self.assertGreater(b, 500)
        self.assertLessEqual(b, 2000)

    def test_role_aware_drops_under_budget(self):
        r = route_context(_mem(), "validator", "validate", budget=200, policy="role_aware")
        self.assertEqual(r.policy, "role_aware")
        self.assertLessEqual(r.tokens_passed + r.tokens_summarized, 200)
        passed_ids = {d.id for d in r.decisions if d.action in ("pass", "summarize")}
        self.assertIn("fail", passed_ids)

    def test_full_carries_all(self):
        r = route_context(_mem(), "main", "plan", budget=50, policy="full")
        self.assertEqual(r.n_dropped, 0)
        self.assertGreater(r.tokens_passed, 50)

    def test_ablate_role_aware_saves_vs_full(self):
        table = ablate(_mem(), "implementer", "implement", budget=250)
        full = table["arms"]["full"]["tokens_carried"]
        ra = table["arms"]["role_aware"]["tokens_carried"]
        self.assertLessEqual(ra, full)
        self.assertIsNotNone(table["arms"]["role_aware"]["vs_full_save_frac"])

    def test_logstore(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            log = GraphLog(db_path=Path(td) / "graph_routes.db")
            r = route_context(_mem(), "planner", "plan", budget=300, policy="role_aware")
            nid = log.log_route_result(r.to_dict())
            self.assertTrue(nid)
            s = log.stats()
            self.assertEqual(s["n_nodes"], 1)


class TestPacketAttach(unittest.TestCase):
    def test_packet_create_load_attach(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["GROK_LAB_DATA"] = td
            from research.packet import create_packet, load_packet
            from research.logstore import ResearchLog

            pkt = create_packet(
                "demo escalate",
                repo="starlab-demo",
                files=["hello.py"],
                failing_tests="1 failed",
            )
            loaded = load_packet(pkt["id"])
            self.assertEqual(loaded["task_goal"], "demo escalate")
            log = ResearchLog(db_path=Path(td) / "research_log.db")
            tid = log.start(
                "demo", repo="starlab-demo", context_pack={"packet_id": pkt["id"]}
            )
            log.attach_context_pack(tid, {"id": pkt["id"], "files": ["hello.py"]})
            p = log._load(tid)
            self.assertEqual(p.get("packet_id"), pkt["id"])


if __name__ == "__main__":
    unittest.main()

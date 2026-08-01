#!/usr/bin/env python3
# tests/test_forge.py — Experiment Forge unit/integration tests (PR3)
"""Uses tempfile GROK_LAB_DATA override; no paid SaaS; stdlib only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORGE_DIR = ROOT / "modules" / "forge"
LIB_DIR = ROOT / "lib"
LAB = ROOT / "bin" / "lab"


def _prep_env(lab_data: Path) -> dict:
    env = os.environ.copy()
    env["GROK_LAB_DATA"] = str(lab_data)
    env["GROK_LAB_REPO"] = str(ROOT)
    env["GROK_HOME"] = str(lab_data.parent)  # isolate from real ~/.grok when possible
    # Ensure python can find modules if tests import directly
    return env


class ForgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="forge-test-")
        self.lab_data = Path(self._tmpdir) / "lab"
        self.lab_data.mkdir(parents=True)
        self.env = _prep_env(self.lab_data)
        # Import forge package against this lab data (modules/ on path)
        for p in (str(LIB_DIR), str(FORGE_DIR.parent)):
            if p in sys.path:
                sys.path.remove(p)
            sys.path.insert(0, p)
        # Drop modules/forge itself so `import forge` is the package
        if str(FORGE_DIR) in sys.path:
            sys.path.remove(str(FORGE_DIR))
        # Reload path helpers / forge with env set
        os.environ["GROK_LAB_DATA"] = str(self.lab_data)
        os.environ["GROK_LAB_REPO"] = str(ROOT)
        # Clear cached modules that bake paths
        for mod in list(sys.modules):
            if mod == "lab_paths" or mod == "forge" or mod.startswith("forge."):
                del sys.modules[mod]
        import lab_paths  # noqa: F401
        import forge.forge as forge_mod

        self.forge = forge_mod

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_store_creates_wal_db(self) -> None:
        store = self.forge.ForgeStore()
        db = self.forge.get_db_path()
        self.assertTrue(db.is_file(), "experiments.db should exist")
        self.assertEqual(db, self.lab_data / "experiments.db")
        with store.connect() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(str(mode).lower(), "wal")
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(ver, 1)
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("experiments", tables)
            self.assertIn("runs", tables)

    def test_get_or_create_experiment_idempotent(self) -> None:
        store = self.forge.ForgeStore()
        a = store.get_or_create_experiment("gym-smoke", project="grok-home", tags=["gym"])
        b = store.get_or_create_experiment("gym-smoke", project="grok-home")
        self.assertEqual(a["id"], b["id"])
        c = store.get_or_create_experiment("gym-smoke", project="other")
        self.assertNotEqual(a["id"], c["id"])

    def test_run_command_success_sets_env_and_writes(self) -> None:
        store = self.forge.ForgeStore()
        # Child prints GROK_LAB_RUN_ID and exits 0
        code = self.forge.run_command(
            store,
            exp_name="env-check",
            command=[
                sys.executable,
                "-c",
                "import os,sys; "
                "rid=os.environ.get('GROK_LAB_RUN_ID',''); "
                "assert rid, 'missing RUN_ID'; "
                "assert os.environ.get('GROK_LAB_DATA'); "
                "assert os.environ.get('GROK_LAB_REPO'); "
                "print('RUN='+rid); sys.exit(0)",
            ],
            project="test",
            tags=["unit"],
        )
        self.assertEqual(code, 0)
        runs = store.list_runs()
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["exit_code"], 0)
        self.assertIsNotNone(run["duration_ms"])
        self.assertGreaterEqual(run["duration_ms"], 0)
        self.assertIsNotNone(run["finished_at"])

        rd = self.lab_data / "experiments" / run["id"]
        self.assertTrue((rd / "results.json").is_file())
        self.assertTrue((rd / "meta.md").is_file())
        self.assertTrue((rd / "console.log").is_file())

        results = json.loads((rd / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["run_id"], run["id"])
        self.assertEqual(results["status"], "completed")
        self.assertEqual(results["experiment_name"], "env-check")
        self.assertIn("duration_ms", results)

        meta = (rd / "meta.md").read_text(encoding="utf-8")
        self.assertIn(run["id"], meta)
        self.assertIn("completed", meta)

    def test_run_command_failure_status(self) -> None:
        store = self.forge.ForgeStore()
        code = self.forge.run_command(
            store,
            exp_name="fail-check",
            command=[sys.executable, "-c", "import sys; sys.exit(7)"],
        )
        self.assertEqual(code, 7)
        run = store.list_runs()[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 7)
        results = json.loads(
            (self.lab_data / "experiments" / run["id"] / "results.json").read_text()
        )
        self.assertEqual(results["status"], "failed")

    def test_child_metric_api(self) -> None:
        store = self.forge.ForgeStore()
        # Child uses Forge API via injected PYTHONPATH (no sys.path surgery)
        child = (
            "from forge import Forge; "
            "f=Forge(); "
            "f.log_param('model','dolphin3:latest'); "
            "f.log_metric('pass_rate',1.0,step=0); "
            "f.log_metric('n_pass',2); "
            "print('ok')"
        )
        code = self.forge.run_command(
            store,
            exp_name="metric-check",
            command=[sys.executable, "-c", child],
            tags=["gym"],
        )
        self.assertEqual(code, 0)
        run = store.list_runs()[0]
        results = json.loads(
            (self.lab_data / "experiments" / run["id"] / "results.json").read_text()
        )
        self.assertEqual(results["params"].get("model"), "dolphin3:latest")
        self.assertEqual(results["metrics"].get("pass_rate"), 1.0)
        self.assertEqual(results["metrics"].get("n_pass"), 2.0)

    def test_timeout_aborts_hung_child(self) -> None:
        store = self.forge.ForgeStore()
        t0 = time.monotonic()
        code = self.forge.run_command(
            store,
            exp_name="timeout-check",
            command=[sys.executable, "-c", "import time; time.sleep(60)"],
            timeout=1.0,
        )
        elapsed = time.monotonic() - t0
        self.assertEqual(code, self.forge.EXIT_TIMEOUT)
        self.assertLess(elapsed, 10.0, "timeout should fire well before sleep(60)")
        run = store.list_runs()[0]
        self.assertEqual(run["status"], "aborted")
        self.assertEqual(run["exit_code"], self.forge.EXIT_TIMEOUT)
        self.assertIsNotNone(run["finished_at"])
        rd = self.lab_data / "experiments" / run["id"]
        self.assertTrue((rd / "results.json").is_file())
        results = json.loads((rd / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["status"], "aborted")
        self.assertTrue((rd / "meta.md").is_file())

    def test_command_not_found_exit_127(self) -> None:
        store = self.forge.ForgeStore()
        code = self.forge.run_command(
            store,
            exp_name="missing-cmd",
            command=["__forge_no_such_binary_xyz__"],
        )
        self.assertEqual(code, 127)
        run = store.list_runs()[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 127)
        rd = self.lab_data / "experiments" / run["id"]
        self.assertTrue((rd / "results.json").is_file())
        self.assertTrue((rd / "meta.md").is_file())
        results = json.loads((rd / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["status"], "failed")
        self.assertEqual(results["exit_code"], 127)

    def test_pythonpath_enables_forge_import(self) -> None:
        store = self.forge.ForgeStore()
        code = self.forge.run_command(
            store,
            exp_name="pypath",
            command=[
                sys.executable,
                "-c",
                "import os; "
                "assert 'modules' in os.environ.get('PYTHONPATH',''); "
                "from forge import Forge; "
                "Forge().log_metric('ok', 1); "
                "print('imported')",
            ],
        )
        self.assertEqual(code, 0)
        run = store.list_runs()[0]
        results = json.loads(
            (self.lab_data / "experiments" / run["id"] / "results.json").read_text()
        )
        self.assertEqual(results["metrics"].get("ok"), 1.0)

    def test_export_jsonl(self) -> None:
        store = self.forge.ForgeStore()
        self.forge.run_command(
            store,
            exp_name="export-me",
            command=[sys.executable, "-c", "print('x')"],
        )
        proc = subprocess.run(
            [str(LAB), "forge", "export", "--exp", "export-me"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertIn("id", row)
        self.assertEqual(row["status"], "completed")

    def test_forge_requires_run_id(self) -> None:
        os.environ.pop("GROK_LAB_RUN_ID", None)
        with self.assertRaises(RuntimeError):
            self.forge.Forge()

    def test_atomic_dual_write_no_tmp_left(self) -> None:
        store = self.forge.ForgeStore()
        code = self.forge.run_command(
            store,
            exp_name="atomic",
            command=[sys.executable, "-c", "print('hi')"],
        )
        self.assertEqual(code, 0)
        run = store.list_runs()[0]
        rd = self.lab_data / "experiments" / run["id"]
        leftovers = list(rd.glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_cli_via_lab_facade(self) -> None:
        # lab forge run --exp NAME -- python3 -c '...'
        proc = subprocess.run(
            [
                str(LAB),
                "forge",
                "run",
                "--exp",
                "cli-smoke",
                "--project",
                "grok-home",
                "--tag",
                "smoke",
                "--",
                sys.executable,
                "-c",
                "import os; print(os.environ['GROK_LAB_RUN_ID'][:8])",
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        # list
        proc2 = subprocess.run(
            [str(LAB), "forge", "list"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc2.returncode, 0, msg=proc2.stderr)
        self.assertIn("cli-smoke", proc2.stdout)
        self.assertIn("completed", proc2.stdout)

        # show via full run id from db
        store = self.forge.ForgeStore()
        run = store.list_runs()[0]
        proc3 = subprocess.run(
            [str(LAB), "forge", "show", run["id"]],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc3.returncode, 0, msg=proc3.stderr)
        self.assertIn(run["id"], proc3.stdout)
        self.assertIn("completed", proc3.stdout)

        # show by prefix
        proc4 = subprocess.run(
            [str(LAB), "forge", "show", run["id"][:12]],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc4.returncode, 0, msg=proc4.stderr)

    def test_cli_exit_code_propagates(self) -> None:
        proc = subprocess.run(
            [
                str(LAB),
                "forge",
                "run",
                "--exp",
                "exit-prop",
                "--",
                sys.executable,
                "-c",
                "import sys; sys.exit(3)",
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 3)

    def test_cli_init_and_list_experiments(self) -> None:
        proc = subprocess.run(
            [str(LAB), "forge", "init", "--exp", "solo", "--project", "p"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("solo", proc.stdout)
        proc2 = subprocess.run(
            [str(LAB), "forge", "list", "--experiments"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc2.returncode, 0)
        self.assertIn("solo", proc2.stdout)

    def test_help_lists_forge(self) -> None:
        proc = subprocess.run(
            [str(LAB), "help"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("forge", proc.stdout)


if __name__ == "__main__":
    unittest.main()

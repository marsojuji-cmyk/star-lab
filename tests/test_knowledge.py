#!/usr/bin/env python3
# Python 3.9+ — Knowledge Crucible unit/integration tests (temp dirs only)
"""
Tests index + query with isolated GROK_HOME / GROK_LAB_DATA / PROJECTS.
Never touches real ~/.grok or session_search.sqlite.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Repo paths
ROOT = Path(__file__).resolve().parent.parent
KNOW = ROOT / "modules" / "knowledge"
LIB = ROOT / "lib"
sys.path.insert(0, str(KNOW))
sys.path.insert(0, str(LIB))


class KnowledgeFTSTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="lab-knowledge-test."))
        self.grok = self.tmpdir / "grok"
        self.lab = self.tmpdir / "lab"
        self.projects = self.tmpdir / "Projects"
        self.db = self.lab / "knowledge" / "fts.db"

        (self.grok / "memory").mkdir(parents=True)
        (self.grok / "rules").mkdir(parents=True)
        (self.lab / "knowledge").mkdir(parents=True)
        (self.lab / "experiments" / "exp1").mkdir(parents=True)

        # Env isolation (lab_paths reads these)
        self._env_backup = {
            k: os.environ.get(k)
            for k in ("GROK_HOME", "GROK_LAB_DATA", "PROJECTS", "GROK_LAB_REPO")
        }
        os.environ["GROK_HOME"] = str(self.grok)
        os.environ["GROK_LAB_DATA"] = str(self.lab)
        os.environ["PROJECTS"] = str(self.projects)
        os.environ["GROK_LAB_REPO"] = str(ROOT)

        # Reload lab_paths / knowledge modules against new env
        for mod in list(sys.modules):
            if mod in ("lab_paths", "index", "query", "cli") or mod.startswith(
                "modules.knowledge"
            ):
                del sys.modules[mod]

        import lab_paths  # noqa: F401
        import index as knowledge_index
        import query as knowledge_query

        self.index = knowledge_index
        self.query = knowledge_query

        self._seed_corpus()

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed_corpus(self) -> None:
        # Memory
        (self.grok / "memory" / "MEMORY.md").write_text(
            "# Durable memory\n\nPrefer user-local Homebrew.\n"
            "Knowledge crucible uses FTS5 offline.\n",
            encoding="utf-8",
        )
        # Rules
        (self.grok / "rules" / "home.md").write_text(
            "# Home Charter\n\nAlways-approve with safety rails.\n",
            encoding="utf-8",
        )
        # Project with AGENTS + design docs
        proj = self.projects / "demo-app"
        (proj / "docs").mkdir(parents=True)
        (proj / "AGENTS.md").write_text(
            "# demo-app agents\n\nUse the ship-it skill before merge.\n",
            encoding="utf-8",
        )
        (proj / "docs" / "DESIGN.md").write_text(
            "# Design: demo-app\n\nCrucible indexes design markdown.\n"
            "Unique token: zebra-widget-42\n",
            encoding="utf-8",
        )
        # Excluded: node_modules markdown must not appear
        nm = proj / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "README.md").write_text(
            "# should-not-index node_modules secret-token-xyz\n",
            encoding="utf-8",
        )
        # Excluded: .git
        git_dir = proj / ".git"
        git_dir.mkdir()
        (git_dir / "COMMIT_EDITMSG.md").write_text(
            "# git noise secret-git-token\n", encoding="utf-8"
        )
        # Oversized file (>1 MiB) under docs — skipped
        big = proj / "docs" / "huge.md"
        big.write_bytes(b"# big\n" + (b"x" * (1 * 1024 * 1024 + 100)))
        # Experiment meta
        (self.lab / "experiments" / "exp1" / "meta.md").write_text(
            "# exp1\n\nMeasured FTS latency under one second.\n",
            encoding="utf-8",
        )
        # Another project without docs
        other = self.projects / "other-proj"
        other.mkdir()
        (other / "AGENTS.md").write_text(
            "# other\n\nOnly agents file here.\n", encoding="utf-8"
        )

    def test_rebuild_and_query(self) -> None:
        stats = self.index.rebuild_index(
            db_path=self.db,
            projects_root=self.projects,
            grok=self.grok,
            lab_data=self.lab,
            repo_root=ROOT,
        )
        self.assertGreaterEqual(stats.indexed, 4)
        self.assertTrue(self.db.is_file())
        self.assertIn("memory", stats.sources)
        self.assertIn("agents", stats.sources)
        self.assertIn("design", stats.sources)

        hits = self.query.search("zebra-widget-42", db_path=self.db)
        self.assertTrue(hits, "expected design-doc hit for unique token")
        self.assertTrue(any("DESIGN.md" in h.path for h in hits))
        self.assertTrue(any(h.source == "design" for h in hits))

        hits_mem = self.query.search("Homebrew", db_path=self.db)
        self.assertTrue(any(h.source == "memory" for h in hits_mem))

    def test_excludes_node_modules_and_git(self) -> None:
        self.index.rebuild_index(
            db_path=self.db,
            projects_root=self.projects,
            grok=self.grok,
            lab_data=self.lab,
            repo_root=ROOT,
        )
        bad = self.query.search("secret-token-xyz", db_path=self.db)
        self.assertEqual(bad, [], "node_modules content must not be indexed")
        bad_git = self.query.search("secret-git-token", db_path=self.db)
        self.assertEqual(bad_git, [], ".git content must not be indexed")

    def test_skips_oversize_files(self) -> None:
        self.index.rebuild_index(
            db_path=self.db,
            projects_root=self.projects,
            grok=self.grok,
            lab_data=self.lab,
            repo_root=ROOT,
        )
        # The huge.md body is mostly x's — unique marker still only in title line
        # but file should be skipped entirely due to size.
        # Ensure path not present via MATCH on something only in huge — hard.
        # Instead inspect documents table paths.
        import sqlite3

        conn = sqlite3.connect(str(self.db))
        paths = [r[0] for r in conn.execute("SELECT path FROM documents")]
        conn.close()
        self.assertFalse(any(p.endswith("huge.md") for p in paths))

    def test_project_scope(self) -> None:
        stats = self.index.rebuild_index(
            project="demo-app",
            db_path=self.db,
            projects_root=self.projects,
            grok=self.grok,
            lab_data=self.lab,
            repo_root=ROOT,
        )
        import sqlite3

        conn = sqlite3.connect(str(self.db))
        paths = [r[0] for r in conn.execute("SELECT path FROM documents")]
        conn.close()
        self.assertTrue(any("demo-app" in p for p in paths))
        self.assertFalse(
            any("other-proj" in p for p in paths),
            "other-proj must be excluded when --project demo-app",
        )
        # Memory still global
        self.assertTrue(any("MEMORY.md" in p for p in paths))
        self.assertGreaterEqual(stats.indexed, 2)

    def test_status(self) -> None:
        info = self.index.status(db_path=self.db)
        self.assertFalse(info["exists"])
        self.index.rebuild_index(
            db_path=self.db,
            projects_root=self.projects,
            grok=self.grok,
            lab_data=self.lab,
            repo_root=ROOT,
        )
        info2 = self.index.status(db_path=self.db)
        self.assertTrue(info2["exists"])
        self.assertGreater(info2["doc_count"], 0)
        self.assertIsNotNone(info2["indexed_at"])

    def test_missing_index_query(self) -> None:
        missing = self.tmpdir / "nope.db"
        with self.assertRaises(FileNotFoundError):
            self.query.search("anything", db_path=missing)

    def test_prepare_match_query(self) -> None:
        q = self.query.prepare_match_query("foo bar")
        self.assertEqual(q, "foo AND bar")
        q2 = self.query.prepare_match_query("")
        self.assertEqual(q2, "")

    def test_no_session_search_path(self) -> None:
        """Indexer must not create or open session_search.sqlite."""
        self.index.rebuild_index(
            db_path=self.db,
            projects_root=self.projects,
            grok=self.grok,
            lab_data=self.lab,
            repo_root=ROOT,
        )
        session_db = self.grok / "session_search.sqlite"
        self.assertFalse(session_db.exists())
        # Only fts.db under lab knowledge
        know_files = list((self.lab / "knowledge").glob("*"))
        names = {p.name for p in know_files if p.is_file()}
        self.assertIn("fts.db", names)
        self.assertNotIn("session_search.sqlite", names)


class CliDispatchTest(unittest.TestCase):
    """Smoke: cli main with temp env."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="lab-knowledge-cli."))
        self.grok = self.tmpdir / "grok"
        self.lab = self.tmpdir / "lab"
        self.projects = self.tmpdir / "Projects"
        (self.grok / "memory").mkdir(parents=True)
        (self.lab / "knowledge").mkdir(parents=True)
        self.projects.mkdir()
        (self.grok / "memory" / "MEMORY.md").write_text(
            "# mem\n\ncli-unique-token-99\n", encoding="utf-8"
        )
        self._env_backup = {
            k: os.environ.get(k)
            for k in ("GROK_HOME", "GROK_LAB_DATA", "PROJECTS", "GROK_LAB_REPO")
        }
        os.environ["GROK_HOME"] = str(self.grok)
        os.environ["GROK_LAB_DATA"] = str(self.lab)
        os.environ["PROJECTS"] = str(self.projects)
        os.environ["GROK_LAB_REPO"] = str(ROOT)
        for mod in list(sys.modules):
            if mod in ("lab_paths", "index", "query", "cli"):
                del sys.modules[mod]

    def tearDown(self) -> None:
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cli_index_query_status(self) -> None:
        import cli as knowledge_cli

        self.assertEqual(knowledge_cli.main(["index"]), 0)
        self.assertEqual(knowledge_cli.main(["status"]), 0)
        self.assertEqual(knowledge_cli.main(["query", "cli-unique-token-99"]), 0)
        self.assertEqual(knowledge_cli.main(["query"]), 2)  # missing terms


if __name__ == "__main__":
    unittest.main()

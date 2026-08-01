#!/usr/bin/env python3
# tests/test_design.py — Design Studio unit/integration tests (PR7)
"""Uses tempfile GROK_LAB_DATA / PROJECTS; no paid SaaS; stdlib only."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN_DIR = ROOT / "modules" / "design"
LIB_DIR = ROOT / "lib"
LAB = ROOT / "bin" / "lab"


def _prep_env(lab_data: Path, projects: Path) -> dict:
    env = os.environ.copy()
    env["GROK_LAB_DATA"] = str(lab_data)
    env["GROK_LAB_REPO"] = str(ROOT)
    env["GROK_HOME"] = str(lab_data.parent)
    env["PROJECTS"] = str(projects)
    # Avoid launching GUI editors during open tests
    env.pop("EDITOR", None)
    env.pop("VISUAL", None)
    return env


class DesignTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="design-test-")
        self.lab_data = Path(self._tmpdir) / "lab"
        self.lab_data.mkdir(parents=True)
        self.projects = Path(self._tmpdir) / "Projects"
        self.projects.mkdir(parents=True)
        self.project = self.projects / "demo-proj"
        self.project.mkdir()
        self.env = _prep_env(self.lab_data, self.projects)

        for p in (str(LIB_DIR), str(DESIGN_DIR.parent)):
            if p in sys.path:
                sys.path.remove(p)
            sys.path.insert(0, p)
        if str(DESIGN_DIR) in sys.path:
            sys.path.remove(str(DESIGN_DIR))

        os.environ["GROK_LAB_DATA"] = str(self.lab_data)
        os.environ["GROK_LAB_REPO"] = str(ROOT)
        os.environ["GROK_HOME"] = str(self.lab_data.parent)
        os.environ["PROJECTS"] = str(self.projects)

        for mod in list(sys.modules):
            if mod in ("lab_paths", "design") or mod.startswith("design."):
                del sys.modules[mod]

        import lab_paths  # noqa: F401
        import design.design as design_mod

        self.design = design_mod

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_doc(self, rel: str, body: str) -> Path:
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_store_creates_wal_db(self) -> None:
        store = self.design.DesignStore()
        db = self.design.get_db_path()
        self.assertTrue(db.is_file())
        self.assertEqual(db, self.lab_data / "design.db")
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
            self.assertIn("design_docs", tables)

    def test_register_copies_to_canonical_and_lists(self) -> None:
        src = self._write_doc(
            "scratch/my-spec.md",
            "# My Spec\n\nBody of the design.\n",
        )
        store = self.design.DesignStore()
        doc = store.register(src, project="demo-proj", slug="my-spec")
        self.assertEqual(doc["slug"], "my-spec")
        self.assertEqual(doc["project"], "demo-proj")
        self.assertTrue(doc.get("_copied"))
        canon = Path(doc["path"])
        self.assertTrue(canon.is_file())
        self.assertIn("docs/design/", str(canon).replace("\\", "/"))
        self.assertIn("my-spec", canon.name)
        self.assertTrue(canon.name.endswith(".md"))
        self.assertIn("# My Spec", canon.read_text(encoding="utf-8"))

        docs = store.list_docs(project="demo-proj")
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], doc["id"])

    def test_register_idempotent_same_slug(self) -> None:
        src = self._write_doc("docs/a.md", "# A\n")
        store = self.design.DesignStore()
        a = store.register(src, project="demo-proj", slug="alpha")
        b = store.register(src, project="demo-proj", slug="alpha")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(store.list_docs()), 1)

    def test_register_no_copy_pointer_only(self) -> None:
        src = self._write_doc("elsewhere/note.md", "# Note\n")
        store = self.design.DesignStore()
        doc = store.register(
            src, project="demo-proj", slug="note", copy_to_canonical=False
        )
        self.assertFalse(doc.get("_copied"))
        self.assertEqual(Path(doc["path"]).resolve(), src.resolve())

    def test_register_showroom_writes_inbox(self) -> None:
        src = self._write_doc("d.md", "# Showcase Design\n")
        store = self.design.DesignStore()
        doc = store.register(
            src, project="demo-proj", slug="showcase-design", showroom=True
        )
        self.assertIsNotNone(doc.get("showroom_capture_id"))
        inbox = self.lab_data / "showroom" / "inbox"
        files = list(inbox.glob("*.json"))
        self.assertEqual(len(files), 1)
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "design")
        self.assertEqual(payload["source"], "from-design")
        self.assertEqual(payload["project"], "demo-proj")
        self.assertFalse(payload.get("published"))
        self.assertTrue(any("docs/design" in p or p.endswith(".md") for p in payload["paths"]))

    def test_infer_project(self) -> None:
        src = self._write_doc("docs/x.md", "# X\n")
        self.assertEqual(self.design.infer_project(src), "demo-proj")
        outside = Path(self._tmpdir) / "loose.md"
        outside.write_text("# Loose\n", encoding="utf-8")
        self.assertIsNone(self.design.infer_project(outside))

    def test_cli_register_list_via_lab(self) -> None:
        src = self._write_doc("docs/via-cli.md", "# Via CLI\n")
        r = subprocess.run(
            [
                str(LAB),
                "design",
                "register",
                str(src),
                "--project",
                "demo-proj",
                "--slug",
                "via-cli",
            ],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr + r.stdout)
        self.assertIn("registered", r.stdout)

        r2 = subprocess.run(
            [str(LAB), "design", "list", "--project", "demo-proj", "--json"],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(r2.returncode, 0, msg=r2.stderr + r2.stdout)
        data = json.loads(r2.stdout)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "via-cli")

    def test_cli_help_and_lab_help(self) -> None:
        r = subprocess.run(
            [str(LAB), "design", "help"],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(r.returncode, 0)
        self.assertIn("lab design", r.stdout)

        r2 = subprocess.run(
            [str(LAB), "help"],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(r2.returncode, 0)
        self.assertIn("design", r2.stdout)

    def test_find_by_prefix_and_slug(self) -> None:
        src = self._write_doc("docs/findme.md", "# Find Me\n")
        store = self.design.DesignStore()
        doc = store.register(src, project="demo-proj", slug="findme")
        self.assertEqual(store.find(doc["id"][:10])["id"], doc["id"])
        self.assertEqual(
            store.find("findme", project="demo-proj")["id"], doc["id"]
        )

    def test_missing_path_errors(self) -> None:
        r = subprocess.run(
            [str(LAB), "design", "register", "/no/such/file.md"],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertNotEqual(r.returncode, 0)

    def test_sanitize_project_rejects_absolute_and_traversal(self) -> None:
        with self.assertRaises(self.design.ProjectNameError):
            self.design.sanitize_project_name("/tmp")
        with self.assertRaises(self.design.ProjectNameError):
            self.design.sanitize_project_name("../../OUTSIDE")
        with self.assertRaises(self.design.ProjectNameError):
            self.design.sanitize_project_name("..")
        with self.assertRaises(self.design.ProjectNameError):
            self.design.sanitize_project_name("")
        with self.assertRaises(self.design.ProjectNameError):
            self.design.sanitize_project_name("foo/bar")
        self.assertEqual(self.design.sanitize_project_name("demo-proj"), "demo-proj")

    def test_register_rejects_escaped_project(self) -> None:
        src = self._write_doc("docs/esc.md", "# Esc\n")
        store = self.design.DesignStore()
        with self.assertRaises(self.design.ProjectNameError):
            store.register(src, project="/tmp", slug="abs")
        with self.assertRaises(self.design.ProjectNameError):
            store.register(src, project="../../OUTSIDE", slug="trav")
        # Must not have written under /tmp or outside PROJECTS
        outside = Path(self._tmpdir) / "OUTSIDE" / "docs" / "design"
        self.assertFalse(outside.exists())

        r = subprocess.run(
            [
                str(LAB),
                "design",
                "register",
                str(src),
                "--project",
                "/tmp",
                "--slug",
                "abs-cli",
            ],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("project", (r.stderr + r.stdout).lower())

    def test_reregister_overwrites_canonical_content(self) -> None:
        src = self._write_doc("scratch/refresh.md", "# V1\n\nversion one\n")
        store = self.design.DesignStore()
        doc1 = store.register(src, project="demo-proj", slug="refresh")
        canon = Path(doc1["path"])
        self.assertIn("version one", canon.read_text(encoding="utf-8"))

        src.write_text("# V2\n\nversion two\n", encoding="utf-8")
        doc2 = store.register(src, project="demo-proj", slug="refresh")
        self.assertEqual(doc1["id"], doc2["id"])
        body = Path(doc2["path"]).read_text(encoding="utf-8")
        self.assertIn("version two", body)
        self.assertNotIn("version one", body)

    def test_list_rejects_negative_limit(self) -> None:
        store = self.design.DesignStore()
        with self.assertRaises(ValueError):
            store.list_docs(limit=-1)
        r = subprocess.run(
            [str(LAB), "design", "list", "--limit", "-1"],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )
        self.assertEqual(r.returncode, 2)

    def test_cli_open_prints_path_without_editor(self) -> None:
        src = self._write_doc("docs/openme.md", "# Open Me\n")
        store = self.design.DesignStore()
        doc = store.register(src, project="demo-proj", slug="openme")
        # Force print path: no EDITOR, and open/xdg-open may exist on macOS —
        # still should exit 0 and mention path or open successfully.
        env = dict(self.env)
        env["EDITOR"] = ""
        env["VISUAL"] = ""
        r = subprocess.run(
            [str(LAB), "design", "open", "openme", "--project", "demo-proj"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr + r.stdout)
        # stdout should reference the doc (open line or printed path)
        combined = r.stdout + r.stderr
        self.assertTrue(
            "openme" in combined or doc["path"] in combined or "docs/design" in combined,
            msg=combined,
        )


if __name__ == "__main__":
    unittest.main()


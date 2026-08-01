#!/usr/bin/env python3
"""Tests for model manifest schema + seal/hash."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from weights.manifest import (
    SCHEMA_VERSION,
    init_manifest,
    seal_manifest,
    validate_manifest,
    bump_semver,
    load_manifest,
    sha256_file,
)
from weights.validate import publish_check


def _write_st(path: Path) -> None:
    raw = b"\x00" * 8
    header = {
        "w": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]},
        "__metadata__": {"lab": "test"},
    }
    hb = json.dumps(header).encode("utf-8")
    pad = (8 - len(hb) % 8) % 8
    hb = hb + b" " * pad
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hb)))
        f.write(hb)
        f.write(raw)


class TestSemver(unittest.TestCase):
    def test_bump(self):
        self.assertEqual(bump_semver("1.2.3", "patch"), "1.2.4")
        self.assertEqual(bump_semver("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump_semver("1.2.3", "major"), "2.0.0")


class TestManifestLifecycle(unittest.TestCase):
    def test_init_seal_validate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_text('{"arch":"tiny"}\n')
            _write_st(root / "model.safetensors")
            m = init_manifest(
                root,
                model_id="lab.test-model",
                version="0.1.0",
                arch="tiny",
                framework="mlx",
                seal=True,
            )
            self.assertEqual(m["schema_version"], SCHEMA_VERSION)
            self.assertNotEqual(m["weights_sha256"], "0" * 64)
            expected = sha256_file(root / "model.safetensors")
            self.assertEqual(m["weights_sha256"], expected)
            r = validate_manifest(m, package_dir=root, check_hash=True)
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["hash_ok"])

    def test_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_st(root / "model.safetensors")
            m = init_manifest(root, model_id="lab.x", seal=True)
            m["weights_sha256"] = "a" * 64
            r = validate_manifest(m, package_dir=root, check_hash=True)
            self.assertFalse(r["ok"])
            self.assertTrue(any("mismatch" in i for i in r["issues"]))

    def test_publish_check_requires_manifest_strict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_text("{}\n")
            _write_st(root / "model.safetensors")
            r = publish_check(root, strict=True)
            self.assertFalse(r["ok"])
            self.assertTrue(any("manifest" in i for i in r["issues"]))
            init_manifest(root, model_id="lab.y", arch="tiny", framework="other", seal=True)
            r2 = publish_check(root, strict=True)
            self.assertTrue(r2["ok"], r2)

    def test_parent_on_bump(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_st(root / "model.safetensors")
            init_manifest(root, model_id="lab.z", seal=True)
            m = load_manifest(root)
            old = m["version"]
            m["parent_version"] = old
            m["version"] = bump_semver(old, "minor")
            from weights.manifest import save_manifest

            save_manifest(root, m)
            m2 = load_manifest(root)
            self.assertEqual(m2["parent_version"], "0.1.0")
            self.assertEqual(m2["version"], "0.2.0")


if __name__ == "__main__":
    unittest.main()

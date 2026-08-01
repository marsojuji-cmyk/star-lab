#!/usr/bin/env python3
"""Tests for safetensors layout/validate (no torch required)."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from weights.layout import is_pickle_checkpoint, package_paths, LAYOUT_DOC
from weights.validate import validate_safetensors_file, publish_check, validate_path


def _write_minimal_safetensors(path: Path, tensors: dict) -> None:
    """
    Write a minimal valid safetensors file.
    tensors: name -> (dtype_str, shape, raw_bytes)
    """
    # Build header with data_offsets
    header = {}
    offset = 0
    blobs = []
    for name, (dtype, shape, raw) in tensors.items():
        n = len(raw)
        header[name] = {
            "dtype": dtype,
            "shape": list(shape),
            "data_offsets": [offset, offset + n],
        }
        blobs.append(raw)
        offset += n
    header["__metadata__"] = {"lab": "test"}
    hbytes = json.dumps(header).encode("utf-8")
    # pad header to 8-byte alignment (optional but common)
    pad = (8 - (len(hbytes) % 8)) % 8
    hbytes = hbytes + b" " * pad
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(hbytes)))
        f.write(hbytes)
        for b in blobs:
            f.write(b)


class TestLayout(unittest.TestCase):
    def test_layout_doc(self):
        self.assertIn("model.safetensors", LAYOUT_DOC)

    def test_pickle_detect(self):
        self.assertTrue(is_pickle_checkpoint(Path("x.pt")))
        self.assertFalse(is_pickle_checkpoint(Path("x.safetensors")))


class TestValidate(unittest.TestCase):
    def test_minimal_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "model.safetensors"
            # 4 float32 zeros = 16 bytes
            raw = b"\x00" * 16
            _write_minimal_safetensors(p, {"w": ("F32", [4], raw)})
            r = validate_safetensors_file(p)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["n_tensors"], 1)
            self.assertEqual(r["tensors"][0]["name"], "w")

    def test_reject_pt(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "model.pt"
            p.write_bytes(b"not a real pickle")
            r = validate_path(p)
            self.assertFalse(r["ok"])
            self.assertEqual(r.get("kind"), "pickle")

    def test_publish_check_package(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_text('{"arch":"tiny"}\n')
            p = root / "model.safetensors"
            raw = b"\x00" * 8
            _write_minimal_safetensors(p, {"bias": ("F32", [2], raw)})
            from weights.manifest import init_manifest

            init_manifest(
                root,
                model_id="lab.test",
                arch="tiny",
                framework="other",
                seal=True,
            )
            r = publish_check(root, strict=True)
            self.assertTrue(r["ok"], r)
            # add pickle → strict fail
            (root / "old.pt").write_bytes(b"x")
            r2 = publish_check(root, strict=True)
            self.assertFalse(r2["ok"])


if __name__ == "__main__":
    unittest.main()

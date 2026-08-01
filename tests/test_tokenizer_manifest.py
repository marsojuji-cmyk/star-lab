#!/usr/bin/env python3
"""Tokenizer-major versioning tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules"))

from weights.tokenizer_manifest import (
    init_tokenizer_manifest,
    seal_tokenizer_manifest,
    validate_tokenizer_manifest,
    bump_tokenizer,
    freeze_tokenizer,
    assert_tokenizer_compatible,
    bind_tokenizer_to_model_manifest,
    hash_tokenizer_content,
)
from weights.manifest import init_manifest, validate_manifest, default_manifest


def _write_tok(dir: Path, vocab=None) -> None:
    dir.mkdir(parents=True, exist_ok=True)
    vocab = vocab or {"hello": 0, "world": 1, "<pad>": 2}
    (dir / "tokenizer.json").write_text(
        json.dumps({"model": {"vocab": vocab}, "added_tokens": []}) + "\n"
    )
    (dir / "merges.txt").write_text("h e\n")


class TestTokenizerLifecycle(unittest.TestCase):
    def test_init_seal_frozen(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_tok(root)
            m = init_tokenizer_manifest(
                root, tokenizer_id="lab.bpe", tokenizer_mode="frozen", seal=True
            )
            self.assertEqual(m["tokenizer_mode"], "frozen")
            self.assertNotEqual(m["tokenizer_hash"], "0" * 64)
            self.assertGreater(m["base_vocab_size"], 0)
            r = validate_tokenizer_manifest(m, package_dir=root)
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["hash_ok"])

    def test_content_change_requires_major(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_tok(root)
            init_tokenizer_manifest(root, tokenizer_id="lab.bpe", seal=True)
            # mutate vocab
            _write_tok(root, vocab={"hello": 0, "world": 1, "new": 3, "<pad>": 2})
            with self.assertRaises(ValueError):
                bump_tokenizer(root, "patch")
            m = bump_tokenizer(root, "major")
            self.assertEqual(m["parent_version"], "1.0.0")
            self.assertEqual(m["version"], "2.0.0")

    def test_bind_and_compatible(self):
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "tok"
            mdir = Path(td) / "model"
            mdir.mkdir()
            _write_tok(tdir)
            tm = init_tokenizer_manifest(tdir, tokenizer_id="lab.bpe", seal=True)
            # minimal weights not needed for bind fields
            mm = default_manifest(model_id="lab.head", arch="mlp", framework="mlx")
            mm = bind_tokenizer_to_model_manifest(mm, tm, tokenizer_uri="tokenizer")
            self.assertEqual(mm["tokenizer_hash"], tm["tokenizer_hash"])
            comp = assert_tokenizer_compatible(mm, tm)
            self.assertTrue(comp["ok"], comp)

    def test_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td) / "tok"
            _write_tok(tdir)
            tm = init_tokenizer_manifest(tdir, tokenizer_id="lab.bpe", seal=True)
            mm = default_manifest(model_id="lab.head")
            mm["tokenizer_id"] = "lab.bpe"
            mm["tokenizer_version"] = "1.0.0"
            mm["tokenizer_hash"] = "b" * 64
            comp = assert_tokenizer_compatible(mm, tm)
            self.assertFalse(comp["ok"])

    def test_model_manifest_requires_hash(self):
        m = default_manifest(model_id="lab.head")
        m["tokenizer_id"] = "lab.bpe"
        m["tokenizer_version"] = "1.0.0"
        # no hash
        r = validate_manifest(m, check_hash=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("tokenizer_hash" in i for i in r["issues"]))

    def test_embedding_remap_unmet_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            _write_tok(tdir)
            tm = init_tokenizer_manifest(tdir, tokenizer_id="lab.bpe", seal=True)
            mm = bind_tokenizer_to_model_manifest(
                default_manifest(model_id="lab.head"),
                tm,
                embedding_remap="required_unmet",
            )
            comp = assert_tokenizer_compatible(mm, tm)
            self.assertFalse(comp["ok"])


if __name__ == "__main__":
    unittest.main()

# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"))
import tempfile
import unittest

import rough_bundle as b


class PortableEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "original.txt"
        self.data = '原始文本\r\n```\n"quoted"\nno final newline'.encode()
        self.source.write_bytes(self.data)
        self.plan = {"account": "tester", "time": "2026-11-18T00:00:00Z", "title": "Test evidence",
                     "sources": [{"path": str(self.source), "name": "run/evidence.txt",
                                  "sha256": b.sha(self.data)}]}
        self.card = self.root / "r-tester-0001.md"

    def test_roundtrip_after_source_removed(self):
        b.pack(self.plan, self.card)
        self.source.unlink()
        b.extract([self.card], self.root / "extracted")
        self.assertEqual((self.root / "extracted/run/evidence.txt").read_bytes(), self.data)

    def test_changed_source_rejected(self):
        self.source.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            b.pack(self.plan, self.card)
        self.assertFalse(self.card.exists())

    def test_missing_card_rejected_before_extraction(self):
        b.pack(self.plan, self.card)
        with self.assertRaises(OSError):
            b.extract([self.card, self.root / "r-tester-9999.md"], self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_payload_tamper_with_rehashed_card_rejected(self):
        b.pack(self.plan, self.card)
        s = self.card.read_text().replace('no final newline', 'modified payload')
        front, body = s[4:].split('---\n', 1)
        front = '\n'.join('content_sha256: ' + b.sha(body.encode()) if line.startswith('content_sha256:') else line
                          for line in front.split('\n'))
        self.card.write_text('---\n' + front + '---\n' + body)
        with self.assertRaises(ValueError):
            b.read_cards([self.card])

    def test_unsafe_paths(self):
        for name in ("../escape", "/absolute", "a/../b", "a\\b", "a//b", "a/./b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                b.safe_name(name)

    def test_duplicate_paths_across_cards(self):
        b.pack(self.plan, self.card)
        other = self.root / "r-tester-0002.md"
        b.pack(self.plan, other)
        with self.assertRaises(ValueError):
            b.extract([self.card, other], self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_existing_output_not_overwritten(self):
        b.pack(self.plan, self.card)
        with self.assertRaises(ValueError):
            b.extract([self.card], self.root)
        self.assertEqual(self.source.read_bytes(), self.data)

    def test_secrets_rejected_without_echo(self):
        # Synthetic non-secret fixture assembled to avoid storing a redline literal.
        content = "password=" + "z" * 24
        self.source.write_text(content)
        self.plan['sources'][0]['sha256'] = b.sha(content.encode())
        with self.assertRaises(ValueError) as raised:
            b.pack(self.plan, self.card)
        self.assertNotIn(content, str(raised.exception))
        self.assertFalse(self.card.exists())

    def test_private_identifiers_in_metadata_rejected(self):
        self.plan['title'] = 'Evidence from /home/private/run'
        with self.assertRaises(ValueError):
            b.pack(self.plan, self.card)
        self.assertFalse(self.card.exists())

    def test_original_identity_must_be_a_sha(self):
        self.plan['sources'][0]['original_sha256'] = 'unverifiable'
        with self.assertRaises(ValueError):
            b.pack(self.plan, self.card)
        self.assertFalse(self.card.exists())

    def test_symlink_output_parent_rejected(self):
        b.pack(self.plan, self.card)
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            b.extract([self.card], self.root / 'link/out')


if __name__ == '__main__':
    unittest.main()

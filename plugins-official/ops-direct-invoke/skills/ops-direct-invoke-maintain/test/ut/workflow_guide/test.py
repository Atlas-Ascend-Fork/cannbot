#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Guard the guide inventory, node IDs, dependencies and task references."""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
from support import SCRIPTS, WORKFLOWS, available_workflows, run_tests


class WorkflowGuideTests(unittest.TestCase):
    def test_guide_covers_all_workflow_templates(self):
        entries = available_workflows()
        for field in ["file"]:
            values = [entry[field] for entry in entries]
            self.assertTrue(
                all(isinstance(value, str) and value.strip() for value in values)
            )
            self.assertEqual(
                len(values), len(set(values)), f"duplicate workflow {field}"
            )
        files = set()
        for path in WORKFLOWS.rglob("*"):
            if path.suffix not in {".yaml", ".yml"}:
                continue
            if path.name.endswith(".graph-preview.yaml"):
                continue
            files.add(path.relative_to(WORKFLOWS).as_posix())
        self.assertEqual(
            {entry["file"] for entry in entries},
            files,
            "missing or obsolete guide entry",
        )

    def generate_guide(self, root, output):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "generate_workflow_guide.py"),
                "--workflows-dir",
                str(root),
                "--output",
                str(output),
            ],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=60,
        )

    def read_guide(self, path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_guide_regenerates_from_nested_templates_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root, output = Path(temp) / "workflows", Path(temp) / "run/guide.csv"
            (root / "ascendc").mkdir(parents=True)
            first = root / "ascendc/first.yaml"
            original = '# template\nuse_when: "含逗号,和换行\\n的场景"\n'
            first.write_text(original, encoding="utf-8")
            result = self.generate_guide(root, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                self.read_guide(output),
                [{"file": "ascendc/first.yaml", "use_when": "含逗号,和换行\n的场景"}],
            )
            self.assertEqual(first.read_text(), original)
            second = root / "ascendc/second.yml"
            second.write_text("use_when: 新场景\n", encoding="utf-8")
            first.unlink()
            self.assertEqual(self.generate_guide(root, output).returncode, 0)
            self.assertEqual(
                self.read_guide(output),
                [{"file": "ascendc/second.yml", "use_when": "新场景"}],
            )
            second.write_text("use_when: 更新场景\n", encoding="utf-8")
            self.assertEqual(self.generate_guide(root, output).returncode, 0)
            self.assertEqual(self.read_guide(output)[0]["use_when"], "更新场景")

    def test_invalid_metadata_does_not_overwrite_previous_guide(self):
        for text in [
            "workflow: missing",
            "use_when: null",
            'use_when: "  "',
            "use_when: [bad]",
            "use_when: one\nuse_when: two",
            "use_when: [invalid",
            None,
        ]:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as temp:
                root, output = Path(temp) / "workflows", Path(temp) / "guide.csv"
                root.mkdir()
                output.write_text("previous guide", encoding="utf-8")
                if text is not None:
                    (root / "invalid.yaml").write_text(text, encoding="utf-8")
                result = self.generate_guide(root, output)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(output.read_text(), "previous guide")

    def test_guide_cannot_overwrite_shared_templates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "template.yaml"
            original = "use_when: 示例场景\n"
            template.write_text(original, encoding="utf-8")
            result = self.generate_guide(root, template)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(template.read_text(), original)


if __name__ == "__main__":
    run_tests()

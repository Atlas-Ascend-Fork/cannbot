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

"""Read-only baseline validation with Agent-owned Git fixtures, plus child assembly contracts."""

import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
from support import SCRIPTS, WORKFLOWS, run_tests  # noqa: E402
import support  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
from assemble_workflow import assemble_template, write_workflow  # noqa: E402
from review_fix import BaselineCheck, SHEETS, inventory  # noqa: E402

GIT = shutil.which("git") or "/usr/bin/git"

RUNNER = """
import argparse, csv, importlib.util
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--sheet")
p.add_argument("--device")
p.add_argument("--require-accelerator", action="store_true")
args=p.parse_args()
root=Path(__file__).parent
spec=importlib.util.spec_from_file_location("fixture_add", root.parent/"add.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with (root/"testcase.csv").open() as f:
    cases=[r for r in csv.DictReader(f) if r["sheet"]==args.sheet and r["status"]=="active"]
results=[]
for case in cases:
    passed=module.run(int(case["inputs_json"])) == int(case["inputs_json"])+1
    results.append(dict(sheet=args.sheet,case_id=case["case_id"],device=args.device,
                        status="passed" if passed else "failed",detail="arithmetic comparison"))
if getattr(module, "OMIT", False):
    results.pop()
out=root/"testcase_output"/args.sheet
out.mkdir(parents=True,exist_ok=True)
with (out/f"verify_result_{args.sheet}.csv").open("w") as f:
    writer=csv.DictWriter(f,fieldnames=["sheet","case_id","device","status","detail"])
    writer.writeheader()
    writer.writerows(results)
raise SystemExit(int(any(r["status"]!="passed" for r in results)))
"""


def write_cases(test):
    with (test / "testcase.csv").open("w") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["sheet", "case_id", "status", "inputs_json", "seed"]
        )
        writer.writeheader()
        for sheet in SHEETS:
            for index in (1, 2):
                writer.writerow(
                    dict(
                        sheet=sheet,
                        case_id=f"{sheet}-{index}",
                        status="active",
                        inputs_json=str(index),
                        seed="42",
                    )
                )


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        doc = self.work / "design/doc"
        doc.mkdir(parents=True)
        (doc / "spec.yaml").write_text("op: {name: add}\n")
        (doc / "DESIGN.md").write_text("# addition\n")
        precision = self.work / "precision"
        precision.mkdir()
        for name in ("execution.yaml", "execution.log", "precision-report.md"):
            (precision / name).write_text(
                "synthetic fixture baseline, not NPU evidence\n"
            )
        self.operator = self.work / "operators/add"
        test = self.operator / "test"
        test.mkdir(parents=True)
        self.source = self.operator / "add.py"
        self.source.write_text("def run(value):\n    return value + 1\n")
        (test / "test_add.py").write_text(RUNNER)
        (test / "add_golden.py").write_text("# frozen Golden fixture\n")
        write_cases(test)
        for sheet in SHEETS:
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(test / "test_add.py"),
                    "--sheet",
                    sheet,
                    "--device",
                    "npu",
                    "--require-accelerator",
                ],
                check=True,
            )
        self.check = BaselineCheck(self.work)

    def agent_git(self, *args):
        return subprocess.check_output(
            [
                GIT,
                f"--git-dir={self.check.root / 'git'}",
                f"--work-tree={self.operator}",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=self.operator,
        )

    def agent_commit(self, excluded=()):
        # The Agent/fixture owns all Git mutations; the production checker only reads.
        subprocess.run(
            [GIT, "init", "--bare", str(self.check.root / "git")],
            capture_output=True,
            check=True,
        )
        self.agent_git("config", "user.name", "Baseline test fixture")
        self.agent_git("config", "user.email", "fixture@example.invalid")
        self.agent_git(
            "add", "-f", "--", *sorted(set(inventory(self.operator)) - set(excluded))
        )
        self.agent_git("commit", "-m", "verified baseline fixture")
        self.agent_git("tag", "baseline")
        return self.agent_git("rev-parse", "baseline").decode().strip()

    def test_agent_created_baseline_check_is_read_only(self):
        commit = self.agent_commit()
        before = inventory(self.work)
        checked = self.check.baseline()
        self.assertEqual(checked["commit"], commit)
        self.assertEqual(checked["operator_files"], inventory(self.operator))
        self.assertEqual(inventory(self.work), before)
        self.assertFalse((self.check.root / "baseline.json").exists())

    def test_missing_baseline_is_rejected_without_initializing_git(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.check.baseline()
        self.assertFalse(self.check.root.exists())

    def test_uncommitted_source_is_rejected_without_restoring_it(self):
        self.agent_commit()
        changed = "def run(value):\n    return value + 2\n"
        self.source.write_text(changed)
        with self.assertRaisesRegex(ValueError, "baseline commit does not match"):
            self.check.baseline()
        self.assertEqual(self.source.read_text(), changed)

    def test_omitted_golden_is_rejected(self):
        self.agent_commit(excluded=["test/add_golden.py"])
        with self.assertRaisesRegex(ValueError, "baseline commit does not match"):
            self.check.baseline()

    def test_untracked_helper_is_rejected(self):
        self.agent_commit()
        (self.operator / "helper.py").write_text("# untracked fixture\n")
        with self.assertRaisesRegex(ValueError, "baseline commit does not match"):
            self.check.baseline()

    def test_changed_test_asset_is_rejected(self):
        self.agent_commit()
        (self.check.test / "add_golden.py").write_text("# changed Golden\n")
        with self.assertRaisesRegex(ValueError, "baseline commit does not match"):
            self.check.baseline()

    def test_binary_assets_are_checked_and_caches_are_excluded(self):
        (self.operator / "add.so").write_bytes(bytes(range(256)))
        cache = self.operator / "__pycache__"
        cache.mkdir()
        (cache / "cache.pyc").write_bytes(b"ignored fixture")
        self.agent_commit()
        checked = self.check.baseline()
        self.assertIn("add.so", checked["operator_files"])
        self.assertFalse(
            any(
                name.startswith(("__pycache__/", "test/testcase_output/"))
                for name in checked["operator_files"]
            )
        )
        (self.operator / "add.so").write_bytes(b"changed native fixture")
        with self.assertRaisesRegex(ValueError, "baseline commit does not match"):
            self.check.baseline()

    def test_incomplete_baseline_evidence_is_rejected(self):
        self.agent_commit()
        result = self.check.test / "testcase_output/tdd/verify_result_tdd.csv"
        result.unlink()
        with self.assertRaisesRegex(ValueError, "incomplete or failed"):
            self.check.baseline()

    def test_cpu_baseline_evidence_is_rejected(self):
        self.agent_commit()
        result = self.check.test / "testcase_output/blackbox/verify_result_blackbox.csv"
        result.write_text(result.read_text().replace(",npu,", ",cpu,"))
        with self.assertRaisesRegex(ValueError, "accelerator device"):
            self.check.baseline()

    def test_outer_git_index_is_untouched(self):
        subprocess.run([GIT, "init", "-q", str(self.work)], check=True)
        sibling = self.work / "unrelated.py"
        sibling.write_text("outer staged fixture\n")
        subprocess.run([GIT, "-C", str(self.work), "add", "unrelated.py"], check=True)
        index = (self.work / ".git/index").read_bytes()
        self.agent_commit()
        self.check.baseline()
        self.assertEqual((self.work / ".git/index").read_bytes(), index)

    def test_cli_checks_baseline_and_has_no_candidate_or_restore_actions(self):
        commit = self.agent_commit()
        before = inventory(self.work)
        command = [sys.executable, str(SCRIPTS / "review_fix.py")]
        result = subprocess.run(
            command + ["baseline", "--work-dir", str(self.work)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        import json

        self.assertEqual(json.loads(result.stdout)["commit"], commit)
        result = subprocess.run(
            command + ["attempt", "--work-dir", str(self.work)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(inventory(self.work), before)

    def test_subgraph_is_frozen_for_assembly_and_never_overwritten(self):
        source = WORKFLOWS / "cannbot-dsl/op-dev.yaml"
        children = {}
        definition = assemble_template(source, children)
        output = self.work / "workflow.yaml"
        write_workflow(definition, output, children)
        child = self.work / "review-fix/workflow.yaml"
        before = child.read_bytes()
        frozen_graph = yaml.safe_load(before)
        self.assertEqual(set(frozen_graph), {"nodes"})
        nodes = frozen_graph["nodes"]
        self.assertEqual([node["id"] for node in nodes], ["baseline", "review", "fix"])
        self.assertTrue(all("yaml" not in node for node in nodes))
        self.assertEqual(nodes[-1]["max_retries"], 1)
        with self.assertRaises(FileExistsError):
            write_workflow(definition, output, children)
        self.assertEqual(child.read_bytes(), before)

    def test_child_uses_standard_assembly_interface(self):
        child = assemble_template(WORKFLOWS / "cannbot-dsl/review-fix.yaml")
        self.assertNotIn("use_when", child)
        self.assertTrue(
            all("yaml" not in node and node["goal"] for node in child["nodes"])
        )
        output = self.work / "child.yaml"
        write_workflow(child, output)
        self.assertEqual(yaml.safe_load(output.read_text()), child)

    def test_frozen_child_is_accepted_by_public_harness_cli(self):
        graph = {
            "workflow": "review-fix-fixture",
            "max_parallel": 1,
            "nodes": [
                {
                    "id": "review-fix",
                    "task_type": "subgraph",
                    "file": "review-fix/workflow.yaml",
                    "depends_on": [],
                }
            ],
        }
        children = {
            Path("review-fix/workflow.yaml"): {
                "nodes": assemble_template(WORKFLOWS / "cannbot-dsl/review-fix.yaml")[
                    "nodes"
                ]
            }
        }
        output = self.work / "workflow.yaml"
        write_workflow(graph, output, children)
        child = self.work / "review-fix/workflow.yaml"
        before = child.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_workflow.py"),
                "--yaml",
                str(output),
                "--work-dir",
                str(self.work),
                "--provider",
                "codex",
                "--prompt",
                "UT simulation only",
                "--harness-skill",
                str(support.HARNESS_SKILL),
                "--foreground",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(child.read_bytes(), before)

    def test_main_publish_failure_can_resume_without_overwriting_child(self):
        children = {}
        definition = assemble_template(WORKFLOWS / "cannbot-dsl/op-dev.yaml", children)
        output = self.work / "workflow.yaml"
        import os

        link = os.link

        def interrupt_main(source, target):
            if target == output:
                raise OSError("simulated main publication failure")
            return link(source, target)

        with patch("assemble_workflow.os.link", side_effect=interrupt_main):
            with self.assertRaises(OSError):
                write_workflow(definition, output, children)
        self.assertFalse(output.exists())
        child = self.work / "review-fix/workflow.yaml"
        frozen = child.read_bytes()
        write_workflow(definition, output, children)
        self.assertEqual(child.read_bytes(), frozen)
        self.assertEqual(yaml.safe_load(output.read_text()), definition)
        self.assertFalse(list(self.work.rglob(".workflow-*")))

    def test_conflicting_child_is_preserved_and_blocks_main(self):
        children = {}
        definition = assemble_template(WORKFLOWS / "cannbot-dsl/op-dev.yaml", children)
        child = self.work / "review-fix/workflow.yaml"
        child.parent.mkdir()
        child.write_text("nodes: []\n")
        output = self.work / "workflow.yaml"
        with self.assertRaises(FileExistsError):
            write_workflow(definition, output, children)
        self.assertEqual(child.read_text(), "nodes: []\n")
        self.assertFalse(output.exists())


if __name__ == "__main__":
    run_tests()

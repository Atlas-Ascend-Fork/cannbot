# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Exercise the DSL inventory and the installed optimization request boundary."""

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from support import SCRIPTS, run_tests

spec = importlib.util.spec_from_file_location(
    "perf_adapter", SCRIPTS / "prepare_dsl_performance.py"
)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
REPO = SCRIPTS.parents[4]
PERF = REPO / "plugins-official/ops-perf-optimize/skills/ops-perf-optimize-workflow"


class InventoryTests(unittest.TestCase):
    def candidate_arguments(self, root):
        args = [
            sys.executable,
            str(SCRIPTS / "run_dsl_performance_case.py"),
            "--candidate-root",
            str(root),
            "--execution-map",
            str(self.work / "perf-optimize/inputs/execution-map.json"),
            "--case-id",
            "blackbox",
            "--entry",
            "operators.reduce_sum.reduce_sum:run",
            "--device",
            "npu",
        ]
        return args

    def check_request_freeze(self, request, args):
        # Synthetic package identity exercises the real freeze API without an NPU.
        package = self.tests / "cannbotdsl_case_contract.py"
        environment = {
            "schema_version": 1,
            "dsl_version": "unit-test-fixture",
            "package_files": [
                {
                    "path": str(package.resolve()),
                    "sha256": adapter.sha(package.read_bytes()),
                }
            ],
        }
        (request.parent / "dsl-environment.json").write_text(
            json.dumps(environment), encoding="utf-8"
        )
        output = request.parent / "run"
        result = subprocess.run(
            args + ["freeze", "--request", str(request), "--output-dir", str(output)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(
            (output / "run-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["collections"]["functional_full"]["count"], 3)
        self.assertEqual(manifest["collections"]["performance_full"]["count"], 3)
        frozen = Path(manifest["collections"]["functional_full"]["case_manifest"])
        self.assertEqual(
            (frozen.parent / "testcase.csv").read_bytes(),
            (self.tests / "testcase.csv").read_bytes(),
        )

    def request_arguments(self, request):
        create = [
            "create-request",
            "--request",
            str(request),
            "--operator-name",
            "reduce_sum",
            "--code-dir",
            str(self.tests.parent),
            "--backend",
            "cannbot_dsl",
            "--dsl-repo-root",
            str(self.work),
            "--dsl-entrypoint",
            "operators.reduce_sum.reduce_sum:run",
            "--dsl-execution-mode",
            "jit",
            "--target-soc",
            "Ascend950",
            "--functional-mode",
            "existing",
            "--functional-cases",
            str(request.parent / "inputs/functional"),
            "--performance-cases",
            str(request.parent / "inputs/performance.csv"),
            "--cann-env-command",
            "inherit",
            "--confirmed-by",
            "unit-test-fixture",
        ]
        return create

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        design = self.work / "design/doc"
        design.mkdir(parents=True)
        (design / "spec.yaml").write_text("op:\n  name: reduce_sum\n", encoding="utf-8")
        self.tests = self.work / "operators/reduce_sum/test"
        self.tests.mkdir(parents=True)
        for name in (
            "test_reduce_sum.py",
            "reduce_sum_golden.py",
            "cannbotdsl_case_contract.py",
        ):
            (self.tests / name).write_text("# frozen test asset\n", encoding="utf-8")
        self.rows = [
            dict(
                sheet=sheet,
                case_id=sheet,
                status="active",
                expected="match_golden",
                seed="41",
                inputs_json='{"x":{"shape":[17]}}',
                assertions_json='[{"kind":"execution","repeat":2}]',
            )
            for sheet in ("blackbox", "whitebox", "tdd")
        ]
        self.write_rows()

    def write_rows(self):
        with (self.tests / "testcase.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)

    def test_frozen_assets_and_sequence_preserved_and_retry_idempotent(self):
        original = (self.tests / "testcase.csv").read_bytes()
        first = adapter.prepare(self.work)
        self.assertEqual(first, adapter.prepare(self.work))
        copied = self.work / "perf-optimize/inputs/functional/testcase.csv"
        self.assertEqual(copied.read_bytes(), original)
        with (copied.parent / "cases.csv").open(encoding="utf-8") as stream:
            cases = list(csv.DictReader(stream))
        self.assertEqual(cases[0]["assertions_json"], self.rows[0]["assertions_json"])
        self.assertEqual(
            first["cases"][0]["arguments"][:4],
            ["--sheet", "blackbox", "--case-id", "blackbox"],
        )

    def test_separate_code_root_preserves_workflow_and_freezes_actual_tests(self):
        code = self.work / "code"
        code.mkdir()
        shutil.move(str(self.work / "operators"), str(code / "operators"))
        self.tests = code / "operators/reduce_sum/test"
        mapping = adapter.prepare(self.work, code)
        self.assertEqual(Path(mapping["casebook"]["path"]), self.tests / "testcase.csv")
        self.assertTrue(
            (self.work / "perf-optimize/inputs/execution-map.json").is_file()
        )
        self.assertFalse((code / "perf-optimize").exists())
        self.assertEqual(mapping, adapter.prepare(self.work, code))
        self.rows[0]["seed"] = "99"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "stale"):
            adapter.prepare(self.work, code)

    def test_error_checks_retained_but_not_timed(self):
        self.rows[0]["expected"] = "raises_error:BAD_SHAPE"
        self.write_rows()
        adapter.prepare(self.work)
        folder = self.work / "perf-optimize/inputs"
        with (folder / "performance.csv").open(encoding="utf-8") as stream:
            perf = list(csv.DictReader(stream))
        self.assertEqual({row["case_id"] for row in perf}, {"whitebox", "tdd"})
        with (folder / "functional/cases.csv").open(encoding="utf-8") as stream:
            functional = list(csv.DictReader(stream))
        self.assertEqual(functional[0]["expected_error"], "")
        self.assertEqual(functional[0]["execution_kind"], "host_only")
        self.assertEqual(
            functional[0]["host_assertion"], "original_runner:raises_error:BAD_SHAPE"
        )

    def test_changed_input_rejected_without_overwriting_snapshot(self):
        adapter.prepare(self.work)
        path = self.work / "perf-optimize/inputs/execution-map.json"
        frozen = path.read_bytes()
        self.rows[0]["seed"] = "43"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "stale"):
            adapter.prepare(self.work)
        self.assertEqual(path.read_bytes(), frozen)

    def test_missing_group_duplicate_and_unknown_semantics_rejected(self):
        for change in ("group", "duplicate", "semantics"):
            with self.subTest(change=change):
                rows = [dict(row) for row in self.rows]
                if change == "group":
                    rows[-1]["status"] = "excluded"
                elif change == "duplicate":
                    rows[-1]["case_id"] = rows[0]["case_id"]
                else:
                    rows[-1]["expected"] = "arbitrary_success"
                original = self.rows
                self.rows = rows
                self.write_rows()
                with self.assertRaises(ValueError):
                    adapter.prepare(self.work)
                self.rows = original

    def test_real_request_creator_and_validator_accept_adapter_inventory(self):
        adapter.prepare(self.work)
        request = self.work / "perf-optimize/optimization-request.json"
        args = [sys.executable, str(PERF / "scripts/prepare_case_sets.py")]
        create = self.request_arguments(request)
        result = subprocess.run(
            args + create, capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            args + ["validate-request", "--request", str(request)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.check_request_freeze(request, args)
        performance = request.parent / "inputs/performance.csv"
        performance.write_text(
            performance.read_text(encoding="utf-8").replace(
                ",device,", ",host_only,", 1
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            args
            + [
                "freeze",
                "--request",
                str(request),
                "--output-dir",
                str(request.parent / "invalid-run"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must contain device cases", result.stdout + result.stderr)
        data = json.loads(request.read_text(encoding="utf-8"))
        data["confirmation"]["status"] = "pending"
        request.write_text(json.dumps(data), encoding="utf-8")
        result = subprocess.run(
            args + ["validate-request", "--request", str(request)], capture_output=True
        )
        self.assertNotEqual(result.returncode, 0)

    def test_candidate_runner_ignores_original_pythonpath_and_rejects_changed_tests(
        self,
    ):
        (self.tests / "test_reduce_sum.py").write_text(
            "import os,importlib\n"
            "assert importlib.import_module(os.environ['CANNBOTDSL_OP_MODULE']).run() == 'candidate'\n",
            encoding="utf-8",
        )
        adapter.prepare(self.work)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "operators/reduce_sum"
            candidate.mkdir(parents=True)
            (candidate / "reduce_sum.py").write_text(
                "def run(): return 'candidate'\n", encoding="utf-8"
            )
            (self.tests.parent / "reduce_sum.py").write_text(
                "def run(): return 'original'\n", encoding="utf-8"
            )
            shutil.copytree(self.tests, candidate / "test")
            args = self.candidate_arguments(root)
            env = {**os.environ, "PYTHONPATH": str(self.work)}
            result = subprocess.run(
                args, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            wrong = list(args)
            wrong[wrong.index("--entry") + 1] = "original.reduce_sum:run"
            result = subprocess.run(
                wrong, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("frozen operator identity", result.stderr)
            result = subprocess.run(
                args + ["--error-matcher", "json"],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("matcher import escaped", result.stderr)
            (candidate / "test/reduce_sum_golden.py").write_text(
                "# modified\n", encoding="utf-8"
            )
            result = subprocess.run(
                args, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("changed frozen", result.stderr)

    def test_assembled_child_and_registered_role(self):
        script = SCRIPTS / "assemble_workflow.py"
        output = self.work / "workflow.yaml"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--template",
                str(SCRIPTS.parent / "workflows/cannbot-dsl/op-dev.yaml"),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        graph = yaml.safe_load(output.read_text(encoding="utf-8"))
        node = next(n for n in graph["nodes"] if n["id"] == "performance")
        child = yaml.safe_load((self.work / node["file"]).read_text(encoding="utf-8"))
        executor = child["nodes"][0]["executor"]
        self.assertTrue((SCRIPTS.parents[2] / "agents" / (executor + ".md")).is_file())


if __name__ == "__main__":
    run_tests()

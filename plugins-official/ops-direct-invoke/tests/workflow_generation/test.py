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

"""Regression tests for our task assembly, references and input validation."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "helpers"))
from support import HARNESS_SKILL, SCRIPTS, load_yaml, run_tests, task_fixture


class WorkflowGenerationTests(unittest.TestCase):
    def write_content_task_fixture(self, folder):
        content = {
            key: value
            for key, value in task_fixture().items()
            if key not in {"task_type", "executor", "verifier", "on_exhaust"}
        }
        content["goal"] = ["CONTENT_SENTINEL"]
        content["context"] = {
            "execute": {"skills": ["ops-direct-invoke-engineering"]},
            "verify": {"skills": [], "resources": {"report": "$WORK_DIR/report"}},
        }
        node = {
            "id": "semantic-id",
            "task_type": "normal",
            "yaml": "task.yaml",
            "depends_on": [],
            "executor": "ops-direct-invoke-developer",
            "verifier": "ops-direct-invoke-verifier",
            "max_retries": 2,
            "on_exhaust": "exit",
        }
        (folder / "task.yaml").write_text(yaml.safe_dump(content))
        definition = {
            "workflow": "fixture",
            "use_when": "test",
            "max_parallel": 1,
            "nodes": [node],
        }
        (folder / "template.yaml").write_text(yaml.safe_dump(definition))
        return content, node

    def test_content_task_merge_preserves_content_and_scheduling(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            content, node = self.write_content_task_fixture(folder)
            source, output = folder / "template.yaml", folder / "output.yaml"
            command = [
                sys.executable,
                str(SCRIPTS / "assemble_workflow.py"),
                "--template",
                str(source),
                "--output",
                str(output),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = {
                **{key: value for key, value in content.items() if key != "context"},
                **{key: value for key, value in node.items() if key != "yaml"},
            }
            self.assertEqual(load_yaml(output)["nodes"], [expected])
            contexts = Path(str(output) + ".contexts.yaml")
            self.assertEqual(load_yaml(contexts), {"semantic-id": content["context"]})
            frozen = output.read_bytes()
            frozen_contexts = contexts.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), frozen)
            self.assertEqual(contexts.read_bytes(), frozen_contexts)

    def test_reference_task_context_is_preserved_and_invalid_phases_rejected(self):
        context = {
            "execute": {"skills": ["ops-direct-invoke-engineering"]},
            "verify": {"skills": ["ops-direct-invoke-repo-guide"]},
        }
        for value, valid in ((context, True), ([], False), ({"verify": []}, False),
                             ({"unknown": {}}, False)):
            with self.subTest(context=value), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                task = folder / "task.yaml"
                task.write_text(yaml.safe_dump({**task_fixture(), "context": value}))
                output = folder / "workflow.yaml"
                result = self.assemble_report_tasks(output, {"task": task}, ["task"], [])
                self.assertEqual(result.returncode, 0 if valid else 2, result.stderr)
                if valid:
                    self.assertNotIn("context", load_yaml(output)["nodes"][0])
                    self.assertEqual(
                        load_yaml(Path(str(output) + ".contexts.yaml")), {"0": context}
                    )
                else:
                    self.assertFalse(output.exists())
                    self.assertFalse(Path(str(output) + ".contexts.yaml").exists())

    def write_report_tasks(self, folder):
        base = task_fixture()
        files = {}
        for title in ["producer", "other", "consumer"]:
            task = {
                **base,
                "title": title,
                "approach": [
                    "write $WORK_DIR/{{id}}-report.md; template templates/report.md"
                ],
                "procedure": ["verify $WORK_DIR/{{id}}-report.md"],
                "acceptance": ['test -s "$WORK_DIR/{{id}}-report.md"'],
            }
            if title == "consumer":
                task["approach"].append("read $WORK_DIR/{{id:producer}}-report.md")
            path = folder / f"{title}.yaml"
            path.write_text(yaml.safe_dump(task), encoding="utf-8")
            files[title] = path
        return files

    def assemble_report_tasks(self, output, files, titles, dependencies):
        args = [
            sys.executable,
            str(SCRIPTS / "assemble_workflow.py"),
            "--max-retries",
            "1",
            "--output",
            str(output),
        ]
        for dependency in dependencies:
            args.extend(["--depends-on", dependency])
        paths = [files.get(title) for title in titles]
        self.assertNotIn(None, paths, "unknown report task fixture")
        return subprocess.run(
            args + list(map(str, paths)), capture_output=True, text=True, timeout=60
        )

    def assert_report_paths(self, node, identifier):
        self.assertEqual(
            node["approach"][0],
            f"write $WORK_DIR/{identifier}-report.md; template templates/report.md",
        )
        self.assertEqual(
            node["procedure"], [f"verify $WORK_DIR/{identifier}-report.md"]
        )
        self.assertEqual(
            node["acceptance"], [f'test -s "$WORK_DIR/{identifier}-report.md"']
        )

    def assert_report_workflow(self, nodes, ids, producer):
        self.assertEqual([node["id"] for node in nodes], ids)
        for node, identifier in zip(nodes, ids):
            self.assert_report_paths(node, identifier)
        consumer = next(node for node in nodes if node["title"] == "consumer")
        self.assertEqual(
            consumer["approach"][1], f"read $WORK_DIR/{producer}-report.md"
        )

    def test_report_paths_follow_ids_and_upstream_producer(self):
        with tempfile.TemporaryDirectory(prefix="workflow-report-ut-") as temp:
            folder = Path(temp)
            files = self.write_report_tasks(folder)
            before = {p: p.read_bytes() for p in files.values()}
            cases = [
                ("serial", ["producer", "consumer"], [], ["0", "1"], "0"),
                (
                    "reordered",
                    ["consumer", "other", "producer"],
                    ["1:3", "2:", "3:"],
                    ["1", "0.0", "0.1"],
                    "0.1",
                ),
                (
                    "repeated",
                    ["producer", "producer", "consumer"],
                    [],
                    ["0", "1", "2"],
                    "1",
                ),
            ]
            for name, titles, dependencies, ids, producer in cases:
                with self.subTest(case=name):
                    output = folder / f"{name}.yaml"
                    result = self.assemble_report_tasks(
                        output, files, titles, dependencies
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    nodes = load_yaml(output)["nodes"]
                    self.assert_report_workflow(nodes, ids, producer)
                    self.assertNotIn("{{id", output.read_text())
            for name, titles, dependencies in [
                ("missing", ["consumer"], []),
                ("not_upstream", ["producer", "consumer"], ["2:"]),
                ("ambiguous", ["producer", "producer", "consumer"], ["2:", "3:1,2"]),
            ]:
                with self.subTest(case=name):
                    output = folder / f"{name}.yaml"
                    result = self.assemble_report_tasks(
                        output, files, titles, dependencies
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("report producer", result.stderr)
                    self.assertFalse(output.exists())
            for path, contents in before.items():
                self.assertEqual(path.read_bytes(), contents)

    def test_unsafe_tags_and_invalid_mapping_keys_are_rejected(self):
        cases = [
            ("duplicate", "workflow: first\nworkflow: second\n", "duplicate YAML key"),
            ("nested_duplicate", "nodes:\n- id: a\n  id: b\n", "duplicate YAML key"),
            ("non_string_key", "1: value\n", "non-string"),
            (
                "python_tag",
                "!!python/object/apply:builtins.str [unsafe]\n",
                "constructor",
            ),
        ]
        for name, payload, message in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "input.yaml"
                source.write_text(payload, encoding="utf-8")
                with self.assertRaises((ValueError, yaml.YAMLError)):
                    load_yaml(source)
                self.assert_assembler_rejects_yaml(source, message)

    def assert_assembler_rejects_yaml(self, source, message):
        for mode in [[], ["--template"]]:
            with self.subTest(mode=mode):
                output = source.parent / "workflow.yaml"
                options = mode or ["--max-retries", "1"]
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "assemble_workflow.py"),
                        *options,
                        str(source),
                        "--output",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)
                self.assertFalse(output.exists())

    def test_template_retries_and_latest_task_content_are_used(self):
        source = task_fixture()
        with tempfile.TemporaryDirectory(prefix="workflow-ut-") as temp:
            folder = Path(temp)
            task = folder / "task.yaml"
            task.write_text(yaml.safe_dump({**source, "goal": ["LATEST_TASK_CONTENT"]}))
            reference = {
                "workflow": "custom",
                "max_parallel": 3,
                "nodes": [
                    {
                        "id": "0",
                        "yaml": "task.yaml",
                        "depends_on": [],
                        "max_retries": 0,
                    },
                    {
                        "id": "1",
                        "yaml": "task.yaml",
                        "depends_on": ["0"],
                        "max_retries": 4,
                    },
                ],
            }
            template = folder / "reference.yaml"
            template.write_text(yaml.safe_dump(reference))
            output = folder / "workflow.yaml"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "assemble_workflow.py"),
                    "--template",
                    str(template),
                    "--output",
                    str(output),
                ],
                cwd="/",
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            definition = load_yaml(output)
            self.assertEqual(definition["workflow"], "custom")
            self.assertEqual(definition["max_parallel"], 3)
            self.assertEqual(
                [node["max_retries"] for node in definition["nodes"]], [0, 4]
            )
            self.assertTrue(
                all(
                    node["goal"] == ["LATEST_TASK_CONTENT"]
                    for node in definition["nodes"]
                )
            )
            self.assertNotIn("max_retries", load_yaml(task))

    def test_invalid_reference_graphs_are_rejected_without_output(self):
        base = {
            "workflow": "fixture",
            "use_when": "test assembly",
            "max_parallel": 2,
            "nodes": [
                {"id": "0.0", "yaml": "task.yaml", "depends_on": [], "max_retries": 1},
                {"id": "0.1", "yaml": "task.yaml", "depends_on": [], "max_retries": 1},
                {
                    "id": "1",
                    "yaml": "task.yaml",
                    "depends_on": ["0.0", "0.1"],
                    "max_retries": 1,
                },
            ],
        }
        mutations = [
            *[
                (
                    f"use_when_{value!r}",
                    lambda graph, value=value: graph.update(use_when=value),
                )
                for value in ["", None, [], 1]
            ],
            ("missing_retry", lambda graph: graph["nodes"][0].pop("max_retries")),
            *[
                (
                    f"retry_{value!r}",
                    lambda graph, value=value: graph["nodes"][0].update(
                        max_retries=value
                    ),
                )
                for value in [-1, True, 1.5, "1", None, []]
            ],
            (
                "unknown_dependency",
                lambda graph: graph["nodes"][2].update(depends_on=["missing"]),
            ),
            (
                "duplicate_dependency",
                lambda graph: graph["nodes"][2].update(depends_on=["0.0", "0.0"]),
            ),
            ("cycle", lambda graph: graph["nodes"][0].update(depends_on=["1"])),
            ("duplicate_id", lambda graph: graph["nodes"][1].update(id="0.0")),
            ("wrong_id", lambda graph: graph["nodes"][-1].update(id="99")),
            (
                "task_missing",
                lambda graph: graph["nodes"][0].update(yaml="missing.yaml"),
            ),
            (
                "inline_task",
                lambda graph: graph["nodes"][0].update(goal=["invalid inline content"]),
            ),
        ]
        for name, mutate in mutations:
            with (
                self.subTest(case=name),
                tempfile.TemporaryDirectory(prefix="workflow-invalid-") as temp,
            ):
                graph = json.loads(json.dumps(base))
                mutate(graph)
                template, output = (
                    Path(temp) / "reference.yaml",
                    Path(temp) / "workflow.yaml",
                )
                (Path(temp) / "task.yaml").write_text(yaml.safe_dump(task_fixture()))
                template.write_text(yaml.safe_dump(graph))
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "assemble_workflow.py"),
                        "--template",
                        str(template),
                        "--output",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(output.exists())

    def test_positional_tasks_require_dispatch_retry_budget(self):
        source = task_fixture()
        for budget, inline_retry, valid in [
            (None, False, False),
            ("-1", False, False),
            ("2", True, False),
            ("2", False, True),
        ]:
            with (
                self.subTest(budget=budget, inline=inline_retry),
                tempfile.TemporaryDirectory() as temp,
            ):
                task = {**source}
                if inline_retry:
                    task["max_retries"] = 1
                path, output = Path(temp) / "task.yaml", Path(temp) / "out.yaml"
                path.write_text(yaml.safe_dump(task))
                args = [
                    sys.executable,
                    str(SCRIPTS / "assemble_workflow.py"),
                    str(path),
                    "--output",
                    str(output),
                ]
                if budget is not None:
                    args += ["--max-retries", budget]
                result = subprocess.run(
                    args, capture_output=True, text=True, timeout=60
                )
                self.assertEqual(result.returncode, 0 if valid else 2, result.stderr)
                if valid:
                    self.assertEqual(load_yaml(output)["nodes"][0]["max_retries"], 2)
                else:
                    self.assertFalse(output.exists())

    def test_optional_procedure_is_preserved_or_rejected_when_invalid(self):
        source = task_fixture()
        for present, value, valid in [
            (False, None, True),
            (True, ["VERIFY_ONLY_SENTINEL"], True),
            (True, [], False),
            (True, None, False),
            (True, "check", False),
            (True, [""], False),
            (True, ["   "], False),
            (True, [1], False),
            (True, {}, False),
        ]:
            with (
                self.subTest(present=present, value=value),
                tempfile.TemporaryDirectory(prefix="workflow-ut-") as temp,
            ):
                task = {key: item for key, item in source.items() if key != "procedure"}
                if present:
                    task["procedure"] = value
                task_path, output = (
                    Path(temp) / "task.yaml",
                    Path(temp) / "workflow.yaml",
                )
                task_path.write_text(
                    yaml.safe_dump(task, allow_unicode=True), encoding="utf-8"
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "assemble_workflow.py"),
                        "--max-retries",
                        "1",
                        str(task_path),
                        "--output",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(
                    result.returncode, 0 if valid else 2, result.stdout + result.stderr
                )
                self.assert_procedure_result(result, output, present, value, valid)

    def assert_procedure_result(self, result, output, present, value, valid):
        if valid:
            workflow = load_yaml(output)
            node = workflow["nodes"][0]
            self.assertEqual("procedure" in node, present)
            if present:
                self.assertEqual(node["procedure"], value)
                self.assertNotIn(value[0], node["approach"] + node["acceptance"])
        else:
            self.assertIn("procedure", result.stderr)
            self.assertFalse(output.exists())


class StaticSubgraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "work/main.yaml"
        node = {**task_fixture(), "id": "work", "depends_on": [], "max_retries": 0}
        self.child = {
            "use_when": "test",
            "workflow": "child",
            "max_parallel": 1,
            "nodes": [node],
        }
        self.write("child.yaml", self.child)

    def write(self, name, definition):
        (self.source / name).write_text(yaml.safe_dump(definition))

    def assemble(self, nodes):
        self.write(
            "parent.yaml",
            {
                "use_when": "test",
                "workflow": "fixture",
                "max_parallel": 1,
                "nodes": nodes,
            },
        )
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "assemble_workflow.py"),
                "--template",
                str(self.source / "parent.yaml"),
                "--output",
                str(self.output),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_arbitrary_names_and_dynamic_child_remain_independent(self):
        fixed = {
            "id": "arbitrary-stage",
            "task_type": "subgraph",
            "template": "child.yaml",
            "file": "renamed/frozen.yaml",
            "depends_on": [],
        }
        dynamic = {
            "id": "runtime-stage",
            "task_type": "subgraph",
            "file": "runtime/generated.yaml",
            "depends_on": ["arbitrary-stage"],
        }
        result = self.assemble([fixed, dynamic])
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = {key: value for key, value in fixed.items() if key != "template"}
        self.assertEqual(load_yaml(self.output)["nodes"], [expected, dynamic])
        self.assertEqual(
            load_yaml(self.output.parent / fixed["file"]),
            {"nodes": self.child["nodes"]},
        )
        self.assertFalse((self.output.parent / "runtime").exists())

    def test_nested_static_templates_use_work_directory_destinations(self):
        nested = {
            "id": "nested",
            "task_type": "subgraph",
            "template": "leaf.yaml",
            "file": "leaves/frozen.yaml",
            "depends_on": ["work"],
        }
        self.write("leaf.yaml", self.child)
        self.write(
            "child.yaml", {**self.child, "nodes": [*self.child["nodes"], nested]}
        )
        result = self.assemble(
            [
                {
                    "id": "outer",
                    "task_type": "subgraph",
                    "template": "child.yaml",
                    "file": "outer/child.yaml",
                    "depends_on": [],
                }
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            load_yaml(self.output.parent / "leaves/frozen.yaml"),
            {"nodes": self.child["nodes"]},
        )
        child = load_yaml(self.output.parent / "outer/child.yaml")
        self.assertNotIn("template", child["nodes"][-1])
        self.assertEqual(child["nodes"][-1]["file"], "leaves/frozen.yaml")

    def test_invalid_templates_publish_no_files(self):
        fixed = {
            "id": "fixed",
            "task_type": "subgraph",
            "template": "child.yaml",
            "file": "fixed.yaml",
            "depends_on": [],
        }
        for change in (
            {"template": "missing.yaml"},
            {"template": "parent.yaml"},
            {"file": "../escape.yaml"},
            {"task_type": "normal"},
            {"file": "main.yaml"},
            {"file": "main.yaml.contexts.yaml"},
            {"file": "fixed.yaml.contexts.yaml"},
        ):
            with self.subTest(change=change):
                result = self.assemble([fixed, {**fixed, "id": "invalid", **change}])
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.parent.exists(), result.stderr)

    def test_conflicting_static_destinations_publish_no_files(self):
        self.write(
            "other.yaml",
            {**self.child, "nodes": [{**self.child["nodes"][0], "id": "other"}]},
        )
        nodes = [
            {
                "id": name,
                "task_type": "subgraph",
                "template": source,
                "file": "shared.yaml",
                "depends_on": [],
            }
            for name, source in (("first", "child.yaml"), ("second", "other.yaml"))
        ]
        result = self.assemble(nodes)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting static subgraph", result.stderr)
        self.assertFalse(self.output.parent.exists())

    def test_template_launcher_publishes_children_for_public_harness_cli(self):
        context = {"execute": {"skills": []}, "verify": {"skills": []}}
        self.child["nodes"][0]["context"] = context
        self.write("child.yaml", self.child)
        node = {
            "id": "arbitrary-stage",
            "task_type": "subgraph",
            "template": "child.yaml",
            "file": "renamed/frozen.yaml",
            "depends_on": [],
        }
        result = self.assemble([node])
        self.assertEqual(result.returncode, 0, result.stderr)
        work = self.root / "launch"
        scripts = self.root / "plugin/tools"
        shutil.copytree(SCRIPTS, scripts, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(self.source, scripts.parent / "orchestrations/workflows")
        result = subprocess.run(
            [
                sys.executable,
                str(scripts / "run_workflow.py"),
                "--template",
                "parent.yaml",
                "--work-dir",
                str(work),
                "--harness-skill",
                str(HARNESS_SKILL),
                "--provider",
                "codex",
                "--prompt",
                "UT simulation only",
                "--foreground",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("template", load_yaml(work / "launch.yaml")["nodes"][0])
        child = load_yaml(work / node["file"])
        self.assertNotIn("context", child["nodes"][0])
        self.assertEqual(
            load_yaml(Path(str(work / node["file"]) + ".contexts.yaml")),
            {"work": context},
        )

    def test_context_files_are_reused_only_when_identical(self):
        context = {"execute": {"skills": ["ops-direct-invoke-engineering"]}}
        self.child["nodes"][0]["context"] = context
        self.write("child.yaml", self.child)
        node = {
            "id": "child",
            "task_type": "subgraph",
            "template": "child.yaml",
            "file": "child.yaml",
            "depends_on": [],
        }
        result = self.assemble([node])
        self.assertEqual(result.returncode, 0, result.stderr)
        child = self.output.parent / "child.yaml"
        contexts = Path(str(child) + ".contexts.yaml")
        self.assertEqual(load_yaml(contexts), {"work": context})
        frozen = contexts.read_bytes()
        self.output.unlink()
        child.unlink()  # Interrupted publication left bindings, but no child graph.
        result = self.assemble([node])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("context", load_yaml(child)["nodes"][0])
        self.output.unlink()
        self.child["nodes"][0]["context"]["execute"]["skills"] = []
        self.write("child.yaml", self.child)
        result = self.assemble([node])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(contexts.read_bytes(), frozen)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    run_tests()

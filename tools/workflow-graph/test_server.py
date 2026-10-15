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
"""子图真实文件、规划预览、监听和只读边界回归。"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

SPEC = importlib.util.spec_from_file_location(
    "workflow_graph_server", Path(__file__).with_name("server.py")
)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class SubgraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workflow = self.root / "main.yaml"
        self.write(
            "main.yaml",
            {"nodes": [{"id": "loop", "task_type": "subgraph", "file": "child.yaml"}]},
        )
        self.write(
            "main.graph-preview.yaml",
            {
                "subgraphs": {
                    "loop": {
                        "title": "规划",
                        "stages": [{"title": "stage", "description": "规划阶段"}],
                        "nodes": [
                            {"id": "placeholder", "title": "占位", "goal": ["规划"]}
                        ],
                    }
                }
            },
        )

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return path

    def child(self):
        return server.build_graph(self.workflow)["nodes"][0]["subgraph"]["graph"]

    def test_planning_and_real_file_priority(self):
        self.assertEqual(self.child()["view_kind"], "planned")
        self.write(
            "child.yaml",
            {
                "nodes": [
                    {"id": "a", "title": "真实 A", "goal": ["执行"]},
                    {"id": "b", "depends_on": ["a"], "rollback_to": "a"},
                ]
            },
        )
        graph = self.child()
        self.assertEqual(graph["view_kind"], "actual")
        self.assertEqual(graph["edges"], [{"from": "a", "to": "b"}])
        self.assertEqual(graph["rollbacks"], [{"from": "b", "to": "a"}])
        self.assertEqual(graph["nodes"][0]["prompt"]["title"], "真实 A")
        (self.root / "child.yaml").unlink()
        self.assertEqual(self.child()["view_kind"], "planned")

    def test_fixed_template_prompt_is_read_only(self):
        task = self.write(
            "tasks/child-task.yaml", {"title": "任务", "goal": ["只读详情"]}
        )
        self.write(
            "template.yaml.templ",
            {"nodes": [{"id": "task", "yaml": "tasks/child-task.yaml"}]},
        )
        data = yaml.safe_load((self.root / "main.graph-preview.yaml").read_text())
        data["subgraphs"]["loop"]["workflow_file"] = "template.yaml.templ"
        self.write("main.graph-preview.yaml", data)
        node = self.child()["nodes"][0]
        self.assertEqual(node["prompt"]["title"], "任务")
        self.assertFalse(node["prompt_editable"])
        _, error = server.editable_target(self.workflow, {"path": str(task)})
        self.assertEqual(error[1], 403)
        self.assertIn(str(task), server.watch_signature(self.workflow))
        self.assertIn(
            str(self.root / "template.yaml.templ"),
            server.watch_signature(self.workflow),
        )

    def test_bad_real_file_does_not_use_planning_as_actual(self):
        (self.root / "child.yaml").write_text("nodes: [")
        subgraph = server.build_graph(self.workflow)["nodes"][0]["subgraph"]
        self.assertNotIn("graph", subgraph)
        self.assertIn("YAML", subgraph["error"])

    def test_nested_subgraph_cycle_is_bounded(self):
        self.write(
            "child.yaml",
            {"nodes": [{"id": "back", "task_type": "subgraph", "file": "main.yaml"}]},
        )
        nested = self.child()["nodes"][0]["subgraph"]
        self.assertIn("循环", nested["error"])
        self.assertNotIn("graph", nested)

    def test_legacy_stages_still_supported(self):
        data = yaml.safe_load((self.root / "main.graph-preview.yaml").read_text())
        del data["subgraphs"]["loop"]["nodes"]
        self.write("main.graph-preview.yaml", data)
        subgraph = server.build_graph(self.workflow)["nodes"][0]["subgraph"]
        self.assertIn("preview", subgraph)
        self.assertNotIn("graph", subgraph)

    def test_real_child_task_change_is_watched(self):
        self.write("child.yaml", {"nodes": [{"id": "a", "yaml": "deep/task.yaml"}]})
        task = self.write("deep/task.yaml", {"title": "任务", "goal": ["v1"]})
        before = server.watch_signature(self.workflow)
        self.write("deep/task.yaml", {"title": "任务", "goal": ["updated"]})
        self.assertNotEqual(
            before[str(task)], server.watch_signature(self.workflow)[str(task)]
        )
        self.assertFalse(self.child()["nodes"][0]["prompt_editable"])


if __name__ == "__main__":
    unittest.main()

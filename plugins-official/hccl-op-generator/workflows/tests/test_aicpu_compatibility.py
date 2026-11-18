#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Installation checks for engine-grouped AICPU Skills."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


from skill_sources import REPO_ROOT, SKILLS_ROOT, COMMUNICATION

PLUGIN_DIR = Path(__file__).resolve().parents[2]
RETIRED_PARENT_DIR = COMMUNICATION / "hccl-aicpu"
RETIRED_TRANSITION_DIR = COMMUNICATION / "hccl-aicpu-formal-new"
TEMPLATE_SKILL = COMMUNICATION / "hccl-aicpu-best-practice" / "SKILL.md"
ISSUE20_SKILLS = (
    "hccl-aicpu-design",
    "hccl-aicpu-debug",
    "hccl-aicpu-whitebox-design",
    "hccl-aicpu-perf-optimize",
)


class AicpuSkillInstallationTests(unittest.TestCase):
    def test_aicpu_skills_are_flat_and_shared_contract_is_retained(self) -> None:
        self.assertFalse(RETIRED_PARENT_DIR.exists())
        expected_children = {"hccl-aicpu-best-practice", *ISSUE20_SKILLS}
        actual_children = {
            path.parent.name for path in (COMMUNICATION).glob("hccl-aicpu-*/SKILL.md")
        }
        self.assertEqual(expected_children, actual_children)
        self.assertFalse((RETIRED_PARENT_DIR / "skills").exists())
        self.assertTrue((TEMPLATE_SKILL.parent / "aicpu-shared-contract.md").exists())
        self.assertTrue((TEMPLATE_SKILL.parent / "review" / "GUIDE.md").exists())
        self.assertFalse((TEMPLATE_SKILL.parent / "review" / "SKILL.md").exists())
        self.assertFalse(RETIRED_TRANSITION_DIR.exists())
        self.assertFalse((COMMUNICATION / "hccl-aicpu-formal").exists())
        self.assertFalse((COMMUNICATION / "hccl-aicpu-template-review").exists())
        self.assertFalse((COMMUNICATION / "hccl-vm" / "SKILL.md").exists())
        self.assertTrue((COMMUNICATION / "hccl-test-tool-hvm" / "SKILL.md").exists())
        self.assertFalse((COMMUNICATION / "hccl-debugging" / "SKILL.md").exists())
        for retired_ccu_skill in ("hccl-ccu-formal", "hccl-design-rules-ccu"):
            self.assertFalse((COMMUNICATION / retired_ccu_skill / "SKILL.md").exists())
        self.assertFalse((COMMUNICATION / "hccl-design-rules-aicpu").exists())

    def test_design_owns_spec_tools_and_resolves_shared_contract_references(
        self,
    ) -> None:
        design = COMMUNICATION / "hccl-aicpu-design"
        for path in (
            design / "references" / "08-algorithm-design.md",
            design / "scripts" / "check_spec.py",
            design / "scripts" / "check_layout.py",
            design / "scripts" / "test_design.py",
            TEMPLATE_SKILL.parent
            / "references"
            / "04-template-implementation-examples.md",
            TEMPLATE_SKILL.parent / "references" / "10-implementation-entry.md",
        ):
            self.assertTrue(path.is_file(), str(path))
        for path in (
            design / "SKILL.md",
            design / "dataflow-spec-template.md",
            *design.joinpath("references").glob("*.md"),
        ):
            content = path.read_text(encoding="utf-8")
            # Design guidance may reference shared architecture and data contracts.
            for target in re.findall(r"\]\(([^)]+)\)", content):
                if "hccl-aicpu-best-practice" not in target:
                    continue
                reference = (path.parent / target.split("#", 1)[0]).resolve()
                self.assertIn(TEMPLATE_SKILL.parent, reference.parents, str(path))
                self.assertTrue(reference.is_file(), str(reference))
        # The design validators must still work without the implementation Skill.
        with tempfile.TemporaryDirectory() as temp_dir:
            isolated = shutil.copytree(design, Path(temp_dir) / design.name)
            example = isolated / "assets" / "dataflow-spec.example.md"
            for checker in ("check_spec.py", "check_layout.py"):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(isolated / "scripts" / checker),
                        str(example),
                    ],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((TEMPLATE_SKILL.parent / "scripts" / "check_spec.py").exists())
        self.assertFalse(
            (TEMPLATE_SKILL.parent / "scripts" / "check_layout.py").exists()
        )

    def test_isolated_install_includes_ccu_for_each_client(self) -> None:
        declared = json.loads((PLUGIN_DIR / "plugin-sources.json").read_text())[
            "skills"
        ]
        self.assertIn("communication/hccl-ccu-best-practice", declared)
        with tempfile.TemporaryDirectory() as temp_dir:
            # Codex's native installation also writes the user's personal plugin registry.
            # These smoke tests exercise project installation without touching that registry.
            for tool in ("opencode", "claude"):
                with self.subTest(tool=tool):
                    self.check_client_install(Path(temp_dir) / tool, tool)

    def check_client_install(self, project, tool):
        environment = dict(
            os.environ,
            CANNBOT_SKIP_CODEX_PLUGIN_ADD="1",
            CANNBOT_SKIP_OPENCODE_PLUGIN_ADD="1",
        )
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required by the installer")
        result = subprocess.run(
            [
                node,
                str(REPO_ROOT / "script/bin/cannbot.js"),
                "install",
                "hccl-op-generator",
                "--source",
                str(REPO_ROOT),
                "--skills",
                str(SKILLS_ROOT),
                "--tool",
                tool,
                "--target",
                str(project),
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = json.loads((project / f".{tool}/cannbot-plugin.json").read_text())[
            "plugins"
        ][0]
        self.assertEqual("1.3.0", record["pluginVersion"])
        self.assertEqual(9, len(record["skills"]))
        self.assertEqual(4, len(record["agents"]))
        self.check_installed_agents(project, record)
        self.check_installed_skills(project, record)
        self.check_installed_scripts(project, tool, record)

    def check_installed_agents(self, project, record):
        for installed_agent in record["agents"]:
            content = (project / installed_agent).read_text()
            self.assertIn("hccl-ccu-best-practice", content)
            for link in re.findall(r"\]\(([^)]+)\)", content):
                if (
                    "ccu-multi-agent-workflow.md" in link
                    or "ccu-task-prompts.md" in link
                ):
                    self.assertTrue((project / link.split("#", 1)[0]).is_file(), link)

    def check_installed_skills(self, project, record):
        for installed in record["skills"]:
            path = project / installed
            self.assertTrue(path.is_symlink())
            self.assertEqual(COMMUNICATION / path.name, path.resolve())

    def check_installed_scripts(self, project, tool, record):
        asset = project / record["assets"] / "workflows"
        skill_dir = (
            project
            / (".claude/skills" if tool == "claude" else ".agents/skills")
            / "hccl-ccu-best-practice"
        )
        routed = subprocess.run(
            [
                sys.executable,
                str(asset / "scripts/workflow_policy.py"),
                "route",
                "--requirement",
                "CCU AllGather",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, routed.returncode, routed.stderr)
        self.assertEqual("CCU", json.loads(routed.stdout)["engine"])
        checked = subprocess.run(
            [
                sys.executable,
                str(skill_dir / "scripts/check_launch_contract.py"),
                str(skill_dir / "assets/launch-contract.example.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        self.assertTrue((asset / "scripts/validate_ccu_artifacts.py").is_file())


if __name__ == "__main__":
    unittest.main()

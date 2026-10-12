#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms of the
# CANN Open Software License Agreement Version 2.0 (the "License").
"""Installation checks for engine-grouped AICPU Skills."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
RETIRED_PARENT_DIR = REPO_ROOT / "communication" / "hccl-aicpu"
RETIRED_TRANSITION_DIR = REPO_ROOT / "communication" / "hccl-aicpu-formal-new"
TEMPLATE_SKILL = (
    REPO_ROOT
    / "communication"
    / "hccl-aicpu-best-practice"
    / "SKILL.md"
)
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
            path.parent.name for path in (REPO_ROOT / "communication").glob("hccl-aicpu-*/SKILL.md")
        }
        self.assertEqual(expected_children, actual_children)
        self.assertFalse((RETIRED_PARENT_DIR / "skills").exists())
        self.assertTrue((TEMPLATE_SKILL.parent / "aicpu-shared-contract.md").exists())
        self.assertTrue(
            (TEMPLATE_SKILL.parent / "review" / "GUIDE.md").exists()
        )
        self.assertFalse(
            (TEMPLATE_SKILL.parent / "review" / "SKILL.md").exists()
        )
        self.assertFalse(RETIRED_TRANSITION_DIR.exists())
        self.assertFalse((REPO_ROOT / "communication" / "hccl-aicpu-formal").exists())
        self.assertFalse((REPO_ROOT / "communication" / "hccl-aicpu-template-review").exists())
        self.assertFalse((REPO_ROOT / "communication" / "hccl-vm" / "SKILL.md").exists())
        self.assertTrue((REPO_ROOT / "communication" / "hccl-test-tool-hvm" / "SKILL.md").exists())
        self.assertFalse((REPO_ROOT / "communication" / "hccl-debugging" / "SKILL.md").exists())
        for retired_ccu_skill in ("hccl-ccu-formal", "hccl-design-rules-ccu"):
            self.assertFalse((REPO_ROOT / "communication" / retired_ccu_skill / "SKILL.md").exists())
        self.assertFalse(
            (REPO_ROOT / "communication" / "hccl-design-rules-aicpu").exists()
        )

    def test_design_owns_algorithm_spec_and_layout_without_implementation_dependency(self) -> None:
        design = REPO_ROOT / "communication" / "hccl-aicpu-design"
        for path in (
            design / "references" / "08-algorithm-design.md",
            design / "scripts" / "check_spec.py",
            design / "scripts" / "check_layout.py",
            design / "scripts" / "test_design.py",
            TEMPLATE_SKILL.parent / "references" / "04-template-implementation-examples.md",
            TEMPLATE_SKILL.parent / "references" / "10-implementation-entry.md",
        ):
            self.assertTrue(path.is_file(), str(path))
        for path in (
            design / "SKILL.md",
            design / "dataflow-spec-template.md",
            *design.joinpath("references").glob("*.md"),
        ):
            self.assertNotIn(
                "hccl-aicpu-best-practice",
                path.read_text(encoding="utf-8"),
                str(path),
            )
        self.assertFalse((TEMPLATE_SKILL.parent / "scripts" / "check_spec.py").exists())
        self.assertFalse((TEMPLATE_SKILL.parent / "scripts" / "check_layout.py").exists())

    def test_isolated_install_exposes_only_current_aicpu_skill_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            project_dir = temp_root / "project"
            project_dir.mkdir()
            skill_dir = project_dir / ".opencode" / "skills"
            skill_dir.mkdir(parents=True)
            retired_sources = {
                "hccl-aicpu": RETIRED_PARENT_DIR,
                "hccl-aicpu-formal-new": RETIRED_TRANSITION_DIR,
                "hccl-aicpu-formal": REPO_ROOT / "communication" / "hccl-aicpu-formal",
                "hccl-aicpu-template": (
                    REPO_ROOT / "communication" / "hccl-aicpu-formal" / "skills" / "hccl-aicpu-template"
                ),
                "hccl-aicpu-template-review": REPO_ROOT / "communication" / "hccl-aicpu-template-review",
                "hccl-vm": REPO_ROOT / "communication" / "hccl-vm",
                "hccl-ccu-formal": REPO_ROOT / "communication" / "hccl-ccu-formal",
                "hccl-design-rules-ccu": REPO_ROOT / "communication" / "hccl-design-rules-ccu",
                "hccl-debugging": REPO_ROOT / "communication" / "hccl-debugging",
                "hccl-performance-analysis": REPO_ROOT / "communication" / "hccl-performance-analysis",
            }
            for name, source in retired_sources.items():
                (skill_dir / name).symlink_to(source)
            for name in ("hccl-aicpu-best-practice", *ISSUE20_SKILLS):
                (skill_dir / name).symlink_to(RETIRED_PARENT_DIR / "skills" / name)
            environment = os.environ.copy()
            environment["HOME"] = str(temp_root / "home")

            result = subprocess.run(
                [
                    str(PLUGIN_DIR / "init.sh"),
                    "project",
                    "opencode",
                    str(project_dir),
                ],
                cwd=PLUGIN_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

            expected = {
                "hccl-aicpu-best-practice": TEMPLATE_SKILL.parent,
                "hccl-test-tool-hvm": REPO_ROOT / "communication" / "hccl-test-tool-hvm",
            }
            expected.update(
                {name: REPO_ROOT / "communication" / name for name in ISSUE20_SKILLS}
            )
            self._assert_installed_skills(skill_dir, expected)
            self._assert_retired_skills_removed(skill_dir, retired_sources)
            self._assert_manifest(project_dir, expected, retired_sources)

    def _assert_installed_skills(
        self, skill_dir: Path, expected: dict[str, Path]
    ) -> None:
        for skill_name, source in expected.items():
            installed = skill_dir / skill_name
            self.assertTrue(installed.is_symlink(), f"missing installed alias: {skill_name}")
            self.assertEqual(source.resolve(), installed.resolve())

    def _assert_manifest(
        self, project_dir: Path, expected: dict[str, Path], retired_sources: dict[str, Path]
    ) -> None:
        manifest = json.loads(
            (project_dir / ".opencode" / "cannbot-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("1.2.13", manifest["version"])
        self.assertEqual(9, len(manifest["installed_skills"]))
        self.assertTrue(expected.keys() <= set(manifest["installed_skills"]))
        for name in retired_sources:
            self.assertNotIn(name, manifest["installed_skills"])
        self.assertNotIn("hcomm-env-setup", manifest["installed_skills"])
        self.assertNotIn("hccl-design-rules-aicpu", manifest["installed_skills"])

    def _assert_retired_skills_removed(
        self, skill_dir: Path, retired_sources: dict[str, Path]
    ) -> None:
        for name in retired_sources:
            retired_installed = skill_dir / name
            self.assertFalse(retired_installed.exists() or retired_installed.is_symlink())
        retired_hcomm_installed = skill_dir / "hcomm-env-setup"
        self.assertFalse(
            retired_hcomm_installed.exists() or retired_hcomm_installed.is_symlink()
        )
        retired_aicpu_rules = skill_dir / "hccl-design-rules-aicpu"
        self.assertFalse(
            retired_aicpu_rules.exists() or retired_aicpu_rules.is_symlink()
        )


if __name__ == "__main__":
    unittest.main()

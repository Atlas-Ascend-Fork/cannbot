#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms of the
# CANN Open Software License Agreement Version 2.0 (the "License").
"""Behavioral boundaries for shared environment and HCCL-VM skills."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
COMMUNICATION = REPO_ROOT / "communication"


def read_skill(name: str) -> str:
    return (COMMUNICATION / name / "SKILL.md").read_text(encoding="utf-8")


class SharedSkillBoundaryTests(unittest.TestCase):
    def test_environment_check_returns_evidence_not_plugin_state(self) -> None:
        text = read_skill("hccl-env-check")
        self.assertIn("status: READY|NOT_READY", text)
        self.assertIn("不写任务状态文件", text)
        self.assertNotIn("environment.md", text)
        self.assertNotIn("禁止进入 Step", text)

    def test_environment_setup_documents_external_mutation_boundary(self) -> None:
        hccl_text = read_skill("hccl-env-setup")
        self.assertIn("探测模式也可能 clone 缺失仓库", hccl_text)
        self.assertIn("不自动 `git pull`", hccl_text)
        self.assertIn("明确授权", hccl_text)

    def test_hccl_test_tool_hvm_environment_check_is_non_provisioning(self) -> None:
        text = (
            COMMUNICATION / "hccl-test-tool-hvm" / "references" / "environment.md"
        ).read_text(encoding="utf-8")
        self.assertIn("不下载安装软件", text)
        self.assertIn("READY", text)
        self.assertIn("NOT_READY", text)
        self.assertNotIn("hccl_vm_installer", text)
        self.assertNotIn("sudo tee", text)

    def test_hccl_test_tool_hvm_routes_technical_operations_without_owning_workflow(self) -> None:
        text = read_skill("hccl-test-tool-hvm")
        self.assertIn("name: hccl-test-tool-hvm", text)
        self.assertFalse((COMMUNICATION / "hccl-vm" / "SKILL.md").exists())
        for reference in (
            "references/environment.md",
            "references/test-plan.md",
            "references/evidence.md",
            "references/recovery.md",
        ):
            self.assertIn(reference, text)
            self.assertTrue((COMMUNICATION / "hccl-test-tool-hvm" / reference).is_file())

        for orchestration_contract in (
            "## 阶段",
            "询问下一步",
            "向用户报告",
            "hccl_vm_installer",
            "curl -fsSL",
            "touch <INSTALL_DIR>/.hccl-vm-verified",
        ):
            self.assertNotIn(orchestration_contract, text)

    def test_retired_hcomm_environment_setup_is_removed(self) -> None:
        self.assertFalse((COMMUNICATION / "hcomm-env-setup").exists())


if __name__ == "__main__":
    unittest.main()

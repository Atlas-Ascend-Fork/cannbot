# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
"""assemble_workspace 的安装后接线和验收契约测试。"""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "assemble_workspace.py"
SPEC = importlib.util.spec_from_file_location("assemble_workspace", SCRIPT)
ASSEMBLE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(ASSEMBLE)


class AssembleWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="assemble-workspace-test-")
        self.target = Path(self.temp.name)
        self.assets = self.target / ".cannbot" / "plugins" / ASSEMBLE.PLUGIN_NAME
        hooks_source = SCRIPT.parents[2] / "hooks"
        self.assets.mkdir(parents=True)
        shutil.copytree(hooks_source, self.assets / "hooks")
        (self.assets / "workflows").mkdir()
        skills = self.target / ".agents" / "skills"
        for name in ASSEMBLE.EXPECTED_SKILLS:
            path = skills / name
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: fixture\n---\n", encoding="utf-8"
            )
        agents = self.target / ".opencode" / "agents"
        agents.mkdir(parents=True)
        for name in ("general-executor.md", "general-verifier.md"):
            (agents / name).write_text("---\nname: fixture\ndescription: fixture\n---\n", encoding="utf-8")
        registry = self.target / ".opencode" / "cannbot-plugin.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            json.dumps({
                "plugins": [{
                    "plugin": ASSEMBLE.PLUGIN_NAME,
                    "dependencies": [],
                    "dependencyAssets": [],
                }]
            }),
            encoding="utf-8",
        )
        self.addCleanup(self.temp.cleanup)

    def test_verify_after_hook_wiring(self):
        error, wired = ASSEMBLE._wire_opencode_hooks(self.target)
        self.assertIsNone(error)
        self.assertEqual(wired, 2)
        error, stats = ASSEMBLE._verify(self.target)
        self.assertIsNone(error)
        self.assertEqual(stats["skills"], 19)
        self.assertTrue((self.target / ".opencode/plugins/lib/state-transition-core.ts").is_file())
        self.assertTrue((self.target / ".opencode/hooks/pypto-op-lint/rules.json").is_file())

    def test_verify_rejects_legacy_dependency_checkout(self):
        legacy = self.target / ".cannbot" / "dependencies" / ASSEMBLE.PLUGIN_NAME
        legacy.mkdir(parents=True)
        error, _ = ASSEMBLE._verify(self.target)
        self.assertIn("旧 dependency", error or "")

    def test_install_mode_cleanup_is_scoped_to_pypto_directory(self):
        legacy = self.target / ".cannbot" / "dependencies" / ASSEMBLE.PLUGIN_NAME
        legacy.mkdir(parents=True)
        (legacy / "old.txt").write_text("old", encoding="utf-8")
        sibling = legacy.parent / "other-plugin"
        sibling.mkdir()
        ASSEMBLE._remove_legacy_root(self.target)
        self.assertFalse(legacy.exists())
        self.assertTrue(sibling.is_dir())


if __name__ == "__main__":
    unittest.main()

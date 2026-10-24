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
"""Tests for the ops-direct-invoke-flash test gate validator.

Focus: the gate binds real skill artifacts (generated cases ↔ execution
results) so it cannot be passed with a fabricated shadow result file, and it
reads the real artifact formats (blackbox CSV cases + ST result JSON; whitebox
S5 cases JSON + TTK `_result.csv` with precision_status).
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_test_gate.py"


def load_module():
    assert SCRIPT_PATH.is_file(), f"missing validator script: {SCRIPT_PATH}"
    spec = importlib.util.spec_from_file_location(
        "ops_direct_flash_validate_test_gate", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def write_agents(plugin_root: Path, test_gate: str) -> None:
    write_text(
        plugin_root / "AGENTS.md",
        f"---\ndescription: test\nharness:\n  test_gate: {test_gate}\n---\n# Team\n",
    )


def wrapped_block(test_gate: str, plugin: str = "ops-direct-invoke-flash") -> str:
    """The marker block the shared installer splices into the project config."""
    return (
        f"<!-- cannbot:{plugin}:start -->\n\n"
        f"---\nname: direct-invoke-flash\nharness:\n  test_gate: {test_gate}\n---\n\n"
        f"# CANNBot\n\n<!-- cannbot:{plugin}:end -->\n"
    )


def write_wrapped_config(path: Path, test_gate: str, prior: str = "") -> None:
    """Write the config the way the installer does: the block comes AFTER existing content."""
    write_text(path, prior + wrapped_block(test_gate))


def seed_passing(op: Path) -> None:
    """A complete, all-passing fixture using the real artifact formats."""
    # provenance
    write_json(
        op / "test-harness/blackbox/WORKFLOW_PROVENANCE.json",
        {"skill": "ascendc-st-design", "workflow": "ops/ascendc-st-design/SKILL.md"},
    )
    write_json(
        op / "test-harness/whitebox/WORKFLOW_PROVENANCE.json",
        {
            "skill": "ascendc-whitebox-design",
            "workflow": "ops/ascendc-whitebox-design/SKILL.md",
        },
    )
    # blackbox: CSV cases (st-design) + ST result JSON
    write_text(
        op / "test-harness/blackbox/cases/op_L0_test_cases.csv",
        "case_id,shape\nbb1,(8,)\nbb2,(16,)\n",
    )
    write_json(
        op / "test-harness/blackbox/results/st_result.json",
        {
            "results": [
                {"case_id": "bb1", "status": "passed"},
                {"case_id": "bb2", "status": "passed"},
            ]
        },
    )
    write_text(op / "test-harness/blackbox/logs/st_run.log", "ran 2 cases\n")
    # whitebox: S5 cases JSON + TTK _result.csv (testcase_name + precision_status)
    write_json(
        op / "test-harness/whitebox/cases/S5_mapped_cases_low.json",
        {"cases": [{"case_id": "wb1"}, {"case_id": "wb2"}]},
    )
    write_text(
        op / "test-harness/whitebox/results/ttk_op_cases_low_result.csv",
        "testcase_name,perf_status,precision_status\nwb1,PASS,PASS\nwb2,PASS,PASS\n",
    )
    write_text(op / "test-harness/whitebox/logs/tilingkey.log", "ran 2 cases\n")
    # gate manifest
    write_json(
        op / "test-harness/results/test_gate.json",
        {
            "blackbox": {
                "cases_paths": ["test-harness/blackbox/cases/op_L0_test_cases.csv"],
                "result_paths": ["test-harness/blackbox/results/st_result.json"],
                "log_paths": ["test-harness/blackbox/logs/st_run.log"],
            },
            "whitebox": {
                "cases_paths": ["test-harness/whitebox/cases/S5_mapped_cases_low.json"],
                "result_paths": [
                    "test-harness/whitebox/results/ttk_op_cases_low_result.csv"
                ],
                "log_paths": ["test-harness/whitebox/logs/tilingkey.log"],
            },
        },
    )


class TestGateValidatorTest(unittest.TestCase):
    def test_off_skips(self):
        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "off")
            self.assertEqual([], v.errors)
            self.assertEqual("skipped_by_config", v.summary["test_gate"])

    def test_on_rejects_missing_provenance(self):
        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on")  # nothing seeded
            self.assertTrue(
                any("ascendc-st-design provenance" in e for e in v.errors), v.errors
            )
            self.assertTrue(
                any("ascendc-whitebox-design provenance" in e for e in v.errors),
                v.errors,
            )

    def test_on_accepts_fully_bound_passing(self):
        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on", seed=seed_passing)
            self.assertEqual([], v.errors)
            self.assertEqual("passed", v.summary["test_gate"])

    def test_result_missing_a_generated_case_fails(self):
        def seed(op: Path):
            seed_passing(op)
            write_json(
                op / "test-harness/blackbox/results/st_result.json",
                {"results": [{"case_id": "bb1", "status": "passed"}]},
            )  # bb2 absent

        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on", seed=seed)
            self.assertTrue(
                any(
                    "do not cover generated cases" in e and "bb2" in e for e in v.errors
                ),
                v.errors,
            )

    def test_whitebox_precision_fail_fails(self):
        def seed(op: Path):
            seed_passing(op)
            write_text(
                op / "test-harness/whitebox/results/ttk_op_cases_low_result.csv",
                "testcase_name,perf_status,precision_status\nwb1,PASS,PASS\nwb2,PASS,FAIL\n",
            )

        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on", seed=seed)
            self.assertTrue(
                any("did not pass" in e and "wb2" in e for e in v.errors), v.errors
            )

    def test_fabricated_unknown_case_id_fails(self):
        # results pass for the real cases but ALSO include a case id not generated.
        def seed(op: Path):
            seed_passing(op)
            write_json(
                op / "test-harness/blackbox/results/st_result.json",
                {
                    "results": [
                        {"case_id": "bb1", "status": "passed"},
                        {"case_id": "bb2", "status": "passed"},
                        {"case_id": "ghost", "status": "passed"},
                    ]
                },
            )

        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on", seed=seed)
            self.assertTrue(
                any("NOT in the generated set" in e and "ghost" in e for e in v.errors),
                v.errors,
            )

    def test_missing_execution_log_fails(self):
        def seed(op: Path):
            seed_passing(op)
            (op / "test-harness/blackbox/logs/st_run.log").unlink()

        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on", seed=seed)
            self.assertTrue(
                any("execution log" in e and "missing" in e for e in v.errors), v.errors
            )

    def test_empty_generated_cases_fails_closed(self):
        def seed(op: Path):
            seed_passing(op)
            write_text(
                op / "test-harness/blackbox/cases/op_L0_test_cases.csv",
                "case_id,shape\n",
            )  # header only

        with tempfile.TemporaryDirectory() as t:
            v = self._validate(t, "on", seed=seed)
            self.assertTrue(any("no case ids" in e for e in v.errors), v.errors)

    def test_marker_wrapped_frontmatter_is_read(self):
        """The installer splices AGENTS.md into a marker block; the switch must still be read."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            write_wrapped_config(root / "AGENTS.md", "on")
            self.assertEqual("on", module._read_test_gate_config(root / "AGENTS.md"))

    def test_config_is_also_read_from_claude_md(self):
        """A claude install writes CLAUDE.md, not AGENTS.md."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            write_wrapped_config(root / "CLAUDE.md", "on")
            op = Path(t) / "docs/demo_op"
            op.mkdir(parents=True, exist_ok=True)
            v = module.TestGateValidator(root, op)
            self.assertEqual("on", v.test_gate)
            self.assertEqual(root / "CLAUDE.md", v.test_gate_source)

    def test_config_discovered_upward_from_operator_dir(self):
        """With no explicit --plugin-root, the nearest ancestor config wins."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            deep = root / "operators" / "relu" / "build"
            deep.mkdir(parents=True, exist_ok=True)
            write_agents(root, "on")
            self.assertEqual(root / "AGENTS.md", module._find_config_file(deep))

    def test_discovery_skips_a_config_without_a_harness_block(self):
        """An unrelated CLAUDE.md must not shadow the plugin's own config."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            inner = root / "sub"
            inner.mkdir(parents=True, exist_ok=True)
            write_agents(root, "on")
            write_text(inner / "CLAUDE.md", "---\nname: unrelated\n---\n# Other\n")
            self.assertEqual(root / "AGENTS.md", module._find_config_file(inner))

    def test_missing_config_fails_closed(self):
        """A mis-resolved root must NOT pass: 'cannot find the switch' != 'switch is off'."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            op = Path(t) / "docs/demo_op"
            op.mkdir(parents=True, exist_ok=True)
            v = module.TestGateValidator(Path(t) / "nowhere", op)
            v.validate_test_gate()
            self.assertIsNone(v.test_gate_source)
            self.assertEqual("config_not_found", v.summary["test_gate"])
            self.assertTrue(
                v.errors, "a missing config must be an error, not a silent pass"
            )
            self.assertEqual(1, v.print_result())

    def test_block_appended_after_existing_project_content_is_read(self):
        """The installer appends its block AFTER prior content, so frontmatter sits mid-file."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            write_wrapped_config(
                root / "CLAUDE.md",
                "on",
                prior="# My project\n\nAlways run the linter.\n",
            )
            self.assertEqual("on", module._read_test_gate_config(root / "CLAUDE.md"))

    def test_another_plugins_block_does_not_shadow_ours(self):
        """Several plugins splice their own blocks; we must read OUR marker's frontmatter."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            write_text(
                root / "CLAUDE.md",
                "# My project\n\n"
                + wrapped_block("off", plugin="some-other-plugin")
                + wrapped_block("on"),
            )
            self.assertEqual("on", module._read_test_gate_config(root / "CLAUDE.md"))

    def test_harness_less_sibling_does_not_shadow_the_real_config(self):
        """A project AGENTS.md with no harness block must not outvote the installer's CLAUDE.md."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            op = root / "docs/demo_op"
            op.mkdir(parents=True, exist_ok=True)
            write_wrapped_config(root / "CLAUDE.md", "on")
            write_text(root / "AGENTS.md", "---\nname: house-rules\n---\n# Rules\n")
            config = module.resolve_config_file(None, op)
            self.assertEqual(root / "CLAUDE.md", config)
            v = module.TestGateValidator(root, op, config)
            self.assertEqual("on", v.test_gate)
            self.assertEqual(root / "CLAUDE.md", v.test_gate_source)

    def test_config_inside_the_operator_doc_dir_is_ignored(self):
        """The workflow writes into docs/{OP}; it must not be able to configure its own gate."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            op = root / "docs/demo_op"
            op.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir(parents=True, exist_ok=True)
            write_agents(root, "on")
            write_agents(op, "off")  # planted by the agent under audit
            self.assertEqual(root / "AGENTS.md", module.resolve_config_file(None, op))

    def test_search_stops_at_the_project_root(self):
        """An unrelated config above the project must not supply the switch."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            outer = Path(t) / "outer"
            root = outer / "project"
            op = root / "docs/demo_op"
            op.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir(parents=True, exist_ok=True)
            write_agents(outer, "on")  # e.g. ~/.claude/CLAUDE.md
            self.assertIsNone(module._find_config_file(op, op))

    def test_end_to_end_main_fails_on_installer_shaped_tree(self):
        """main() on an installer-shaped project with the gate on and no evidence must exit 1."""
        module = load_module()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "project"
            op = root / "docs/demo_op"
            op.mkdir(parents=True, exist_ok=True)
            (root / ".git").mkdir(parents=True, exist_ok=True)
            write_wrapped_config(root / "CLAUDE.md", "on", prior="# My project\n")
            self.assertEqual(1, module.main(["--operator-doc-dir", str(op)]))

    def _validate(self, tmp: str, test_gate: str, seed=None):
        module = load_module()
        plugin_root = Path(tmp) / "plugin"
        op = Path(tmp) / "docs/demo_op"
        op.mkdir(parents=True, exist_ok=True)
        write_agents(plugin_root, test_gate)
        if seed is not None:
            seed(op)
        v = module.TestGateValidator(plugin_root, op)
        v.validate_test_gate()
        return v


if __name__ == "__main__":
    unittest.main()

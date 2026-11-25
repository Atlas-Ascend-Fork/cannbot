#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""hooks/doc_gate.py 的 UT。

覆盖：文件分类、文档覆盖度、状态读写、精度门禁、三个 handler 的判定。

运行：python3 tests/hooks/test_doc_gate.py
"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from hook_sandbox import (  # noqa: E402
    HookSandbox,
    context_of,
    decision_of,
    event_of,
    reason_of,
)


DOC_PIPELINE = (
    "/x/asc-devkit/docs/zh/guide/operator_practice/simd_operator_impl/"
    "vector_programming/pipeline.md"
)
DOC_TBUF = (
    "/x/asc-devkit/docs/zh/guide/operator_practice/simd_operator_impl/"
    "vector_programming/tbuf_usage.md"
)
DOC_API = "/x/asc-devkit/docs/zh/api/SIMD-API/basic_api/Add.md"
DOC_EXAMPLE = "/x/asc-devkit/examples/01_simd_cpp_api/demo.cpp"
FULL_DOCS = [DOC_PIPELINE, DOC_TBUF, DOC_API, DOC_EXAMPLE]

KERNEL_FILE = "/proj/out/42_Matmul/kernel/op_kernel/x.cpp"


class DocGateTestBase(unittest.TestCase):
    def setUp(self):
        self.sandbox = HookSandbox()
        self.addCleanup(self.sandbox.cleanup)
        self.module = self.sandbox.load("doc_gate")

    # ── helpers ─────────────────────────────────────────────
    def seed_docs(self, docs, remaining=0):
        self.module.write_state({"docs_read": list(docs), "edits_remaining": remaining})

    def write_precision(self, state):
        self.module.write_precision_state(state)

    def run_pre(self, tool_name="Edit", file_path=KERNEL_FILE):
        return self.sandbox.call_main(
            self.module,
            "pre",
            {"tool_name": tool_name, "tool_input": {"file_path": file_path}},
        )

    def run_post(self, tool_name="Read", file_path=DOC_API):
        return self.sandbox.call_main(
            self.module,
            "post",
            {"tool_name": tool_name, "tool_input": {"file_path": file_path}},
        )

    def run_skill(self, skill, tool_name="Skill"):
        return self.sandbox.call_main(
            self.module,
            "skill_post",
            {"tool_name": tool_name, "tool_input": {"skill": skill}},
        )


class FileClassificationTest(DocGateTestBase):
    def test_kernel_files(self):
        for path in (
            "/a/kernel/x.cpp",
            "/a/kernel/op_kernel/x.h",
            "/a/op_kernel/x.hpp",
            "/a/op_host/x.cc",
            "kernel/op_kernel/x.cpp",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.module.is_kernel_file(path))

    def test_non_kernel_files(self):
        for path in (
            "/a/kernel/readme.md",
            "/a/src/x.cpp",
            "/a/kernel_utils/x.cpp",
            "",
        ):
            with self.subTest(path=path):
                self.assertFalse(self.module.is_kernel_file(path))

    def test_doc_files(self):
        self.assertTrue(self.module.is_doc_file(DOC_API))
        self.assertTrue(self.module.is_doc_file(DOC_EXAMPLE))
        self.assertFalse(self.module.is_doc_file("/a/docs/readme.md"))


class CoverageTest(DocGateTestBase):
    def test_empty(self):
        self.assertEqual(self.module.get_covered_categories([]), set())
        self.assertEqual(len(self.module.get_missing_categories([])), 4)

    def test_full_coverage(self):
        covered = self.module.get_covered_categories(FULL_DOCS)
        self.assertEqual(len(covered), 4)
        self.assertEqual(self.module.get_missing_categories(FULL_DOCS), {})

    def test_tbuf_doc_covers_two_categories(self):
        covered = self.module.get_covered_categories([DOC_TBUF])
        self.assertEqual(len(covered), 2)

    def test_partial_coverage(self):
        covered = self.module.get_covered_categories([DOC_API])
        self.assertEqual(len(covered), 1)
        self.assertEqual(len(self.module.get_missing_categories([DOC_API])), 3)

    def test_duplicates_do_not_inflate_coverage(self):
        covered = self.module.get_covered_categories([DOC_API, DOC_API])
        self.assertEqual(len(covered), 1)


class StateFileTest(DocGateTestBase):
    def test_roundtrip(self):
        self.module.write_state({"docs_read": [DOC_API], "edits_remaining": 7})
        self.assertEqual(
            self.module.read_state(),
            {"docs_read": [DOC_API], "edits_remaining": 7},
        )

    def test_missing_file_returns_defaults(self):
        self.assertEqual(
            self.module.read_state(), {"docs_read": [], "edits_remaining": 0}
        )

    def test_legacy_last_doc_read_is_migrated(self):
        self.module.write_state({"last_doc_read": DOC_API, "edits_remaining": 3})
        state = self.module.read_state()
        self.assertEqual(state["docs_read"], [DOC_API])
        self.assertEqual(state["edits_remaining"], 3)


class PrecisionGateTest(DocGateTestBase):
    def test_no_state(self):
        self.assertEqual(self.module.check_precision_gate(), (False, None))

    def test_inactive(self):
        self.write_precision({"d_class_active": False, "edits_allowed": 5})
        self.assertEqual(self.module.check_precision_gate(), (False, None))

    def test_consumes_budget(self):
        self.write_precision({"d_class_active": True, "edits_allowed": 2})
        self.assertEqual(self.module.check_precision_gate(), (False, None))
        self.assertEqual(self.module.read_precision_state()["edits_allowed"], 1)

    def test_d1_blocked(self):
        self.write_precision(
            {
                "d_class_active": True,
                "edits_allowed": 0,
                "stage": "D1",
                "debug_call_count": 2,
            }
        )
        denied, reason = self.module.check_precision_gate()
        self.assertTrue(denied)
        self.assertIn("D-1", reason)
        self.assertIn("BLOCKED", reason)

    def test_d1_exhausted_points_to_d2(self):
        self.write_precision(
            {
                "d_class_active": True,
                "edits_allowed": 0,
                "stage": "D1",
                "debug_call_count": 7,
            }
        )
        denied, reason = self.module.check_precision_gate()
        self.assertTrue(denied)
        self.assertIn("D-2", reason)

    def test_d2_blocked(self):
        self.write_precision(
            {
                "d_class_active": True,
                "edits_allowed": 0,
                "stage": "D2",
                "tune_call_count": 1,
            }
        )
        denied, reason = self.module.check_precision_gate()
        self.assertTrue(denied)
        self.assertIn("D-2", reason)

    def test_terminal_after_twelve(self):
        self.write_precision(
            {
                "d_class_active": True,
                "edits_allowed": 0,
                "stage": "D2",
                "debug_call_count": 7,
                "tune_call_count": 5,
            }
        )
        denied, reason = self.module.check_precision_gate()
        self.assertTrue(denied)
        self.assertIn("TERMINAL", reason)


class PreHandlerTest(DocGateTestBase):
    def test_non_edit_tool_allowed(self):
        self.assertEqual(decision_of(self.run_pre(tool_name="Read")), "allow")

    def test_non_kernel_file_allowed(self):
        self.assertEqual(decision_of(self.run_pre(file_path="/a/readme.md")), "allow")

    def test_missing_docs_denied(self):
        records = self.run_pre()
        self.assertEqual(decision_of(records), "deny")
        reason = reason_of(records)
        self.assertIn("Doc Gate", reason)
        self.assertIn("缺少以下类别", reason)

    def test_full_coverage_allowed_and_budget_consumed(self):
        self.seed_docs(FULL_DOCS, remaining=50)
        records = self.run_pre()
        self.assertEqual(decision_of(records), "allow")
        self.assertEqual(self.module.read_state()["edits_remaining"], 49)

    def test_precision_gate_denies_without_spending_doc_budget(self):
        self.seed_docs(FULL_DOCS, remaining=50)
        self.write_precision(
            {"d_class_active": True, "edits_allowed": 0, "stage": "D1"}
        )
        records = self.run_pre()
        self.assertEqual(decision_of(records), "deny")
        self.assertIn("Precision Gate", reason_of(records))
        self.assertEqual(self.module.read_state()["edits_remaining"], 50)


class PostHandlerTest(DocGateTestBase):
    def test_non_doc_read_is_ignored(self):
        self.run_post(file_path="/a/readme.md")
        self.assertEqual(self.module.read_state()["docs_read"], [])

    def test_doc_read_is_recorded(self):
        self.run_post(file_path=DOC_API)
        state = self.module.read_state()
        self.assertEqual(state["docs_read"], [DOC_API])
        # 覆盖率 1 → 分档预算 10；但 pre 阶段 coverage<4 仍会拒绝编辑
        self.assertEqual(state["edits_remaining"], 10)
        self.assertIn("还需查阅", context_of(self.run_post(file_path=DOC_API)))

    def test_partial_coverage_grants_tier_budget(self):
        self.run_post(file_path=DOC_API)
        self.run_post(file_path=DOC_PIPELINE)
        # 覆盖率 2 → 分档预算 20
        self.assertEqual(self.module.read_state()["edits_remaining"], 20)

    def test_full_coverage_grants_budget(self):
        for path in FULL_DOCS:
            self.run_post(file_path=path)
        self.assertEqual(self.module.read_state()["edits_remaining"], 50)

    def test_duplicate_reads_are_deduplicated(self):
        self.run_post(file_path=DOC_API)
        self.run_post(file_path=DOC_API)
        self.assertEqual(self.module.read_state()["docs_read"], [DOC_API])


class SkillPostTest(DocGateTestBase):
    def seed_d_class(self, **extra):
        state = {"d_class_active": True, "edits_allowed": 0}
        state.update(extra)
        self.write_precision(state)

    def test_non_skill_tool_ignored(self):
        self.seed_d_class()
        self.assertEqual(decision_of(self.run_skill("x", tool_name="Read")), "allow")

    def test_unrelated_skill_ignored(self):
        self.seed_d_class()
        self.run_skill("ops-profiling")
        self.assertEqual(self.module.read_precision_state()["edits_allowed"], 0)

    def test_skill_without_d_class_grants_nothing(self):
        self.run_skill("ascendc-precision-debug")
        state = self.module.read_precision_state()
        self.assertFalse(state["d_class_active"])
        self.assertEqual(state["edits_allowed"], 0)

    def test_debug_skill_grants_seven_edits(self):
        self.seed_d_class()
        self.run_skill("ascendc-precision-debug")
        state = self.module.read_precision_state()
        self.assertEqual(state["debug_call_count"], 1)
        self.assertEqual(state["edits_allowed"], 7)
        self.assertTrue(state["skill_just_called"])

    def test_seventh_debug_call_advances_stage(self):
        self.seed_d_class(debug_call_count=6)
        self.run_skill("ascendc-precision-debug")
        state = self.module.read_precision_state()
        self.assertEqual(state["debug_call_count"], 7)
        self.assertEqual(state["stage"], "D2")

    def test_tuning_skill_grants_five_edits(self):
        self.seed_d_class()
        self.run_skill("ascendc-precision-tuning")
        state = self.module.read_precision_state()
        self.assertEqual(state["tune_call_count"], 1)
        self.assertEqual(state["edits_allowed"], 5)
        self.assertEqual(state["stage"], "D2")


class ProtocolTest(DocGateTestBase):
    def test_empty_or_invalid_json_is_allowed(self):
        for text in ("", "not json"):
            with self.subTest(text=text):
                proc = self.sandbox.run("doc_gate.py", "--mode", "pre", stdin_text=text)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_mode_dispatch_sets_event_name(self):
        self.seed_docs(FULL_DOCS, remaining=5)
        self.assertEqual(event_of(self.run_pre()), "PreToolUse")
        self.assertEqual(event_of(self.run_post(file_path=DOC_API)), "PostToolUse")
        # skill_post 只校验分发结果
        self.assertEqual(
            decision_of(self.run_skill("ascendc-precision-debug")), "allow"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

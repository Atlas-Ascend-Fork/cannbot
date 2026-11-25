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
"""hooks/skill_script_hook.py 的 UT。

覆盖：拦截判定、前缀解析、命令执行、错误分类、精度门禁状态、钩子协议输出。
运行：python3 tests/hooks/test_skill_script_hook.py
"""

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from hook_sandbox import HookSandbox  # noqa: E402
from runtime import BASH, PYTHON  # noqa: E402


class HookTestBase(unittest.TestCase):
    def setUp(self):
        self.sandbox = HookSandbox()
        self.addCleanup(self.sandbox.cleanup)
        self.module = self.sandbox.load("skill_script_hook")

    def invoke(self, name, *args, **kwargs):
        """调用被测模块的内部入口（模块内以下划线开头的函数）。"""
        return vars(self.module)[f"_{name}"](*args, **kwargs)

    def set_internal(self, name, value):
        """覆盖被测模块的内部常量。"""
        vars(self.module)[f"_{name}"] = value


class ShouldInterceptTest(HookTestBase):
    def test_intercepts_python_and_shell_scripts(self):
        for command in (
            "python3 /a/b/validate_tilelang_impl.py x",
            "python /a/validate_ascendc_impl.py x",
            "python3.11 /a/performance.py",
            "bash /a/evaluate_ascendc.sh out",
            "sh ./evaluate_tilelang.sh out",
            "python3 /a/build_ascendc.py out",
            "python3 /a/verification_ascendc.py out",
            "python3 /a/verification_tilelang.py out",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.module.should_intercept(command))

    def test_intercepts_with_cd_and_env_prefix(self):
        for command in (
            "cd /tmp/out && bash /a/evaluate_ascendc.sh .",
            "ASCEND_RT_VISIBLE_DEVICES=1 bash /a/evaluate_ascendc.sh out",
            "export A=1 && python3 /a/performance.py out",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.module.should_intercept(command))

    def test_ignores_non_script_mentions(self):
        for command in (
            "cat /a/evaluate_ascendc.sh",
            "grep evaluate_ascendc.sh build.log",
            "echo 'python3 /a/evaluate_ascendc.sh'",
            "python3 /a/evaluate_ascendc.sh.bak out",
            "python3 my_evaluate_ascendc.sh out",
            "ls -l /a",
        ):
            with self.subTest(command=command):
                self.assertFalse(self.module.should_intercept(command))


class ParseCommandTest(HookTestBase):
    def test_plain_command(self):
        cwd, env, argv = self.invoke(
            "parse_intercepted_command", "python3 /a/build.py out"
        )
        self.assertIsNone(cwd)
        self.assertEqual(env, {})
        self.assertEqual(argv, ["python3", "/a/build.py", "out"])

    def test_cd_prefix(self):
        cwd, env, argv = self.invoke(
            "parse_intercepted_command", "cd /tmp/out && bash /a/e.sh ."
        )
        self.assertEqual(cwd, "/tmp/out")
        self.assertEqual(env, {})
        self.assertEqual(argv, ["bash", "/a/e.sh", "."])

    def test_env_and_export_prefixes(self):
        cwd, env, argv = self.invoke(
            "parse_intercepted_command", "export A=1 && cd /tmp && B=2 bash /a/e.sh out"
        )
        self.assertEqual(cwd, "/tmp")
        self.assertEqual(env, {"A": "1", "B": "2"})
        self.assertEqual(argv, ["bash", "/a/e.sh", "out"])

    def test_combinations_of_prefixes(self):
        cwd, env, index = self.invoke(
            "consume_command_prefixes",
            ["export", "A=1", "&&", "cd", "/tmp", "&&", "bash", "/a/e.sh"],
        )
        self.assertEqual(cwd, "/tmp")
        self.assertEqual(env, {"A": "1"})
        self.assertEqual(index, 6)

    def test_unparseable_commands_fall_back(self):
        for command in (
            "bash /a/e.sh out | tee log",
            "bash /a/e.sh out > log.txt",
            "bash /a/e.sh out 2>&1",
            "bash /a/e.sh out && echo done",
            "bash /a/e.sh out; echo done",
            "python3 /a/e.py\npython3 /a/e.py",
            "bash $SCRIPT out",
            "cd",
            "/a/e.sh out",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.invoke("parse_intercepted_command", command))

    def test_trailing_cd_is_rejected(self):
        self.assertIsNone(self.invoke("consume_command_prefixes", ["cd"]))


class ClassifyResultTest(HookTestBase):
    def classify(self, stdout, exit_code=0, stderr=""):
        return self.invoke("classify_result", exit_code, stdout, stderr)

    def test_pass(self):
        self.assertEqual(self.classify("Result: pass\n"), "PASS")

    def test_precision_failure(self):
        self.assertEqual(self.classify("max_abs_diff=0.5\nResult: fail\n"), "D")

    def test_numeric_variants(self):
        for text in ("MERE=0.1", "matched_ratio=0.9", "max_abs_diff=1e-3"):
            with self.subTest(text=text):
                self.assertEqual(self.classify(text + "\nResult: fail\n"), "D")

    def test_code_errors(self):
        for stdout in (
            "error: use of undeclared identifier",
            "CMake Error: broken",
            "Segmentation fault",
            "make[2]: *** [x] Error 1",
        ):
            with self.subTest(stdout=stdout):
                self.assertEqual(self.classify(stdout, exit_code=1), "A")

    def test_nonzero_exit_without_patterns_is_a(self):
        self.assertEqual(self.classify("something odd", exit_code=1), "A")

    def test_zero_exit_without_patterns_is_unknown(self):
        self.assertEqual(self.classify("nothing to see", exit_code=0), "UNKNOWN")


class RunCommandTest(HookTestBase):
    def test_runs_argv_and_reports_output(self):
        code, stdout, stderr, _ms, started = self.invoke(
            "run_command",
            [PYTHON, "-c", "import sys; sys.stdout.write('hi\\n')"],
            str(self.sandbox.root),
        )
        self.assertEqual(code, 0)
        self.assertEqual(stdout.strip(), "hi")
        self.assertTrue(started)
        self.assertEqual(stderr, "")

    def test_missing_interpreter_is_not_started(self):
        code, _stdout, stderr, _ms, started = self.invoke(
            "run_command", ["definitely-not-a-real-interpreter"], str(self.sandbox.root)
        )
        self.assertEqual(code, 1)
        self.assertFalse(started)
        self.assertIn("执行异常", stderr)

    def test_resolve_cwd(self):
        self.module.PROJECT_ROOT = str(self.sandbox.root)
        self.assertEqual(
            self.invoke("resolve_cwd", "sub"), str(self.sandbox.root / "sub")
        )
        self.assertEqual(self.invoke("resolve_cwd", "/abs"), "/abs")
        self.assertEqual(self.invoke("resolve_cwd", None), str(self.sandbox.root))

    def test_missing_cd_target_is_not_started(self):
        code, _stdout, stderr, _ms, started = self.invoke(
            "run_parsed_command",
            [BASH, "-c", "true"],
            str(self.sandbox.root / "missing"),
            {},
        )
        self.assertEqual(code, 1)
        self.assertFalse(started)
        self.assertIn("No such file or directory", stderr)


class ExtractOutputDirTest(HookTestBase):
    def test_extracts_argument(self):
        self.assertEqual(
            self.invoke("extract_output_dir", "bash /a/evaluate_ascendc.sh /out/x"),
            "/out/x",
        )

    def test_missing_argument(self):
        self.assertEqual(
            self.invoke("extract_output_dir", "bash /a/evaluate_ascendc.sh"), ""
        )
        self.assertEqual(self.invoke("extract_output_dir", "ls"), "")


class PrecisionStateTest(HookTestBase):
    def setUp(self):
        super().setUp()
        self.state = self.sandbox.state_dir / "precision_gate.json"
        self.set_internal("PRECISION_GATE_STATE", str(self.state))

    def read_state(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def seed(self, state):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(state), encoding="utf-8")

    def test_d_class_writes_locked_state_and_keeps_counters(self):
        self.seed(
            {
                "d_class_active": True,
                "stage": "D1",
                "debug_call_count": 3,
                "tune_call_count": 1,
            }
        )
        self.invoke(
            "update_precision_gate", "D", "max_abs_diff=0.5\nResult: fail\n", "/out"
        )
        state = self.read_state()
        self.assertTrue(state["d_class_active"])
        self.assertEqual(state["edits_allowed"], 0)
        self.assertEqual(state["debug_call_count"], 3)
        self.assertEqual(state["tune_call_count"], 1)
        self.assertEqual(state["output_dir"], "/out")
        self.assertIn("max_abs_diff", state["failure_summary"])

    def test_debug_count_seven_advances_to_d2(self):
        self.seed({"debug_call_count": 7, "tune_call_count": 0})
        self.invoke("update_precision_gate", "D", "Result: fail\n", "/out")
        self.assertEqual(self.read_state()["stage"], "D2")

    def test_pass_resets_state(self):
        self.seed({"d_class_active": True, "edits_allowed": 3, "debug_call_count": 5})
        self.invoke("update_precision_gate", "PASS", "Result: pass\n", "/out")
        state = self.read_state()
        self.assertFalse(state["d_class_active"])
        self.assertEqual(state["edits_allowed"], 0)


class HookProtocolTest(HookTestBase):
    def parse(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, f"hook produced no output: {proc.stderr}")
        return json.loads(lines[-1])["hookSpecificOutput"]

    def test_intercepted_evaluation_returns_result(self):
        task = self.sandbox.make_task()
        script = self.sandbox.make_eval('echo "Result: pass"')
        out = self.parse(self.sandbox.run_skill_hook(f"bash {script} {task}"))
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertIn("hook-noop", out["updatedInput"]["command"])
        self.assertIn("exit_code: 0", out["additionalContext"])

    def test_cd_and_env_prefix_are_applied(self):
        task = self.sandbox.make_task()
        script = self.sandbox.make_eval(
            'echo "cwd=$(pwd)"\n'
            'echo "npu=${ASCEND_RT_VISIBLE_DEVICES:-unset}"\n'
            'echo "Result: pass"'
        )
        command = f"cd {task} && ASCEND_RT_VISIBLE_DEVICES=3 bash {script} {task}"
        out = self.parse(self.sandbox.run_skill_hook(command))
        context = out["additionalContext"]
        self.assertIn(f"cwd: {task}", context)
        self.assertIn("npu=3", context)

    def test_pipe_command_is_left_to_harness(self):
        task = self.sandbox.make_task()
        script = self.sandbox.make_eval('echo "Result: pass"')
        out = self.parse(self.sandbox.run_skill_hook(f"bash {script} {task} | tee log"))
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertNotIn("updatedInput", out)
        self.assertNotIn("additionalContext", out)

    def test_non_bash_tool_is_allowed(self):
        proc = self.sandbox.run(
            "skill_script_hook.py",
            payload={
                "tool_name": "Edit",
                "tool_input": {"file_path": "/a/kernel/x.cpp"},
            },
        )
        self.assertEqual(self.parse(proc)["permissionDecision"], "allow")

    def test_malformed_input_is_allowed(self):
        for text in ("", "not json", "[]"):
            with self.subTest(text=text):
                proc = self.sandbox.run("skill_script_hook.py", stdin_text=text)
                self.assertEqual(self.parse(proc)["permissionDecision"], "allow")

    def test_d_class_writes_gate_state(self):
        task = self.sandbox.make_task()
        script = self.sandbox.make_eval('echo "max_abs_diff=0.5"\necho "Result: fail"')
        self.parse(self.sandbox.run_skill_hook(f"bash {script} {task}"))
        state = json.loads(
            (self.sandbox.state_dir / "precision_gate.json").read_text(encoding="utf-8")
        )
        self.assertTrue(state["d_class_active"])

    def test_failed_cd_does_not_touch_gate_state(self):
        task = self.sandbox.make_task()
        script = self.sandbox.make_eval('echo "max_abs_diff=0.5"\necho "Result: fail"')
        out = self.parse(
            self.sandbox.run_skill_hook(f"cd /no/such/dir && bash {script} {task}")
        )
        self.assertIn("命令未启动", out["permissionDecisionReason"])
        self.assertFalse((self.sandbox.state_dir / "precision_gate.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

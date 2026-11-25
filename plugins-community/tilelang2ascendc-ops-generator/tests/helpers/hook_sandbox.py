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
"""Hook 测试夹具：把 hooks/ 复制到临时目录，隔离状态文件与插件仓库。"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from runtime import BASH, PYTHON


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_SRC = PLUGIN_ROOT / "hooks"


class HookSandbox:
    """每个用例一份独立的 hooks 副本、项目目录与状态目录。

    方法排列规则：构造 → 属性 → 静态方法 → 实例方法
    （实例方法按调用顺序：生命周期、模块加载、调用、运行、数据构造）。
    """

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="t2a-hook-"))
        self.hooks = self.root / "hooks"
        shutil.copytree(
            HOOKS_SRC,
            self.hooks,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        self.project = self.root / "project"
        self.project.mkdir()

    # ── properties ──────────────────────────────────────────
    @property
    def env(self):
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(self.root)
        env["CLAUDE_PROJECT_DIR"] = str(self.project)
        env.pop("PROJECT_ROOT", None)
        return env

    @property
    def state_dir(self):
        """当前实现的状态目录（插件根下的 .claude/hooks/state）。"""
        return self.root / ".claude" / "hooks" / "state"

    # ── static helpers ──────────────────────────────────────
    @staticmethod
    def capture_emit(module):
        """替换模块的 emit，兼容两种定义：emit(dict) 与 emit(event, **kwargs)。"""
        records = []

        def fake_emit(*args, **kwargs):
            if args and isinstance(args[0], str):
                records.append({"event": args[0], **kwargs})
            elif args and isinstance(args[0], dict):
                records.append(args[0])
            else:
                records.append(kwargs)

        module.emit = fake_emit
        return records

    # ── lifecycle ───────────────────────────────────────────
    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ── module loading ──────────────────────────────────────
    def load(self, module_name):
        path = self.hooks / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(
            f"{module_name}_{id(self)}", str(path)
        )
        module = importlib.util.module_from_spec(spec)
        # 固定模块级路径常量，避免宿主的同名环境变量把状态指到仓库里
        with mock.patch.dict(
            os.environ,
            {
                "CLAUDE_PLUGIN_ROOT": str(self.root),
                "CLAUDE_PROJECT_DIR": str(self.project),
                "PROJECT_ROOT": "",
            },
        ):
            spec.loader.exec_module(module)
        return module

    def call_main(self, module, mode, payload):
        """以 stdin 喂 payload 调用 main()，返回 capture 的记录。"""
        records = self.capture_emit(module)
        argv = ["hook", "--mode", mode] if mode else ["hook"]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))),
        ):
            module.main()
        return records

    # ── subprocess runners ──────────────────────────────────
    def run(self, script_name, *args, payload=None, stdin_text=None, timeout=60):
        command = [PYTHON, str(self.hooks / script_name), *args]
        if stdin_text is None:
            stdin_text = json.dumps(payload or {})
        return subprocess.run(
            command,
            input=stdin_text,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=timeout,
            shell=False,
        )

    def run_script(self, script_path, *args, timeout=60, env=None):
        return subprocess.run(
            [BASH, str(script_path), *args],
            capture_output=True,
            text=True,
            env=env or self.env,
            timeout=timeout,
            shell=False,
        )

    def run_doc_gate(self, mode, payload):
        return self.run("doc_gate.py", "--mode", mode, payload=payload)

    def run_skill_hook(self, command, session="s1"):
        return self.run(
            "skill_script_hook.py",
            payload={
                "session_id": session,
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )

    def run_session_start(self):
        return self.run_script(
            self.hooks / "session-start-tilelang2ascendc-ops-generator"
        )

    # ── fixtures ────────────────────────────────────────────
    def make_task(self, name="task"):
        task = self.root / name
        (task / "kernel" / "op_kernel").mkdir(parents=True, exist_ok=True)
        (task / "kernel" / "op_kernel" / "x.cpp").write_text(
            "// kernel\n", encoding="utf-8"
        )
        return task

    def make_eval(self, body, name="evaluate_ascendc.sh"):
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        script = bin_dir / name
        script.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
        return script


def last_hook_output(records):
    if not records:
        raise AssertionError("hook emitted no decision")
    record = records[-1]
    if "hookSpecificOutput" in record:
        return record["hookSpecificOutput"]
    return record


def decision_of(records):
    record = last_hook_output(records)
    return record.get("permissionDecision") or record.get("decision")


def reason_of(records):
    record = last_hook_output(records)
    return record.get("permissionDecisionReason") or record.get("reason") or ""


def context_of(records):
    record = last_hook_output(records)
    return record.get("additionalContext") or record.get("context") or ""


def event_of(records):
    if not records:
        raise AssertionError("hook emitted no decision")
    record = records[-1]
    if "hookSpecificOutput" in record:
        return record["hookSpecificOutput"].get("hookEventName")
    return record.get("event")

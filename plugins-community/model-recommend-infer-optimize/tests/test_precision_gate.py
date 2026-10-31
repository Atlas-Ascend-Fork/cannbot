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
"""逐输出精度门禁（verify.py --gate）的解析规则回归测试。

只覆盖阈值解析逻辑，不跑真实推理：门禁文件 -> 每个输出的 (rtol, atol) 取值优先级。
  A 无门禁文件（未显式指定）      -> (None, None)，走 CLI 回退
  B 显式指定但文件缺失            -> SystemExit
  C outputs 命中                  -> 用该输出的阈值
  D outputs 未命中但有 default    -> 用 default
  E outputs/default 都没有        -> 回退 CLI 值
  F 阈值非数字                    -> SystemExit
"""

import importlib.util
import json
import logging
import os
import sys
import tempfile

LOG = logging.getLogger("test_precision_gate")


def configure_logging():
    """测试结果按纯文本输出，便于 CI 直接阅读。"""
    if LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "framework", "GE_SESSION_DEMO", "tools")


def load_verify_module():
    sys.path.insert(0, TOOLS)
    spec = importlib.util.spec_from_file_location(
        "demo_verify", os.path.join(TOOLS, "verify.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case_missing_gate(verify, check, root):
    """A/B：无默认门禁文件、显式指定但缺失。"""
    path, gate = verify.load_precision_gate("M999_no_such_model", None)
    check("A 无门禁文件", path is None and gate is None, "path=%s" % path)

    try:
        verify.load_precision_gate("M100", os.path.join(root, "missing.json"))
        check("B 显式缺失应报错", False, "未抛 SystemExit")
    except SystemExit:
        check("B 显式缺失应报错", True, "SystemExit")


def case_thresholds(verify, check):
    """C/D/E：阈值优先级 outputs[name] > default > CLI。"""
    gate = {
        "default": {"rtol": 1e-3, "atol": 1e-2},
        "outputs": {"det_box": {"rtol": 1e-3, "atol": 0.5}, "mask": {"atol": 1e-4}},
    }
    rtol, atol = verify.gate_threshold(gate, "det_box", 1e-3, 1e-3)
    check(
        "C outputs 命中", (rtol, atol) == (1e-3, 0.5), "rtol=%s atol=%s" % (rtol, atol)
    )

    rtol, atol = verify.gate_threshold(gate, "mask", 1e-3, 1e-3)
    check(
        "C2 部分覆盖走 default",
        (rtol, atol) == (1e-3, 1e-4),
        "rtol=%s atol=%s" % (rtol, atol),
    )

    rtol, atol = verify.gate_threshold(gate, "other", 1e-3, 1e-3)
    check(
        "D 未命中走 default",
        (rtol, atol) == (1e-3, 1e-2),
        "rtol=%s atol=%s" % (rtol, atol),
    )

    rtol, atol = verify.gate_threshold({"outputs": {}}, "other", 2e-3, 3e-3)
    check(
        "E 无 default 回退 CLI",
        (rtol, atol) == (2e-3, 3e-3),
        "rtol=%s atol=%s" % (rtol, atol),
    )

    rtol, atol = verify.gate_threshold(None, "other", 2e-3, 3e-3)
    check(
        "E2 无门禁回退 CLI",
        (rtol, atol) == (2e-3, 3e-3),
        "rtol=%s atol=%s" % (rtol, atol),
    )


def case_invalid_gate(verify, check):
    """F：阈值非数字必须报错，不能静默放行。"""
    try:
        verify.gate_threshold(
            {"outputs": {"bad": {"atol": "loose"}}}, "bad", 1e-3, 1e-3
        )
        check("F 非数字阈值应报错", False, "未抛 SystemExit")
    except SystemExit:
        check("F 非数字阈值应报错", True, "SystemExit")


def case_invalid_structure(verify, check, root):
    """G：门禁文件结构非法（outputs 不是对象）必须报错。"""
    bad_path = os.path.join(root, "bad_gate.json")
    with open(bad_path, "w", encoding="utf-8") as fh:
        json.dump({"outputs": [1, 2]}, fh)
    try:
        verify.load_precision_gate("M100", bad_path)
        check("G 结构非法应报错", False, "未抛 SystemExit")
    except SystemExit:
        check("G 结构非法应报错", True, "SystemExit")


def main():
    configure_logging()
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        failures += 0 if ok else 1
        LOG.info("%-4s %-30s %s" % ("OK" if ok else "FAIL", name, detail))

    verify = load_verify_module()
    with tempfile.TemporaryDirectory() as root:
        case_missing_gate(verify, check, root)
        case_thresholds(verify, check)
        case_invalid_gate(verify, check)
        case_invalid_structure(verify, check, root)

    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

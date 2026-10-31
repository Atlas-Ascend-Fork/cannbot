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
"""sweep.py 设备占用判断的回归测试（用假的 npu-smi 输出，不需要真实卡）。

对应 M300 实测暴露的问题（8 NPU × 2 die）：
  A 竖线分列格式：空闲 device 0 不得因「别的 NPU 的 Chip0 忙」被误判 busy
  B 竖线分列格式：device 4–7 必须按 (npu, chip) 正确命中 busy（不得漏判）
  C 整行一格的格式同样能解析
  D 表头存在但没有数据行 -> 全空闲且不告警
  E 找不到表头 -> 按空闲处理并告警
  F --skip-device-check / SWEEP_SKIP_DEVICE_CHECK 生效
  G 等待超时 -> SystemExit（不再逐个 config 反复等）
"""

import importlib.util
import io
import contextlib
import logging
import os
import sys

LOG = logging.getLogger("test_sweep_device_check")


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

# M300 现场：device0 空闲，device1-7 被占用（8 NPU × 2 die）
BUSY_PAIRS = [(0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)]

HEADER = "| NPU     Chip     Process id     Process name     Memory Usage |"
RULE = (
    "+==============================================================================+"
)


def table_piped(pairs):
    lines = [
        "+--------------------------------+",
        "| npu-smi 23.0.3   Version: 23.0.3 |",
        RULE,
        HEADER,
        RULE,
    ]
    for npu, chip in pairs:
        lines.append(
            "| %-7d | %-7d | %-13d | python | 1234 |"
            % (npu, chip, 12345 + npu * 10 + chip)
        )
    lines.append(RULE)
    return "\n".join(lines) + "\n"


def table_single_cell(pairs):
    lines = ["+--------------------------------+", RULE, HEADER, RULE]
    for npu, chip in pairs:
        lines.append(
            "| %-7d %-8d %-14d python 1234 |" % (npu, chip, 12345 + npu * 10 + chip)
        )
    lines.append(RULE)
    return "\n".join(lines) + "\n"


def table_no_rows():
    return "\n".join(["", RULE, HEADER, RULE]) + "\n"


def load_sweep():
    sys.path.insert(0, TOOLS)
    spec = importlib.util.spec_from_file_location(
        "demo_sweep", os.path.join(TOOLS, "sweep.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeProc:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def case_mapping(sweep, with_table, check):
    """A/A2/B：device -> (npu, chip) 映射不得误判或漏判。"""
    occupied = with_table(
        table_piped(BUSY_PAIRS), lambda: [sweep.device_occupied(d) for d in range(8)]
    )
    check("A device0 空闲不误判", occupied[0] is False, "occupied=%s" % occupied[1:])
    check("B device1-7 占用不漏判", all(occupied[1:]), "occupied=%s" % occupied[1:])

    # A2：对照旧的错误条件——chip_id 相同的别的 NPU 不应影响 device 0
    only_npu0chip1 = with_table(table_piped([(0, 1)]), lambda: sweep.device_occupied(0))
    check(
        "A2 上层 die 忙不影响本 die",
        only_npu0chip1 is False,
        "device0=%s" % only_npu0chip1,
    )


def case_table_formats(sweep, with_table, check):
    """C/D/E：两种进程表排布、无数据行、表头缺失。"""
    single = with_table(
        table_single_cell(BUSY_PAIRS),
        lambda: [sweep.device_occupied(d) for d in range(8)],
    )
    check(
        "C 单格排布解析", single[0] is False and all(single[1:]), "occupied=%s" % single
    )

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        free = with_table(
            table_no_rows(), lambda: [sweep.device_occupied(d) for d in range(4)]
        )
    check(
        "D 无进程时不告警",
        all(x is False for x in free) and "WARN" not in buf.getvalue(),
        "warn=%r" % buf.getvalue().strip(),
    )

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        garbage = with_table("no such header\n", lambda: sweep.device_occupied(0))
    check(
        "E 无表头告警且按空闲",
        garbage is False and "未找到进程表表头" in buf.getvalue(),
    )


def case_skip_switch(sweep, check):
    """F：命令行开关与环境变量都能跳过设备检查。"""
    sweep.SKIP_DEVICE_CHECK = True
    try:
        check("F skip-device-check 生效", sweep.device_occupied(1) is False)
    finally:
        sweep.SKIP_DEVICE_CHECK = False

    os.environ["SWEEP_SKIP_DEVICE_CHECK"] = "1"
    try:
        check("F2 环境变量跳过", sweep.device_occupied(1) is False)
    finally:
        os.environ.pop("SWEEP_SKIP_DEVICE_CHECK", None)


def case_wait_timeout(sweep, with_table, check):
    """G：等待超时终止整轮，不再逐个 config 空等。"""
    try:
        with_table(table_piped(BUSY_PAIRS), lambda: sweep.wait_device_free(1, 0, 0))
        check("G 超时抛 SystemExit", False, "未抛异常")
    except SystemExit as exc:
        check(
            "G 超时抛 SystemExit", "未空闲" in str(exc), str(exc).splitlines()[0][:48]
        )


def main():
    configure_logging()
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        failures += 0 if ok else 1
        LOG.info("%-4s %-38s %s" % ("OK" if ok else "FAIL", name, detail))

    sweep = load_sweep()
    original_run = sweep.subprocess.run

    def with_table(text, fn, returncode=0):
        def fake_run(*_args, **_kwargs):
            return FakeProc(text, returncode)

        sweep.subprocess.run = fake_run
        try:
            return fn()
        finally:
            sweep.subprocess.run = original_run

    try:
        case_mapping(sweep, with_table, check)
        case_table_formats(sweep, with_table, check)
        case_skip_switch(sweep, check)
        case_wait_timeout(sweep, with_table, check)
    finally:
        sweep.subprocess.run = original_run

    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

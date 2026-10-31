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
"""loop_state.py 的行为回归测试。

覆盖正常态与失败态，重点是「不应继续循环时脚本必须给出非 0」与「终止标记/原因必须自洽」：
  A 正常           -> 0
  B ledger 裸数组  -> 0（兼容写法不再抛 AttributeError）
  C ledger 领先    -> 2
  D history 重复   -> 2
  E history > iter -> 2
  F 缺号           -> 0 + WARN（分析轮可能未记录，不阻断）
  G 终止标记矛盾   -> 2
  H 终止无原因     -> 2
  I 准入未通过     -> 4
  J 预算用尽       -> 3
  K 连续无收益     -> 3
  L 已终止         -> 3

用法：python3 tests/test_loop_state.py
"""

import json
import logging
import os
import subprocess
import sys
import tempfile

LOG = logging.getLogger("test_loop_state")


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
SCRIPT = os.path.join(HERE, "..", "workflows", "scripts", "loop_state.py")

BASE = {
    "iteration": 0,
    "no_gain_streak": 0,
    "max_iterations": 10,
    "noise_band_pct": 3.0,
    "target": {"metric": "qps", "op": ">=", "value": 1500, "confirmed_by_user": True},
    "history": [],
    "terminated": False,
    "termination_reason": "",
}


def run(log_dir, *args):
    proc = subprocess.run(
        [sys.executable, SCRIPT, *args, "--log-dir", log_dir],
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def write_case(log_dir, state_data, ledger):
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "loop_state.json"), "w", encoding="utf-8") as fh:
        json.dump(state_data, fh, ensure_ascii=False)
    with open(os.path.join(log_dir, "perf_ledger.json"), "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False)


def state(**overrides):
    data = json.loads(json.dumps(BASE))
    data.update(overrides)
    return data


CASES = [
    (
        "A 正常",
        "check",
        state(iteration=2, history=[{"iter": 1}, {"iter": 2}]),
        [{"note": "循环第1轮"}, {"note": "循环第2轮"}],
        0,
    ),
    ("B ledger 裸数组", "check", state(), [], 0),
    (
        "C ledger 领先",
        "check",
        state(iteration=2, history=[{"iter": 1}, {"iter": 2}]),
        [{"note": "循环第1轮"}, {"note": "循环第2轮"}, {"note": "循环第3轮"}],
        2,
    ),
    (
        "D history 重复",
        "check",
        state(iteration=1, history=[{"iter": 1}, {"iter": 1}]),
        [],
        2,
    ),
    (
        "E history > iteration",
        "check",
        state(iteration=1, history=[{"iter": 1}, {"iter": 2}]),
        [],
        2,
    ),
    (
        "F 缺号",
        "check",
        state(iteration=3, history=[{"iter": 1}, {"iter": 3}]),
        [{"note": "循环第3轮"}],
        0,
    ),
    (
        "G 终止标记矛盾",
        "check",
        state(terminated=False, termination_reason="target_reached"),
        [],
        2,
    ),
    ("H 终止无原因", "check", state(terminated=True, termination_reason=""), [], 2),
    ("I 准入未通过", "next", state(target={"confirmed_by_user": False}), [], 4),
    ("J 预算用尽", "next", state(iteration=2, max_iterations=2), [], 3),
    ("K 连续无收益", "next", state(iteration=1, no_gain_streak=3), [], 3),
    (
        "L 已终止",
        "next",
        state(terminated=True, termination_reason="target_reached"),
        [],
        3,
    ),
    # M/N/O：delta_pct 允许写成对象（W1）
    (
        "M delta_pct 对象",
        "check",
        state(iteration=1, history=[{"iter": 1, "gain_pct": -6.3}]),
        [{"note": "循环第1轮", "delta_pct": {"latency": -6.3, "qps": 6.7}}],
        0,
    ),
    (
        "N delta_pct 对象不一致",
        "check",
        state(iteration=1, history=[{"iter": 1, "gain_pct": -6.3}]),
        [{"note": "循环第1轮", "delta_pct": {"latency": -12.0, "qps": 14.0}}],
        2,
    ),
    (
        "O delta_pct 无可用数字",
        "check",
        state(iteration=1, history=[{"iter": 1, "gain_pct": -6.3}]),
        [{"note": "循环第1轮", "delta_pct": {"note": "见报告"}}],
        0,
    ),
]


def check_extra_cases(root):
    """P：旧版 schema 迁移；Q：损坏 JSON 的可读报错。"""
    failures = 0

    # P：旧版字段 round/rounds_executed/status + history.round
    log_dir = os.path.join(root, "case_migrate")
    os.makedirs(log_dir, exist_ok=True)
    legacy = {
        "target": {
            "metric": "latency_avg_ms",
            "op": "<=",
            "value": 4.2,
            "confirmed_by_user": True,
        },
        "noise_band_pct": 3.0,
        "round": 3,
        "rounds_executed": 3,
        "status": "running",
        "history": [{"round": 1, "gain_pct": -6.3}],
    }
    with open(os.path.join(log_dir, "loop_state.json"), "w", encoding="utf-8") as fh:
        json.dump(legacy, fh, ensure_ascii=False)
    with open(os.path.join(log_dir, "perf_ledger.json"), "w", encoding="utf-8") as fh:
        json.dump([], fh, ensure_ascii=False)
    code, output = run(log_dir, "migrate")
    with open(os.path.join(log_dir, "loop_state.json"), encoding="utf-8") as fh:
        migrated = json.load(fh)
    ok = (
        code == 0
        and migrated.get("schema_version") == 2
        and migrated.get("iteration") == 3
        and not {"round", "rounds_executed", "status"} & set(migrated)
        and migrated["history"][0].get("iter") == 1
    )
    failures += 0 if ok else 1
    LOG.info(
        "%-4s %-18s exit=%d | iteration=%s schema=%s"
        % (
            "OK" if ok else "FAIL",
            "P 旧schema迁移",
            code,
            migrated.get("iteration"),
            migrated.get("schema_version"),
        )
    )

    # Q：损坏的 JSON 必须给出可读错误并返回 1
    log_dir = os.path.join(root, "case_broken")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "loop_state.json"), "w", encoding="utf-8") as fh:
        fh.write('{"iteration": 5b}')
    with open(os.path.join(log_dir, "perf_ledger.json"), "w", encoding="utf-8") as fh:
        json.dump([], fh, ensure_ascii=False)
    code, output = run(log_dir, "check")
    ok = code == 1 and "不是合法 JSON" in output and "Traceback" not in output
    failures += 0 if ok else 1
    LOG.info(
        "%-4s %-18s exit=%d | %s"
        % (
            "OK" if ok else "FAIL",
            "Q 损坏JSON报错",
            code,
            (output.splitlines() or [""])[0][:70],
        )
    )
    return failures


def main():
    configure_logging()
    failures = 0
    with tempfile.TemporaryDirectory() as root:
        for index, (name, command, st, ledger, expect) in enumerate(CASES, 1):
            # 目录名用序号，避免用例名里的 / 或 > 在 Windows 上非法
            log_dir = os.path.join(root, "case_%02d" % index)
            write_case(log_dir, st, ledger)
            code, output = run(log_dir, command)
            ok = code == expect
            failures += 0 if ok else 1
            LOG.info(
                "%-4s %-18s exit=%d expect=%d | %s"
                % (
                    "OK" if ok else "FAIL",
                    name,
                    code,
                    expect,
                    output.splitlines()[-1][:90] if output else "",
                )
            )
        failures += check_extra_cases(root)
    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

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
"""run.sh 的 --batch 备份/预演/回退回归测试（不跑真实推理）。

在 framework/models 下建临时模型工作区（用后即删），覆盖：
  A --batch N --dry-run 不落盘，仅打印计划
  B 无备份记录时 --restore 报错退出 1
  C 有备份时 --restore 把 shape_config 恢复回备份值
"""

import json
import logging
import os
import shutil
import subprocess
import sys

LOG = logging.getLogger("test_run_batch")


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
FRAMEWORK = os.path.join(HERE, "..", "framework", "GE_SESSION_DEMO")
MODEL_ID = "998bat"
WS = os.path.join(FRAMEWORK, "models", "M" + MODEL_ID)
SHAPE = os.path.join(WS, "config", "shape_config.json")


def run(*args):
    proc = subprocess.run(
        ["bash", "run.sh", MODEL_ID, *args],
        cwd=FRAMEWORK,
        capture_output=True,
        text=True,
        shell=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def batch_size():
    with open(SHAPE, encoding="utf-8") as fh:
        return json.load(fh).get("batch_size")


def main():
    configure_logging()
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        failures += 0 if ok else 1
        LOG.info("%-4s %-28s %s" % ("OK" if ok else "FAIL", name, detail))

    shutil.rmtree(WS, ignore_errors=True)
    try:
        os.makedirs(os.path.join(WS, "config"))
        os.makedirs(os.path.join(WS, "input_data"))
        with open(SHAPE, "w", encoding="utf-8") as fh:
            json.dump({"batch_size": 1, "mode": "all_static"}, fh)
        with open(
            os.path.join(WS, "config", "io_config.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump({"inputs": [], "outputs": []}, fh)
        with open(os.path.join(WS, "input_data", "x.npy"), "wb") as fh:
            fh.write(b"fake-input")

        # A：dry-run 只打印，不改文件
        code, out = run("--batch", "4", "--dry-run")
        check(
            "A --dry-run 不落盘",
            code == 0 and "dry-run" in out and batch_size() == 1,
            "exit=%d batch_size=%s" % (code, batch_size()),
        )

        # B：没有备份记录时 restore 必须失败
        code, out = run("--restore")
        check(
            "B 无备份时 --restore 报错",
            code == 1 and "no --batch backup recorded" in out,
            "exit=%d" % code,
        )

        # C：伪造备份后，改动现场再恢复
        backup = os.path.join(WS, ".cache", "pre_batch_20260101_000000")
        os.makedirs(os.path.join(backup, "config"))
        os.makedirs(os.path.join(backup, "input_data"))
        shutil.copy2(SHAPE, os.path.join(backup, "config", "shape_config.json"))
        shutil.copy2(
            os.path.join(WS, "config", "io_config.json"),
            os.path.join(backup, "config", "io_config.json"),
        )
        shutil.copy2(
            os.path.join(WS, "input_data", "x.npy"),
            os.path.join(backup, "input_data", "x.npy"),
        )
        with open(
            os.path.join(WS, ".cache", "pre_batch_last"), "w", encoding="utf-8"
        ) as fh:
            fh.write(backup + "\n")
        with open(SHAPE, "w", encoding="utf-8") as fh:
            json.dump({"batch_size": 8, "mode": "all_static"}, fh)
        code, out = run("--restore")
        check(
            "C --restore 恢复备份值",
            code == 0 and batch_size() == 1,
            "exit=%d batch_size=%s" % (code, batch_size()),
        )
    finally:
        shutil.rmtree(WS, ignore_errors=True)

    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

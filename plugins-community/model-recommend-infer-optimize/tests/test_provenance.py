#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""基线指纹工具（check_provenance.py）的回归测试。

在 framework/models 下建临时模型工作区（用后即删），覆盖：
  A --write 记录指纹
  B 未变更时比对通过
  C frozen 域（输入）变化 -> exit 1
  D --merge 保留其余字段，并同步写 config/provenance.json
  E --merge 支持相对 GE_SESSION_DEMO 根的路径
  F 未建立基线 -> exit 2（不得静默通过）
  G merge-only 之后 frozen 漂移 -> 仍能拦住（maintainer P1-1 回归）
  H declared 域（shape_config）变化但未声明 -> exit 1
  I 同一变化用 --declare 声明后 -> exit 0，并输出 declared_change 记录
  J --declare 非实验变量 -> 参数错误
"""

import json
import logging
import os
import shutil
import subprocess
import sys

LOG = logging.getLogger("test_provenance")


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
MODEL_ID = "999prov"
BARE_ID = "999prov2"
WS = os.path.join(FRAMEWORK, "models", "M" + MODEL_ID)
BARE = os.path.join(FRAMEWORK, "models", "M" + BARE_ID)
SCRIPT = os.path.abspath(os.path.join(FRAMEWORK, "tools", "check_provenance.py"))


def run(model_id, *args, cwd=None):
    proc = subprocess.run(
        [sys.executable, SCRIPT, model_id, *args],
        cwd=cwd or FRAMEWORK,
        capture_output=True,
        text=True,
        shell=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def write_ws(root, batch=1):
    os.makedirs(os.path.join(root, "model"), exist_ok=True)
    os.makedirs(os.path.join(root, "input_data"), exist_ok=True)
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    with open(os.path.join(root, "model", "model.onnx"), "wb") as fh:
        fh.write(b"fake-onnx-bytes")
    with open(os.path.join(root, "input_data", "x.npy"), "wb") as fh:
        fh.write(b"fake-input")
    with open(
        os.path.join(root, "config", "shape_config.json"), "w", encoding="utf-8"
    ) as fh:
        json.dump({"batch_size": batch, "mode": "all_static"}, fh)


def read_json(path):
    """读取 JSON；文件不存在时返回空字典（避免 open 泄漏句柄）。"""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def case_write_and_compare(check, prov):
    """A/B/C：写指纹、未变更通过、frozen 域漂移判失败。"""
    code, _ = run(MODEL_ID, "--write")
    written = read_json(prov)
    check(
        "A --write 记录指纹",
        code == 0 and written.get("model_sha256") and written.get("input_sha256"),
        "keys=%d" % len(written),
    )

    code, out = run(MODEL_ID)
    check("B 未变更比对通过", code == 0 and "OK" in out, "exit=%d" % code)

    with open(os.path.join(WS, "input_data", "x.npy"), "ab") as fh:
        fh.write(b"tampered")
    code, out = run(MODEL_ID)
    check(
        "C 输入漂移判失败",
        code == 1 and "FAIL" in out and "input_sha256" in out,
        "exit=%d" % code,
    )

    # 恢复输入并重建基线
    write_ws(WS)
    run(MODEL_ID, "--write")


def case_merge(check, prov, baseline):
    """D/E：--merge 保留其余字段并回写记录；支持相对 GE_SESSION_DEMO 根的路径。"""
    with open(baseline, "w", encoding="utf-8") as fh:
        json.dump({"model_name": "M" + MODEL_ID, "timing": {"avg_ms": 4.24}}, fh)
    os.remove(prov)
    code, _ = run(MODEL_ID, "--merge", baseline)
    merged = read_json(baseline)
    check(
        "D --merge 保留字段并回写记录",
        code == 0
        and "fingerprints" in merged
        and merged.get("timing", {}).get("avg_ms") == 4.24
        and os.path.exists(prov),
        "exit=%d" % code,
    )

    os.remove(prov)
    rel = os.path.join("models", "M" + MODEL_ID, "config", "baseline_metadata.json")
    code, _ = run(MODEL_ID, "--merge", rel, cwd=HERE)
    check(
        "E --merge 仓根相对路径", code == 0 and os.path.exists(prov), "exit=%d" % code
    )


def case_bare_and_drift(check):
    """F/G：无基线必须 exit 2；merge-only 之后 frozen 漂移仍被拦住。"""
    code, out = run(BARE_ID)
    check("F 无基线记录非零退出", code == 2 and "尚未建立基线" in out, "exit=%d" % code)

    with open(os.path.join(WS, "input_data", "x.npy"), "ab") as fh:
        fh.write(b"drift-after-merge")
    code, _ = run(MODEL_ID)
    check("G merge 后漂移仍被拦截", code == 1, "exit=%d" % code)
    write_ws(WS)
    run(MODEL_ID, "--write")


def case_declared(check):
    """H/I/J：declared 域变化需声明、声明后放行、frozen 域不可声明。"""
    write_ws(WS, batch=4)
    code, out = run(MODEL_ID)
    check(
        "H 未声明的实验变量变化判失败",
        code == 1 and "未声明" in out and "shape_config_sha256" in out,
        "exit=%d" % code,
    )

    code, out = run(MODEL_ID, "--declare", "shape_config_sha256")
    check(
        "I 声明后通过并输出记录",
        code == 0 and "declared_change" in out,
        "exit=%d" % code,
    )

    code, out = run(MODEL_ID, "--declare", "input_sha256")
    check(
        "J 不允许声明 frozen 变量", code != 0 and "不允许声明" in out, "exit=%d" % code
    )


def main():
    configure_logging()
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        failures += 0 if ok else 1
        LOG.info("%-4s %-34s %s" % ("OK" if ok else "FAIL", name, detail))

    for path in (WS, BARE):
        shutil.rmtree(path, ignore_errors=True)
    prov = os.path.join(WS, "config", "provenance.json")
    baseline = os.path.join(WS, "config", "baseline_metadata.json")
    try:
        write_ws(WS)
        write_ws(BARE)
        case_write_and_compare(check, prov)
        case_merge(check, prov, baseline)
        case_bare_and_drift(check)
        case_declared(check)
    finally:
        for path in (WS, BARE):
            shutil.rmtree(path, ignore_errors=True)

    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

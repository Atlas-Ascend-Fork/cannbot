#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""从 CANN debug 日志核对被测算子实际加载的 kernel 二进制来源。

已知 CANN 有三种 bin-path 日志行：``Op[...]->bin path is``、
``OpName:[...]->bin file path[...]``、``Available bin for op ... is ...``。
本脚本把含被测 OpType 的行里的 bin path 抽出，并校验全部落在 --expect-dir 下。

用法：
  check_op_binpath.py <debug_log> --optype <OpType> --expect-dir <vendors/OpType 绝对路径>
退出码 0 表示 PASS；1 表示 bin path 来自内置/其它位置；2 表示没有匹配到 bin path。
"""

import argparse
import logging
import os
import re
import sys

LOG = logging.getLogger(__name__)

# 三种 bin-path 行（实机实测）：op 标识后接 bin 路径。
# ① `... Op[X] ... bin path is <P>`      ② `... OpName:[Y] ... bin file path[<P>]`
# ③ `Available bin for op <Op> is <P>`
PATTERNS = [
    re.compile(r"Op\[([A-Za-z0-9_]+)\][^\n]*?bin path is\s+(/[^\s\],]+\.o)"),
    re.compile(
        r"OpName:\[([A-Za-z0-9_]+)\][^\n]*?bin file path\s*\[\s*(/[^\]\s]+\.o)\]"
    ),
    re.compile(r"Available bin for op\s+([A-Za-z0-9_]+)\s+is\s+(/[^\s\],]+\.o)"),
]


def _read_log(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _matching_paths(text, optype):
    want = re.compile(
        r"(?:aclnn)?" + re.escape(optype.lower()) + r"(?:_\d+(?:_[a-z0-9_]+)?)?"
    )
    paths = []
    for pattern in PATTERNS:
        for optoken, bin_path in pattern.findall(text):
            if want.fullmatch(optoken.lower()) and bin_path not in paths:
                paths.append(bin_path)
    return paths


def _inside(path, expected_dir):
    real = os.path.realpath(path)
    return real == expected_dir or real.startswith(expected_dir + os.sep)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument(
        "--optype",
        required=True,
        help="被测算子 OpType(驼峰)，如 AddCustom / SoftShrink",
    )
    parser.add_argument(
        "--expect-dir",
        required=True,
        help="自定义算子安装包位置 vendors/<OpType> 绝对路径",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="没抓到本 op 的 bin path 也判失败(默认 WARN)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    try:
        text = _read_log(args.log)
    except OSError as exc:
        LOG.error("[check-origin] FAIL: 读不到日志 %s: %s", args.log, exc)
        return 1

    paths = _matching_paths(text, args.optype)
    if not paths:
        tag = "FAIL" if args.require else "WARN"
        LOG.info(
            "[check-origin] %s: 日志里没抓到 %s 的 bin path；请确认 CANN 日志和算子执行。",
            tag,
            args.optype,
        )
        return 1 if args.require else 2

    expected_dir = os.path.realpath(args.expect_dir)
    bad = [path for path in paths if not _inside(path, expected_dir)]
    for path in paths:
        status = "BAD" if path in bad else "OK "
        LOG.info("[check-origin] %s %s", status, path)

    if bad:
        LOG.error(
            "[check-origin] FAIL: %s 有 %d 个 kernel bin 不在自定义算子安装包 %s 下。",
            args.optype,
            len(bad),
            args.expect_dir,
        )
        return 1
    LOG.info(
        "[check-origin] PASS: %s 的 kernel bin 全部来自自定义算子安装包。", args.optype
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

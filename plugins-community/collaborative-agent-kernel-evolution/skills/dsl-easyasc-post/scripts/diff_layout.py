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

"""diff_layout.py — precondition + post-validation checker for dsl-easyasc-post.

Two modes:

  --mode pre    (default): validate that codegen_status.json says we're ready
                for post (a2 + next_step=post + raw_dir present + key files exist).
                Refuses on a5 (post is a no-op for simulator-only path).

  --mode post:  after transform.py ran, sanity-check that the destination tree
                contains the expected files with the expected names.

Usage:
    python diff_layout.py <op_name> [--workspace <ws>] [--output-root ./output]
                           [--mode pre|post]

Exit codes:
  0  ok
  1  layout mismatch / missing files
  2  setup error (status missing, wrong target_device)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


class _StreamProxy:
    """按名字在写出时解析 sys.stdout / sys.stderr。

    logging.StreamHandler 在构造时就持有流对象，而 print 每次调用才取
    sys.stdout / sys.stderr。用本代理转发，使二者行为一致——进程内替换或
    重定向标准流时，输出仍落到替换后的流。
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def write(self, text: str) -> int:
        return getattr(sys, self._name).write(text)

    def flush(self) -> None:
        getattr(sys, self._name).flush()


_LOG = logging.getLogger(__name__ + ".stdout")
_ERR = logging.getLogger(__name__ + ".stderr")


def _init_loggers() -> None:
    """把脚本输出接到 logging，格式为 %(message)s，每行内容与原 print 一致。"""
    for logger, name in ((_LOG, "stdout"), (_ERR, "stderr")):
        if logger.handlers:
            continue
        handler = logging.StreamHandler(_StreamProxy(name))
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


_init_loggers()


def snake_to_pascal(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_") if part)


# Files that must exist in <op>_raw/ before transform runs.
RAW_REQUIRED = [
    "CMakeLists.txt",
    "build.sh",
    "op_host/CMakeLists.txt",
    "op_host/kernel.cpp",
    "op_host/kernel_tiling.h",
    "op_kernel/CMakeLists.txt",
    "op_kernel/kernel.cpp",
]

# Files that must exist in <Op>Custom/ after transform runs.
DST_REQUIRED_TMPL = [
    "CMakeLists.txt",
    "build.sh",
    "op_host/CMakeLists.txt",
    "op_host/{snake}_custom.cpp",
    "op_host/{snake}_custom_tiling.h",
    "op_kernel/CMakeLists.txt",
    "op_kernel/{snake}_custom.cpp",
]

# Tokens that must NOT survive in the destination cpp/h files.
DST_FORBIDDEN_TOKENS_TMPL = {
    "op_host/{snake}_custom.cpp": [
        "class Kernel : public OpDef",
        "OP_ADD(Kernel)",
        "KernelTilingData ",
        '#include "kernel_tiling.h"',
    ],
    "op_host/{snake}_custom_tiling.h": [
        "BEGIN_TILING_DATA_DEF(KernelTilingData)",
        "REGISTER_TILING_DATA_CLASS(Kernel,",
    ],
    "op_kernel/{snake}_custom.cpp": [
        "void kernel(GM_ADDR",
    ],
}

# Tokens that MUST appear in destination files.
DST_REQUIRED_TOKENS_TMPL = {
    "op_host/{snake}_custom.cpp": [
        "class {Op}Custom : public OpDef",
        "OP_ADD({Op}Custom)",
        "{Op}CustomTilingData tiling",
    ],
    "op_host/{snake}_custom_tiling.h": [
        "BEGIN_TILING_DATA_DEF({Op}CustomTilingData)",
        "REGISTER_TILING_DATA_CLASS({Op}Custom,",
    ],
    "op_kernel/{snake}_custom.cpp": [
        "void {snake}_custom(GM_ADDR",
    ],
}


def check_pre(ws: Path, status: dict) -> int:
    target = status.get("target_device")
    if target == "a5":
        _ERR.info(
            "[diff_layout] REFUSE: target_device=a5; post is a no-op for simulator-only path"
        )
        return 2
    if target != "a2":
        _ERR.info(f"[diff_layout] ERROR: target_device={target!r}; expected 'a2'")
        return 2

    if status.get("next_step") != "post":
        _ERR.info(
            f"[diff_layout] ERROR: status.next_step={status.get('next_step')!r}; "
            "expected 'post'. Run dsl-easyasc-codegen first."
        )
        return 2

    raw_dir = status.get("raw_dir")
    if not raw_dir:
        _ERR.info("[diff_layout] ERROR: status.raw_dir is empty")
        return 2
    raw = Path(raw_dir)
    if not raw.is_dir():
        _ERR.info(f"[diff_layout] ERROR: raw_dir {raw} is not a directory")
        return 1

    missing = [p for p in RAW_REQUIRED if not (raw / p).is_file()]
    if missing:
        _ERR.info(f"[diff_layout] ERROR: raw_dir missing files: {missing}")
        return 1

    run_package = status.get("run_package")
    if run_package and not Path(run_package).is_file():
        _ERR.info(
            f"[diff_layout] WARN: run_package {run_package} not on disk; "
            "rebuild_if_modified.sh will need to rebuild"
        )

    _LOG.info(f"[diff_layout] PRE OK raw_dir={raw}")
    return 0


def check_post(op_name: str, dst: Path) -> int:
    snake = op_name
    op_pascal = snake_to_pascal(op_name)

    if not dst.is_dir():
        _ERR.info(f"[diff_layout] ERROR: destination {dst} is not a directory")
        return 1

    missing = []
    for tmpl in DST_REQUIRED_TMPL:
        rel = tmpl.format(snake=snake)
        if not (dst / rel).is_file():
            missing.append(rel)
    if missing:
        _ERR.info(f"[diff_layout] ERROR: destination missing files: {missing}")
        return 1

    # Token presence/absence checks.
    for rel_tmpl, tokens in DST_FORBIDDEN_TOKENS_TMPL.items():
        rel = rel_tmpl.format(snake=snake)
        text = (dst / rel).read_text()
        leaks = [
            t.format(snake=snake, Op=op_pascal)
            for t in tokens
            if t.format(snake=snake, Op=op_pascal) in text
        ]
        if leaks:
            _ERR.info(
                f"[diff_layout] ERROR: {rel} still contains pre-transform tokens: {leaks}"
            )
            return 1

    for rel_tmpl, tokens in DST_REQUIRED_TOKENS_TMPL.items():
        rel = rel_tmpl.format(snake=snake)
        text = (dst / rel).read_text()
        absent = [
            t.format(snake=snake, Op=op_pascal)
            for t in tokens
            if t.format(snake=snake, Op=op_pascal) not in text
        ]
        if absent:
            _ERR.info(f"[diff_layout] ERROR: {rel} missing required tokens: {absent}")
            return 1

    _LOG.info(f"[diff_layout] POST OK dst={dst} op_class={op_pascal}Custom")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("op_name")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--output-root", default="./output")
    ap.add_argument("--mode", choices=("pre", "post"), default="pre")
    args = ap.parse_args()

    out_root = Path(args.output_root).resolve()
    ws = (
        Path(args.workspace).resolve()
        if args.workspace
        else (out_root / args.op_name / "easyasc_workspace")
    )
    if not ws.is_dir():
        _ERR.info(f"[diff_layout] ERROR: workspace {ws} missing")
        return 2

    status_path = ws / "codegen_status.json"
    if not status_path.is_file():
        _ERR.info(f"[diff_layout] ERROR: codegen_status.json missing at {status_path}")
        return 2
    status = json.loads(status_path.read_text())

    if args.mode == "pre":
        return check_pre(ws, status)

    op_pascal = snake_to_pascal(args.op_name)
    dst = out_root / args.op_name / f"{op_pascal}Custom"
    return check_post(args.op_name, dst)


if __name__ == "__main__":
    sys.exit(main())

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

"""transform.py — rewrite easyasc's `<op>_raw/` tree into cake's `<Op>Custom/`.

Reads:
  output/<op>/easyasc_workspace/codegen_status.json    (asserts next_step="post" for a2)

Writes:
  output/<op>/<Op>Custom/                              (full cake-shaped tree)

Implements the rules from references/layout_mapping.md and references/rewrite_rules.md.

Usage:
    python transform.py <op_name> [--workspace <ws>] [--output-root ./output]
                                  [--force] [--inline-kernel]

Exit codes:
  0  success
  1  rewrite failure (rule miss, file IO, etc.)
  2  setup error (status missing, wrong target_device, dest exists without --force)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import List, Tuple


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


# (relative_path_template, find, replace_template) — applied in order.
# {snake} and {Op} are formatted in by `transform.py`.
RULES: List[Tuple[str, str, str]] = [
    (
        "op_host/{snake}_custom_tiling.h",
        "BEGIN_TILING_DATA_DEF(KernelTilingData)",
        "BEGIN_TILING_DATA_DEF({Op}CustomTilingData)",
    ),
    (
        "op_host/{snake}_custom_tiling.h",
        "REGISTER_TILING_DATA_CLASS(Kernel, KernelTilingData)",
        "REGISTER_TILING_DATA_CLASS({Op}Custom, {Op}CustomTilingData)",
    ),
    (
        "op_host/{snake}_custom.cpp",
        '#include "kernel_tiling.h"',
        '#include "{snake}_custom_tiling.h"',
    ),
    (
        "op_host/{snake}_custom.cpp",
        "KernelTilingData tiling;",
        "{Op}CustomTilingData tiling;",
    ),
    (
        "op_host/{snake}_custom.cpp",
        "class Kernel : public OpDef",
        "class {Op}Custom : public OpDef",
    ),
    (
        "op_host/{snake}_custom.cpp",
        "explicit Kernel(const char* name)",
        "explicit {Op}Custom(const char* name)",
    ),
    ("op_host/{snake}_custom.cpp", "OP_ADD(Kernel);", "OP_ADD({Op}Custom);"),
    # Kernel entry symbol must be the snake_case form of the op class (TBE convention).
    # easyasc emits: extern "C" __global__ __aicore__ void kernel(GM_ADDR ...)
    # cake expects:                                    void {snake}_custom(GM_ADDR ...)
    (
        "op_kernel/{snake}_custom.cpp",
        "void kernel(GM_ADDR",
        "void {snake}_custom(GM_ADDR",
    ),
]

# (src_relative, dst_template) — renames inside the destination tree.
RENAMES: List[Tuple[str, str]] = [
    ("op_host/kernel.cpp", "op_host/{snake}_custom.cpp"),
    ("op_host/kernel_tiling.h", "op_host/{snake}_custom_tiling.h"),
    ("op_kernel/kernel.cpp", "op_kernel/{snake}_custom.cpp"),
]


def apply(text: str, find: str, replace: str) -> Tuple[str, int]:
    if find not in text:
        return text, 0
    return text.replace(find, replace), text.count(find)


def inline_kernel_files(dest: Path, snake: str) -> None:
    """Strategy 2: collapse op_kernel into one cpp."""
    op_kernel = dest / "op_kernel"
    cpp = op_kernel / f"{snake}_custom.cpp"
    parts = []
    for header in ("tensorutils.h", "kernel_cube.h", "kernel_vec.h"):
        h = op_kernel / header
        if h.exists():
            body = h.read_text()
            body = re.sub(r"^\s*#pragma\s+once\s*$", "", body, flags=re.M)
            # strip self-references and intra-kernel includes that are about to be inlined
            body = re.sub(
                r'^\s*#include\s+"(tensorutils|kernel_cube|kernel_vec)\.h"\s*$',
                "",
                body,
                flags=re.M,
            )
            parts.append(f"// ===== inlined from {header} =====\n{body}\n")

    cpp_text = cpp.read_text()
    cpp_text = re.sub(
        r'^\s*#include\s+"(tensorutils|kernel_cube|kernel_vec)\.h"\s*$',
        "",
        cpp_text,
        flags=re.M,
    )
    # split system-style includes (top) from the rest, insert headers between.
    lines = cpp_text.splitlines(keepends=True)
    last_include = 0
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#include"):
            last_include = i + 1
    head = "".join(lines[:last_include])
    rest = "".join(lines[last_include:])
    cpp.write_text(head + "\n" + "".join(parts) + rest)
    for header in ("tensorutils.h", "kernel_cube.h", "kernel_vec.h"):
        h = op_kernel / header
        if h.exists():
            h.unlink()


def fix_kernel_entry_name(kernel_cpp: Path, snake: str) -> None:
    """Step A：把 extern "C" 入口名统一成 {snake}_custom。

    easyasc codegen 有时将入口写成驼峰形式（如 BatchNorm_custom），而 CANN
    构建系统按 optype_snake(op_class) 推导期望名称（batchnorm_custom）。
    RULES 里那条只处理 "void kernel(..."，easyasc 已用非标准名时不会命中，
    这里用正则兜底。
    """
    if not kernel_cpp.exists():
        return
    text = kernel_cpp.read_text()
    # 匹配 void 任意名_custom(，排除已经正确的 {snake}_custom(
    pattern = re.compile(rf"void (?!{re.escape(snake)}_custom\b)(\w+)_custom\s*\(")
    fixed, n_fixed = pattern.subn(f"void {snake}_custom(", text)
    if n_fixed > 0:
        kernel_cpp.write_text(fixed)
        _LOG.info(
            f"[post] Step A: fixed kernel entry name → {snake}_custom "
            f"({n_fixed} replacement(s))"
        )


CUBE_OPS = ("BlockMmad", "blockMmad", "Mmad", "mmad", "MMAD", "matmul(", "blockMmad(")


def strip_pipe_barrier_for_vec_only(dst: Path, kernel_cpp: Path, snake: str) -> None:
    """Step B：vec-only 算子移除 PipeBarrier<PIPE_ALL>()。

    easyasc 对 KERNEL_TYPE_MIX_AIC_1_2 算子统一插入 PipeBarrier<PIPE_ALL>()。
    对 vec-only 算子（kernel_cube.h 无实质 Cube 操作），PIPE_ALL 含 PIPE_FIX，
    AIV 侧会等待 AIC 侧永远不会到来的 BlockMmad 信号，导致死锁、输出全零。
    """
    cube_h = dst / "op_kernel/kernel_cube.h"
    cube_is_empty = True
    if cube_h.exists():
        cube_text = cube_h.read_text()
        cube_is_empty = not any(op in cube_text for op in CUBE_OPS)

    if cube_is_empty and kernel_cpp.exists():
        text = kernel_cpp.read_text()
        if "PipeBarrier<PIPE_ALL>()" in text:
            fixed = text.replace(
                "PipeBarrier<PIPE_ALL>();",
                "// [post] Removed PipeBarrier<PIPE_ALL>: vec-only kernel, "
                "AIC side has no BlockMmad — AIV would deadlock otherwise",
            )
            kernel_cpp.write_text(fixed)
            _LOG.info(
                f"[post] Step B: removed PipeBarrier<PIPE_ALL>() from "
                f"{snake}_custom.cpp (kernel_cube.h has no Cube ops)"
            )


def transform(op_name: str, src: Path, dst: Path, *, force: bool, inline: bool) -> int:
    snake = op_name
    op_pascal = snake_to_pascal(op_name)

    if not src.is_dir():
        _ERR.info(f"[post] ERROR: source {src} is not a directory")
        return 2

    if dst.exists():
        if not force:
            _ERR.info(
                f"[post] ERROR: destination {dst} exists; pass --force to overwrite"
            )
            return 2
        shutil.rmtree(dst)

    # Copy the whole tree as-is. Preserve symlinks (build_out/ has internal links
    # that may dangle outside the source root) and tolerate any dangling ones.
    shutil.copytree(src, dst, symlinks=True, ignore_dangling_symlinks=True)

    # Apply renames.
    for src_rel, dst_tmpl in RENAMES:
        s = dst / src_rel
        d = dst / dst_tmpl.format(snake=snake)
        if not s.exists():
            _ERR.info(f"[post] ERROR: expected {s} after copy; can't rename")
            return 1
        s.rename(d)

    # Apply rules.
    rule_hits = 0
    for rel_tmpl, find_tmpl, repl_tmpl in RULES:
        rel = rel_tmpl.format(snake=snake)
        find = find_tmpl.format(snake=snake, Op=op_pascal)
        repl = repl_tmpl.format(snake=snake, Op=op_pascal)
        path = dst / rel
        if not path.exists():
            _ERR.info(f"[post] ERROR: rule target {path} missing")
            return 1
        text = path.read_text()
        new_text, hits = apply(text, find, repl)
        if hits == 0:
            _ERR.info(f"[post] ERROR: rule produced 0 hits in {rel} for find={find!r}")
            return 1
        if hits > 1:
            _ERR.info(f"[post] WARN: rule for {rel} matched {hits}x; expected 1")
        path.write_text(new_text)
        rule_hits += hits

    if inline:
        inline_kernel_files(dst, snake)

    kernel_cpp = dst / f"op_kernel/{snake}_custom.cpp"
    fix_kernel_entry_name(kernel_cpp, snake)
    strip_pipe_barrier_for_vec_only(dst, kernel_cpp, snake)

    _LOG.info(
        f"[post] PASS dst={dst} rules_applied={len(RULES)} hits={rule_hits} inline={inline}"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("op_name")
    ap.add_argument(
        "--workspace",
        default=None,
        help="easyasc workspace; defaults to <output-root>/<op>/easyasc_workspace",
    )
    ap.add_argument("--output-root", default="./output")
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite the {Op}Custom destination if it exists",
    )
    ap.add_argument(
        "--inline-kernel",
        action="store_true",
        help="strategy 2: collapse op_kernel/*.h into a single .cpp",
    )
    return ap


def _load_gated_status(ws: Path):
    """Load codegen_status.json and apply the four preconditions for post.

    Returns (status, status_path), or None when any precondition fails — every
    failure path is an exit-code-2 condition for the caller.
    """
    status_path = ws / "codegen_status.json"
    if not status_path.is_file():
        _ERR.info(f"[post] ERROR: codegen_status.json missing at {status_path}")
        return None
    status = json.loads(status_path.read_text())

    target = status.get("target_device")
    if target != "a2":
        _ERR.info(f"[post] REFUSE: target_device={target}; post is only valid for a2")
        return None

    if not status.get("ascendc_generated"):
        _ERR.info(
            "[post] ERROR: status.ascendc_generated is false; run dsl-easyasc-codegen first"
        )
        return None

    # next_step is advisory: "post" is the expected fresh state, but we also tolerate
    # re-runs from "rebuild" / "verify" / "human-intervention" (combined with --force).
    accepted = {"post", "rebuild", "verify", "human-intervention"}
    if status.get("next_step") not in accepted:
        _ERR.info(
            f"[post] ERROR: status.next_step={status.get('next_step')!r}; expected one of {sorted(accepted)}.\n"
            f"        Run dsl-easyasc-codegen first."
        )
        return None

    return status, status_path


def main() -> int:
    args = _build_parser().parse_args()

    out_root = Path(args.output_root).resolve()
    ws = (
        Path(args.workspace).resolve()
        if args.workspace
        else (out_root / args.op_name / "easyasc_workspace")
    )
    if not ws.is_dir():
        _ERR.info(f"[post] ERROR: workspace {ws} missing")
        return 2

    gated = _load_gated_status(ws)
    if gated is None:
        return 2
    status, status_path = gated

    raw_dir = status.get("raw_dir")
    if not raw_dir:
        _ERR.info("[post] ERROR: status.raw_dir is empty")
        return 2
    src = Path(raw_dir)

    op_pascal = snake_to_pascal(args.op_name)
    dst = out_root / args.op_name / f"{op_pascal}Custom"

    rc = transform(args.op_name, src, dst, force=args.force, inline=args.inline_kernel)
    if rc == 0:
        status.setdefault("post", {})
        status["post"]["dst_dir"] = str(dst)
        status["post"]["op_class"] = f"{op_pascal}Custom"
        status["post"]["inline_kernel"] = bool(args.inline_kernel)
        status["next_step"] = "rebuild"
        status_path.write_text(json.dumps(status, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())

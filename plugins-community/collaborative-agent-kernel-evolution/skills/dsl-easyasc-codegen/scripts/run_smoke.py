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

"""run_smoke.py — run easyasc OpExec(simulator=True) and compare to PyTorch reference.

Usage:
    python run_smoke.py <op_name> [--workspace <path>] [--output-root <path>]
                        [--rtol <float>] [--atol <float>]

Contract for the kernel file at <workspace>/<op>_easyasc.py:
    The file MUST define three top-level names:
      - kernel        : the @kernel-decorated function (KernelBase)
      - make_inputs() : returns a tuple of positional args to pass to OpExec(...)
                        (torch.Tensors first, then scalar Vars)
      - reference(*inputs) : pure PyTorch implementation; takes the SAME args
                             as make_inputs() returns; returns either a tensor
                             or a tuple of tensors. The smoke harness compares
                             OpExec's return against this.

It also reads target_device from <workspace>/codegen_status.json and uses
easyasc.a2 or easyasc.a5 accordingly via the kernel module's own imports
(this script does not import easyasc directly — it loads the kernel file).

Updates codegen_status.json:
  smoke.passed  -> bool
  smoke.attempts -> increment by 1

Exit codes:
  0  smoke passed
  1  smoke failed (numerical or runtime)
  2  setup error (missing files, bad workspace, etc.)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Tuple


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


def _load_status(ws: Path) -> dict:
    p = ws / "codegen_status.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"codegen_status.json missing at {p}; run init_workspace.sh first"
        )
    return json.loads(p.read_text())


def _save_status(ws: Path, status: dict) -> None:
    p = ws / "codegen_status.json"
    p.write_text(json.dumps(status, indent=2))


def _load_kernel_module(ws: Path, op_name: str):
    kernel_file = ws / f"{op_name}_easyasc.py"
    if not kernel_file.is_file():
        raise FileNotFoundError(
            f"{kernel_file} not found. Author the kernel before running smoke."
        )
    spec = importlib.util.spec_from_file_location(f"{op_name}_easyasc", kernel_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to build import spec for {kernel_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _coerce_tuple(x: Any) -> Tuple[Any, ...]:
    if isinstance(x, tuple):
        return x
    if isinstance(x, list):
        return tuple(x)
    return (x,)


def _compare(out: Any, ref: Any, rtol: float, atol: float) -> Tuple[bool, str]:
    import torch

    out_t = _coerce_tuple(out)
    ref_t = _coerce_tuple(ref)
    if len(out_t) != len(ref_t):
        return False, f"output arity mismatch: kernel={len(out_t)} ref={len(ref_t)}"

    diffs = []
    for i, (o, r) in enumerate(zip(out_t, ref_t)):
        if not isinstance(o, torch.Tensor) or not isinstance(r, torch.Tensor):
            return (
                False,
                f"output {i} not a torch.Tensor (kernel={type(o).__name__} ref={type(r).__name__})",
            )
        if o.shape != r.shape:
            return (
                False,
                f"output {i} shape mismatch: kernel={tuple(o.shape)} ref={tuple(r.shape)}",
            )
        try:
            torch.testing.assert_close(
                o.cpu().float(), r.cpu().float(), rtol=rtol, atol=atol
            )
            diffs.append(
                f"out{i} max_abs={(o.cpu().float() - r.cpu().float()).abs().max().item():.6e}"
            )
        except AssertionError as e:
            return False, f"output {i} numerical mismatch: {e}"
    return True, "; ".join(diffs)


def load_kernel_and_opexec(ws, op_name: str, target: str):
    """导入 kernel 模块与对应 target 的 OpExec，返回 (mod, OpExec) 或 (None, 退出码)。

    OpExec 必须在 kernel 模块之后惰性导入，且按 target_device 严格分支，
    a2 与 a5 之间不做回退。
    """
    # Load the kernel module (it will import easyasc.a2 or easyasc.a5 itself).
    try:
        mod = _load_kernel_module(ws, op_name)
    except Exception as e:
        _ERR.info(f"[smoke] ERROR loading kernel module: {e}")
        traceback.print_exc()
        return None, 2

    for required in ("kernel", "make_inputs", "reference"):
        if not hasattr(mod, required):
            _ERR.info(f"[smoke] ERROR: {op_name}_easyasc.py must define `{required}`")
            return None, 2

    # Import OpExec lazily, after the kernel module has set up easyasc imports.
    # Strict branch by target_device — do NOT fall back between a2/a5.
    try:
        if target == "a2":
            from easyasc.a2 import OpExec  # type: ignore
        else:
            from easyasc.a5 import OpExec  # type: ignore
    except Exception as e:
        _ERR.info(f"[smoke] ERROR: cannot import OpExec from easyasc.{target}: {e}")
        return None, 2
    return mod, OpExec


def split_inputs(raw_inputs):
    """归一 make_inputs() 的返回值，返回 (kernel 入参, reference 入参, shape_bindings)。

    make_inputs 可返回位置参数元组，或 (位置参数元组, shape_bindings 字典)。
    reference 始终只看裸位置参数。
    """
    # Optional shape_bindings: make_inputs may return either
    #   tuple_of_args                 -> no shape_bindings
    #   (tuple_of_args, dict)         -> 2-tuple where the second element is the bindings
    shape_bindings = None
    is_pair = isinstance(raw_inputs, tuple) and len(raw_inputs) == 2
    if (
        is_pair
        and isinstance(raw_inputs[1], dict)
        and isinstance(raw_inputs[0], (tuple, list))
    ):
        inputs_for_kernel = _coerce_tuple(raw_inputs[0])
        shape_bindings = raw_inputs[1]
    else:
        inputs_for_kernel = _coerce_tuple(raw_inputs)

    # `reference` always sees the bare positional args, never the bindings.
    inputs_for_ref = inputs_for_kernel
    return inputs_for_kernel, inputs_for_ref, shape_bindings


def run_kernel_and_reference(
    ws,
    op_exec_cls,
    mod,
    status: dict,
    *,
    inputs_for_kernel,
    inputs_for_ref,
    shape_bindings,
):
    """跑 kernel 与 reference，返回 (kernel_out, ref_out) 或 (None, 退出码)。"""
    try:
        if shape_bindings is not None:
            kernel_out = op_exec_cls(mod.kernel, simulator=True)(
                *inputs_for_kernel, shape_bindings=shape_bindings
            )
        else:
            kernel_out = op_exec_cls(mod.kernel, simulator=True)(*inputs_for_kernel)
    except Exception as e:
        _ERR.info(f"[smoke] FAIL: OpExec raised: {e}")
        traceback.print_exc()
        status["smoke"]["passed"] = False
        _save_status(ws, status)
        return None, 1

    try:
        ref_out = mod.reference(*inputs_for_ref)
    except Exception as e:
        _ERR.info(f"[smoke] FAIL: reference() raised: {e}")
        traceback.print_exc()
        status["smoke"]["passed"] = False
        _save_status(ws, status)
        return None, 1
    return kernel_out, ref_out


def finalize_smoke(ws, status: dict, target: str, ok: bool, msg: str) -> int:
    """写回 a5 的终态并打印结论，返回 main 的退出码。

    a2 的终态由 run_codegen.py 负责。
    """
    # Write terminal next_step for a5 path (a5 has no codegen step).
    # a2 terminal state is written by run_codegen.py.
    if target == "a5":
        if ok:
            status["next_step"] = "report-only"
        elif status["smoke"]["attempts"] >= 3:
            status["next_step"] = "human-intervention"

    _save_status(ws, status)

    if ok:
        _LOG.info(f"[smoke] PASS attempt={status['smoke']['attempts']} {msg}")
        return 0
    else:
        _ERR.info(f"[smoke] FAIL attempt={status['smoke']['attempts']} {msg}")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("op_name")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--output-root", default="./output")
    ap.add_argument("--rtol", type=float, default=3e-3)
    ap.add_argument("--atol", type=float, default=3e-3)
    args = ap.parse_args()

    ws = (
        Path(args.workspace)
        if args.workspace
        else Path(args.output_root) / args.op_name / "easyasc_workspace"
    )
    ws = ws.resolve()
    if not ws.is_dir():
        _ERR.info(f"[smoke] ERROR: workspace {ws} does not exist")
        return 2

    try:
        status = _load_status(ws)
    except Exception as e:
        _ERR.info(f"[smoke] ERROR: {e}")
        return 2

    target = status.get("target_device")
    if target not in ("a2", "a5"):
        _ERR.info(
            f"[smoke] ERROR: target_device in status is {target!r}; expected a2|a5"
        )
        return 2

    mod, op_exec_cls = load_kernel_and_opexec(ws, args.op_name, target)
    if mod is None:
        return op_exec_cls

    inputs_for_kernel, inputs_for_ref, shape_bindings = split_inputs(mod.make_inputs())

    # Always increment attempts.
    status["smoke"]["attempts"] = int(status.get("smoke", {}).get("attempts", 0)) + 1

    kernel_out, ref_out = run_kernel_and_reference(
        ws,
        op_exec_cls,
        mod,
        status,
        inputs_for_kernel=inputs_for_kernel,
        inputs_for_ref=inputs_for_ref,
        shape_bindings=shape_bindings,
    )
    if kernel_out is None and isinstance(ref_out, int):
        return ref_out

    ok, msg = _compare(kernel_out, ref_out, args.rtol, args.atol)
    status["smoke"]["passed"] = ok

    return finalize_smoke(ws, status, target, ok, msg)


if __name__ == "__main__":
    sys.exit(main())

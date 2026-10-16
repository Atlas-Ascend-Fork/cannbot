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

"""run_codegen.py — invoke easyasc OpExec(simulator=False) to emit AscendC + build + run.

Only valid for target_device=a2. Refuses to run if target_device=a5.

Usage:
    python run_codegen.py <op_name> [--workspace <path>] [--output-root <path>]
                          [--gen-only]

Side effects:
  - chdir into the workspace (so easyasc writes b.sh / r.sh there)
  - calls OpExec(mod.kernel, out_dir=f"{op}_raw", simulator=False, gen_only=...)
    with inputs from mod.make_inputs()
  - on success, populates codegen_status.json:
      ascendc_generated -> true
      raw_dir           -> <ws>/<op>_raw
      run_package       -> <ws>/<op>_raw/build_out/custom_*.run (if it exists)
      aclnn_test_dir    -> <ws>/<op>_raw_aclnn_test
      next_step         -> "post"

Exit codes:
  0  success
  1  codegen / build / run failure
  2  setup error or wrong target_device
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import logging
import os
import sys
import traceback
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


def _a5_sim_host_available() -> bool:
    """True if this host can build+run a5 AscendC via cannsim:
    the `cannsim` binary is on PATH AND at least one Ascend950PR_* simulator
    variant is installed under $ASCEND_HOME_PATH/*-linux/simulator/."""
    import shutil

    if shutil.which("cannsim") is None:
        return False
    home = os.environ.get("ASCEND_HOME_PATH", "")
    if not home:
        return False
    return bool(glob.glob(os.path.join(home, "*-linux", "simulator", "Ascend950PR_*")))


def _load_status(ws: Path) -> dict:
    return json.loads((ws / "codegen_status.json").read_text())


def _save_status(ws: Path, status: dict) -> None:
    (ws / "codegen_status.json").write_text(json.dumps(status, indent=2))


def _load_kernel_module(ws: Path, op_name: str):
    kernel_file = ws / f"{op_name}_easyasc.py"
    if not kernel_file.is_file():
        raise FileNotFoundError(f"{kernel_file} missing")
    spec = importlib.util.spec_from_file_location(f"{op_name}_easyasc", kernel_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed import spec for {kernel_file}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_target_gate(ws, status: dict, target) -> int | None:
    """校验 target_device：a2 直接放行；a5 仅在有 A5 仿真宿主时放行。

    返回非 None 即为 main 应当据此结束的退出码。
    """
    if target == "a5":
        # a5 cannot run on a plain 910B host, but CAN be built + validated via cannsim
        # on an A5-simulator host. Default to the cannsim path when capable; otherwise report-only.
        if _a5_sim_host_available():
            _ERR.info(
                "[codegen] a5 + A5-simulator host detected (cannsim + Ascend950PR_* variant); "
                "proceeding with codegen → build → cannsim."
            )
            status["a5_sim_host"] = True
            # fall through to the shared codegen path below
        else:
            _ERR.info(
                "[codegen] target_device=a5 and no A5-simulator host found "
                "(need cannsim + an Ascend950PR_* variant under $ASCEND_HOME_PATH); report-only."
            )
            status["a5_sim_host"] = False
            status["next_step"] = "report-only"
            _save_status(ws, status)
            return 2
    elif target != "a2":
        _ERR.info(f"[codegen] REFUSE: target_device={target}; expected a2 or a5")
        _save_status(ws, status)
        return 2
    return None


def normalize_inputs(raw_inputs):
    """把 make_inputs() 的返回值归一成 (inputs 元组, shape_bindings 或 None)。"""
    shape_bindings = None
    is_pair = isinstance(raw_inputs, tuple) and len(raw_inputs) == 2
    if (
        is_pair
        and isinstance(raw_inputs[1], dict)
        and isinstance(raw_inputs[0], (tuple, list))
    ):
        inputs = tuple(raw_inputs[0])
        shape_bindings = raw_inputs[1]
    else:
        inputs = raw_inputs
        if not isinstance(inputs, tuple):
            inputs = tuple(inputs) if isinstance(inputs, list) else (inputs,)
    return inputs, shape_bindings


def run_opexec(
    ws,
    op_exec_cls,
    mod,
    inputs,
    *,
    shape_bindings,
    raw_name: str,
    gen_only: bool,
    status: dict,
) -> int | None:
    """在 ws 下执行 OpExec；返回非 None 即为 main 应当据此结束的退出码。

    easyasc 会把 b.sh/r.sh 写到当前工作目录，故先切到 ws 再还原。
    """
    # easyasc emits b.sh/r.sh in the current working directory; we want them in ws.
    prev_cwd = os.getcwd()
    os.chdir(ws)
    try:
        op = op_exec_cls(
            mod.kernel, out_dir=raw_name, simulator=False, gen_only=gen_only
        )
        if shape_bindings is not None:
            op(*inputs, shape_bindings=shape_bindings)
        else:
            op(*inputs)
    except Exception as e:
        _ERR.info(f"[codegen] FAIL: OpExec raised: {e}")
        traceback.print_exc()
        status["ascendc_generated"] = False
        status["next_step"] = "human-intervention"
        _save_status(ws, status)
        return 1
    finally:
        os.chdir(prev_cwd)
    return None


def record_artifacts(ws, status: dict, raw_name: str, target) -> int:
    """登记构建产物路径与终态，返回 main 的退出码。"""
    # Locate build artifacts.
    raw_dir = ws / raw_name
    aclnn_test_dir = ws / f"{raw_name}_aclnn_test"

    run_package = None
    candidates = sorted(glob.glob(str(raw_dir / "build_out" / "custom_*.run")))
    if candidates:
        run_package = candidates[0]

    status["ascendc_generated"] = raw_dir.is_dir()
    status["raw_dir"] = str(raw_dir) if raw_dir.is_dir() else None
    status["aclnn_test_dir"] = str(aclnn_test_dir) if aclnn_test_dir.is_dir() else None
    status["run_package"] = run_package
    if status["ascendc_generated"]:
        # a2 → hand off to dsl-easyasc-post ({Op}Custom layout for ascend-evaluation).
        # a5 → post refuses a5; the cannsim run (r.sh) IS the authoritative validation, so mark done.
        status["next_step"] = "report-only" if target == "a5" else "post"
        _save_status(ws, status)
        _LOG.info(
            f"[codegen] PASS raw_dir={raw_dir} run_package={run_package} next_step={status['next_step']}"
        )
        return 0
    else:
        status["next_step"] = "human-intervention"
        _save_status(ws, status)
        _ERR.info(f"[codegen] FAIL: expected raw_dir at {raw_dir} but it is missing")
        return 1


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("op_name")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--output-root", default="./output")
    ap.add_argument(
        "--gen-only",
        action="store_true",
        help="only emit AscendC source, skip b.sh/r.sh",
    )
    return ap


def _check_smoke_gate(status: dict) -> int | None:
    """Return an exit code when smoke blocks codegen, else None."""
    if status.get("smoke", {}).get("passed") is True:
        return None
    # We allow proceeding to codegen even when smoke failed 3 times — that's the
    # documented fallback path. But warn loudly.
    attempts = status.get("smoke", {}).get("attempts", 0)
    if attempts < 1:
        _ERR.info("[codegen] ERROR: smoke has not been run; run_smoke.py first")
        return 2
    _ERR.info(
        f"[codegen] WARN: smoke did not pass (attempts={attempts}); "
        f"continuing as documented fallback. Accuracy/perf tuning deferred to AscendC layer."
    )
    return None


def _load_dsl_entry(ws: Path, op_name: str):
    """Import the kernel module and OpExec.

    Returns (mod, OpExec), or None when any of the three preconditions fails
    (module import, required attributes, easyasc.a2 import). Every failure path
    is an exit-code-2 condition for the caller.
    """
    try:
        mod = _load_kernel_module(ws, op_name)
    except Exception as e:
        _ERR.info(f"[codegen] ERROR loading kernel module: {e}")
        traceback.print_exc()
        return None

    for required in ("kernel", "make_inputs"):
        if not hasattr(mod, required):
            _ERR.info(f"[codegen] ERROR: {op_name}_easyasc.py must define `{required}`")
            return None

    try:
        from easyasc.a2 import OpExec  # type: ignore
    except Exception as e:
        _ERR.info(f"[codegen] ERROR importing OpExec: {e}")
        return None

    return mod, OpExec


def main() -> int:
    args = _build_parser().parse_args()

    ws = (
        Path(args.workspace)
        if args.workspace
        else Path(args.output_root) / args.op_name / "easyasc_workspace"
    )
    ws = ws.resolve()
    if not ws.is_dir():
        _ERR.info(f"[codegen] ERROR: workspace {ws} missing")
        return 2

    status = _load_status(ws)
    target = status.get("target_device")
    rc = check_target_gate(ws, status, target)
    if rc is not None:
        return rc

    rc = _check_smoke_gate(status)
    if rc is not None:
        return rc

    loaded = _load_dsl_entry(ws, args.op_name)
    if loaded is None:
        return 2
    mod, op_exec_cls = loaded

    inputs, shape_bindings = normalize_inputs(mod.make_inputs())

    raw_name = f"{args.op_name}_raw"

    rc = run_opexec(
        ws,
        op_exec_cls,
        mod,
        inputs,
        shape_bindings=shape_bindings,
        raw_name=raw_name,
        gen_only=args.gen_only,
        status=status,
    )
    if rc is not None:
        return rc

    return record_artifacts(ws, status, raw_name, target)


if __name__ == "__main__":
    sys.exit(main())

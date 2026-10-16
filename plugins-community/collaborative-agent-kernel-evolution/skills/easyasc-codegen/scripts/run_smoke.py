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

"""run_smoke.py — structured simulator smoke gate for the easyasc DSL.

Runs the DSL file's own ``__main__`` self-check (which calls
``OpExec(simulator=True)`` and asserts against a torch reference) as a
subprocess, then records a structured pass/fail into the workspace's
``codegen_status.json``. This makes the simulator validation a first-class,
gated step instead of an informal "run the DSL by hand".

It works for BOTH targets — the surface (a2 vs a5) is decided by the DSL
file's own ``from easyasc.a2/a5 import *`` line, so this driver does not
import easyasc itself; it just executes ``{op}_dsl.py`` and reads its exit
code. easyasc's simulator runs on any host (no NPU needed), so the a5
simulator-only path validates here even on an a2 (910B) box.

target_device semantics (read from codegen_status.json, default a2):
  - a5  : simulator is the TERMINAL validation. Pass → next_step=report-only;
          after --max-attempts consecutive fails → next_step=human-intervention.
          (a5 never runs real codegen on this host.)
  - a2  : simulator is advisory. We record smoke.passed but do NOT set
          next_step — run_codegen.py owns the a2 terminal state, and a2 may
          fall through to codegen even on smoke failure (documented fallback).

Usage:
    PYTHONPATH="${EASYASC_DSL_HOME}:${PYTHONPATH}" \
      python3 run_smoke.py <op_name> [--output-root output] [--workspace DIR]
                           [--max-attempts 3] [--timeout 600]

Exit codes:
    0  — simulator self-check passed
    1  — simulator self-check failed (non-zero DSL exit / assertion)
    2  — setup error (missing DSL / workspace / status file)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
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


def _load_status(ws: Path) -> dict:
    p = ws / "codegen_status.json"
    if not p.is_file():
        raise FileNotFoundError(
            f"codegen_status.json missing at {p}; run init_workspace.sh first"
        )
    return json.loads(p.read_text())


def _save_status(ws: Path, status: dict) -> None:
    (ws / "codegen_status.json").write_text(json.dumps(status, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    """命令行参数定义。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("op_name")
    ap.add_argument("--output-root", default="output")
    ap.add_argument(
        "--workspace",
        default=None,
        help="override easyasc_workspace path (default: "
        "{output-root}/{op}/easyasc_workspace)",
    )
    ap.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="a5: consecutive sim fails before human-intervention",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="seconds before the DSL self-check is killed",
    )
    return ap


def run_self_check(dsl_path: Path, timeout: int) -> bool:
    """在子进程里跑 DSL 的 __main__ 自检，返回是否通过。

    easyasc 需要能被子进程导入，故把 EASYASC_DSL_HOME 前置到 PYTHONPATH。
    """
    easyasc_home = os.environ.get("EASYASC_DSL_HOME", "")
    env = dict(os.environ)
    if easyasc_home:
        env["PYTHONPATH"] = easyasc_home + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [sys.executable, str(dsl_path)],
            env=env,
            timeout=timeout,
        )
        passed = proc.returncode == 0
    except subprocess.TimeoutExpired:
        _ERR.info(f"[smoke] FAIL: self-check exceeded {timeout}s timeout")
        passed = False
    return passed


def main() -> int:
    args = build_arg_parser().parse_args()

    op = args.op_name
    op_dir = Path(args.output_root) / op
    dsl_path = op_dir / f"{op}_dsl.py"
    ws = Path(args.workspace) if args.workspace else op_dir / "easyasc_workspace"

    if not dsl_path.is_file():
        _ERR.info(f"[smoke] ERROR: DSL not found: {dsl_path}")
        return 2
    try:
        status = _load_status(ws)
    except Exception as e:  # noqa: BLE001 — surface any status-load failure
        _ERR.info(f"[smoke] ERROR: {e}")
        return 2

    target = status.get("target_device", "a2") or "a2"

    _LOG.info(
        f"[smoke] target={target}: running {dsl_path} __main__ (OpExec simulator=True)"
    )
    passed = run_self_check(dsl_path, args.timeout)

    smoke = status.setdefault("smoke", {"passed": None, "attempts": 0})
    smoke["attempts"] = int(smoke.get("attempts", 0)) + 1
    smoke["passed"] = passed

    # a5 is simulator-only: this is the terminal gate.
    if target == "a5":
        if passed:
            status["next_step"] = "report-only"
        elif smoke["attempts"] >= args.max_attempts:
            status["next_step"] = "human-intervention"
        # else: leave next_step unset → the agent re-authors the DSL and retries
    # a2: advisory only; run_codegen.py owns the terminal state.

    _save_status(ws, status)

    if passed:
        tail = "→ next_step=report-only" if target == "a5" else "→ proceed to codegen"
        _LOG.info(f"[smoke] PASS attempt={smoke['attempts']} {tail}")
        return 0
    _ERR.info(
        f"[smoke] FAIL attempt={smoke['attempts']}"
        + (
            f" (>= {args.max_attempts} → human-intervention)"
            if target == "a5" and smoke["attempts"] >= args.max_attempts
            else ""
        )
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

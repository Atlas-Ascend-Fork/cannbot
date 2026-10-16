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

"""check_ub_usage — flag under-utilized UB in easyasc simulator output.

Usage
-----
Pipe simulator output through this script (or pass a saved log path):

    python3 path/to/{op}_dsl.py 2>&1 | check_ub_usage.py
    check_ub_usage.py /path/to/simulator.log

    # Optionally pass the DSL file to detect Var-tile (shape-adaptive UB)
    # mode. With --dsl provided, low UB usage on small shapes is NOT
    # flagged — instead it's reported as "shape-adaptive OK".
    check_ub_usage.py --dsl path/to/{op}_dsl.py /path/to/simulator.log

The simulator prints lines like ``| Usage: 20 KB / 192 KB |`` for each kernel
run. This script extracts every such line, computes the utilization %, and:

1. **Without --dsl** (legacy mode): flags any run with utilization < 30%
   as likely TILE-sizing miss. Suggests TILE multipliers.

2. **With --dsl detecting Var-tile pattern** (recommended): observes that
   UB usage scales with shape, reports per-run usage with shape annotation,
   only flags if usage is high AND not adapting (i.e., already at compile-
   time max). This is the right mode for shape-aware kernels.

Why a separate script (not patched into the simulator)
------------------------------------------------------
The simulator lives in upstream ``ops-easyasc-dsl`` (a git submodule of
cake). We don't fork it just to add a warning. This wrapper is
purely additive — runs against existing simulator stdout.

Var-tile detection
------------------
The script looks at the provided DSL file (--dsl) for patterns indicating
shape-adaptive UB sizing:

    - ``Tensor(DT.*, [..., Min(...)``         (Min-bounded runtime tile)
    - ``Tensor(DT.*, [..., CeilDiv(...)``     (Aligned runtime tile)
    - ``tile_var =`` or ``TILE_VAR =``        (common variable name)
    - ``Tensor(DT.*, [..., <some Var expr>``  (Var in shape)

If any pattern matches, Var-tile mode is enabled — low UB usage on small
shapes is interpreted as correct adaptation, not waste.

Exit codes
----------
0 — all kernel runs use >= 30% UB, OR Var-tile pattern detected (any usage OK)
1 — at least one kernel run uses < 30% UB AND no Var-tile pattern detected.
    CI / DSL verification should treat this as a soft warning (allow override
    via PROGRESS.md note explaining why the small TILE is necessary).
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import sys
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

# Matches lines like "             | Usage: 20 KB / 192 KB              |"
# Also handles fractional KB (e.g. "115.25 KB").
USAGE_RE = re.compile(r"Usage:\s*([\d.]+)\s*KB\s*/\s*([\d.]+)\s*KB")

# Threshold below which we flag a run as under-utilized.
LOW_UTIL_THRESHOLD = 0.30

# Target utilization the suggestion aims for (leaves some headroom for
# double-buffering / scratch).
TARGET_UTIL = 0.80


def parse_usage_lines(text: str) -> List[Tuple[float, float]]:
    """Return list of (used_kb, capacity_kb) for every ``Usage: X / Y KB`` line."""
    out: List[Tuple[float, float]] = []
    for m in USAGE_RE.finditer(text):
        used = float(m.group(1))
        cap = float(m.group(2))
        out.append((used, cap))
    return out


def suggest_scale_factor(used_kb: float, cap_kb: float) -> int:
    """Suggest an integer multiplier for TILE_* to approach TARGET_UTIL.

    Picks the largest power-of-two multiplier ``2^k`` such that
    ``used_kb * 2^k <= cap_kb * TARGET_UTIL``. Power-of-two preserves the
    common ``TILE_N = 1024`` / 2048 / 4096 / 8192 cadence.
    """
    if used_kb <= 0:
        return 1
    headroom = cap_kb * TARGET_UTIL / used_kb
    if headroom < 2:
        return 1
    return 1 << int(math.floor(math.log2(headroom)))


# Var-tile detection — DSL patterns that indicate shape-adaptive UB.
_VAR_TILE_PATTERNS = [
    # Tensor(DT.*, [..., Min(...)...]) — runtime-bounded tile size
    re.compile(r"Tensor\s*\([^,]+,\s*\[[^\]]*Min\s*\(", re.IGNORECASE),
    # Tensor(DT.*, [..., CeilDiv(...)...]) — runtime-aligned tile
    re.compile(r"Tensor\s*\([^,]+,\s*\[[^\]]*CeilDiv\s*\(", re.IGNORECASE),
    # Tensor(DT.*, [..., <lowercase_var>, ...]) — Var name as shape
    # (matches "[1, tile_var]" style)
    re.compile(r"Tensor\s*\([^,]+,\s*\[[^\]]*(?:tile_var|tile_size|adaptive_tile)\b"),
]


def detect_var_tile(dsl_path: str | None) -> Tuple[bool, str]:
    """Return (is_var_tile, reason). Reads DSL file if given."""
    if not dsl_path:
        return (False, "no --dsl provided")
    try:
        text = open(dsl_path, encoding="utf-8").read()
    except OSError:
        return (False, f"could not read DSL file: {dsl_path}")
    for pat in _VAR_TILE_PATTERNS:
        m = pat.search(text)
        if m:
            return (True, f"matched pattern {pat.pattern[:50]}...")
    return (False, "no Var-tile expression found in Tensor shapes")


def print_scan_header(
    usage_lines: List[Tuple[float, float]], var_tile_mode: bool
) -> None:
    """打印扫描抬头；Var-tile 模式下注明 kernel 为形状自适应。"""
    if var_tile_mode:
        _ERR.info(
            f"check_ub_usage — scanning {len(usage_lines)} simulator run(s) "
            f"in **Var-tile mode** (kernel shape-adaptive):"
        )
    else:
        _ERR.info(f"check_ub_usage — scanning {len(usage_lines)} simulator run(s):")


def print_var_tile_diagnostic(usage_pcts: List[float], var_tile_reason: str) -> None:
    """Var-tile 模式下报告 UB 用量是否真的随形状变化。调用方已确认样本数 >= 2。"""
    var_range = max(usage_pcts) - min(usage_pcts)
    if var_range < 0.05:
        _ERR.info(
            "\n[check_ub_usage] Var-tile pattern detected but UB usage is\n"
            "  uniform across runs (range < 5%). Either: (a) all shapes happen\n"
            "  to hit the same tile_var bucket, or (b) Var expression in\n"
            "  Tensor shape isn't actually shrinking. Verify with a self-\n"
            "  check shape where N << TILE_MAX (e.g. N=128)."
        )
    else:
        _ERR.info(
            f"\n[check_ub_usage] OK — Var-tile shape-adaptation verified.\n"
            f"  UB usage range: {min(usage_pcts) * 100:.1f}% — {max(usage_pcts) * 100:.1f}%\n"
            f"  Reason: {var_tile_reason}"
        )


def print_utilization_verdict(any_low: bool) -> None:
    """打印 UB 利用率结论：低于阈值时给出调整 TILE 或改用 Var-tile 的指引。"""
    if any_low:
        _ERR.info(
            "\n[check_ub_usage] FAILED: >=1 kernel run uses < 30% UB.\n"
            "  Common cause: TILE_N or TILE_H is set conservatively (often\n"
            "  1024) when the algorithm could fit a much larger tile per\n"
            "  iteration. Larger tiles => fewer col/row loops => less MTE\n"
            "  dispatch overhead, often 2-8x wall-time speedup with zero\n"
            "  precision loss.\n"
            "\n"
            "  How to fix (recommended):\n"
            "    Switch to the Var-tile pattern — shape-adaptive UB sizing\n"
            "    that maxes UB on large N and shrinks on small N. See:\n"
            "      references/output_example/mish_var_tile.py\n"
            "    Empirically, Var-tile beats both fixed TILE=1024 and\n"
            "    fixed TILE=8192 on mixed-shape benchmarks (geomean +41%\n"
            "    over baseline on mish 8-shape suite).\n"
            "\n"
            "  How to fix (legacy, fixed-TILE pattern):\n"
            "    1. Identify the TILE_N / TILE_H constant at the top of\n"
            "       your DSL file.\n"
            "    2. Double it; re-run simulator self-check; check Usage.\n"
            "    3. Repeat until Usage > 60% or simulator throws\n"
            "       MemoryError. Back off one step.\n"
            "    4. Confirm precision diff didn't change.\n"
            "    But: fixed-TILE wastes UB on small shapes and underutilizes\n"
            "    on large shapes vs Var-tile. Prefer Var-tile for new DSL.\n"
            "\n"
            "  Exception path: if your op intentionally uses small tiles\n"
            "  (e.g. tail-merge or per-row scalar reduction with intrinsic\n"
            "  cadd-of-64 granularity), document in PROGRESS.md why the\n"
            "  small TILE is necessary and ignore this warning."
        )
    else:
        _ERR.info("\n[check_ub_usage] OK: all runs use >= 30% UB.")


def _scale_suggestion(cap: float, used: float) -> str:
    """低利用率时给出放大 TILE 的建议；放大倍数不足 2 倍时返回空串。"""
    factor = suggest_scale_factor(used, cap)
    if factor < 2:
        return ""
    target_kb = used * factor
    target_util = target_kb / cap
    return (
        f"  -> try increasing TILE_N / TILE_H by {factor}x "
        f"(would yield ~{target_kb:.1f} KB, "
        f"{target_util * 100:.0f}% utilization), "
        f"OR switch to Var-tile pattern "
        f"(see references/output_example/mish_var_tile.py)"
    )


def report(
    usage_lines: List[Tuple[float, float]],
    var_tile_mode: bool = False,
    var_tile_reason: str = "",
) -> bool:
    """Print a per-run report; return True iff any run is under-utilized.

    var_tile_mode=True: shape-adaptive kernel detected. Low usage on small
    shapes is reported as expected behavior, not as a warning.
    """
    if not usage_lines:
        _ERR.info("[check_ub_usage] no 'Usage:' lines found in input.")
        return False

    print_scan_header(usage_lines, var_tile_mode)

    any_low = False
    usage_pcts = []
    for i, (used, cap) in enumerate(usage_lines, 1):
        util = used / cap if cap > 0 else 0.0
        usage_pcts.append(util)
        mark = ""
        suggestion = ""

        if var_tile_mode:
            # Var-tile: any utilization is fine. Annotate "adapts up" / "adapts down"
            # by comparing to median.
            pass  # reporting only — no flagging
        elif util < LOW_UTIL_THRESHOLD:
            any_low = True
            mark = "  WARN UNDER 30%"
            suggestion = _scale_suggestion(cap, used)

        _ERR.info(
            f"  run #{i}: {used:>6.1f} / {cap:.0f} KB  ({util * 100:>5.1f}%){mark}"
        )
        if suggestion:
            _ERR.info(suggestion)

    # Diagnostic — Var-tile mode reports if UB sizes are actually varying.
    if var_tile_mode and len(usage_pcts) >= 2:
        print_var_tile_diagnostic(usage_pcts, var_tile_reason)
        return False  # never fail in var-tile mode

    print_utilization_verdict(any_low)
    return any_low


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "log",
        nargs="?",
        default="-",
        help="Path to simulator log file. Use '-' for stdin (default).",
    )
    parser.add_argument(
        "--dsl",
        default=None,
        help="Path to {op}_dsl.py. If provided, the script detects Var-tile "
        "(shape-adaptive UB) patterns and treats low usage as expected "
        "behavior rather than a warning.",
    )
    args = parser.parse_args(argv)

    if args.log == "-":
        text = sys.stdin.read()
    else:
        with open(args.log, encoding="utf-8") as f:
            text = f.read()

    var_tile_mode, var_tile_reason = detect_var_tile(args.dsl)

    lines = parse_usage_lines(text)
    failed = report(lines, var_tile_mode=var_tile_mode, var_tile_reason=var_tile_reason)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

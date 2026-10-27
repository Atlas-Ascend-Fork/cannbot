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
"""summarize_verify.py — 把一次 verify/profile 的产物解析为一行结论 JSON（优化项③）。

输入：某次 verify 的输出目录（含 perf_result.json；可选 msprof op_summary_*.csv）。
输出（stdout，一行 JSON）：
  {speedup, impl_avg_ms, framework_avg_ms, precision, passed_cases, total_cases,
   kernels: {name: {avg_us, launch_count}}, pipe: {mte2_ratio, mac_ratio, cube_util},
   bottleneck_tag}

瓶颈标签规则（写死，与 route.md 瓶颈分析口径一致）：
  - mte2_ratio >= 0.85                          -> MTE2-bound
  - mac_ratio <= 0.55 且 cube_util >= 0.95      -> MTE2-bound(tile 锁定)
  - scalar_ratio >= 0.30                        -> scalar-bound
  - cube_util < 0.30                            -> compute-idle
  - mac_ratio >= 0.70                           -> MAC-bound
  - 其他                                        -> mixed

用法:
  python3 summarize_verify.py --verify-dir <verify 输出目录> [--op-summary <op_summary_*.csv 路径>]

纯标准库实现（禁止 import torch/pandas，优化项 E1）。
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def _find_perf_result(verify_dir: Path) -> Path | None:
    """在 verify 目录中定位 perf_result.json（本目录优先，其次递归）。"""
    direct = verify_dir / "perf_result.json"
    if direct.is_file():
        return direct
    for candidate in sorted(verify_dir.rglob("perf_result.json")):
        return candidate
    return None


def _find_op_summary(verify_dir: Path, explicit: str | None) -> Path | None:
    """定位 msprof op_summary CSV：显式参数优先，其次目录内最新一个。"""
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    candidates = sorted(verify_dir.rglob("op_summary_*.csv"))
    return candidates[-1] if candidates else None


def _csv_ratio(row: dict, key: str) -> float:
    """Parse a CSV ratio field, returning 0.0 on empty/invalid."""
    raw = (row.get(key) or "").strip()
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def summarize_op_summary(csv_path: Path) -> dict:
    """解析 op_summary CSV -> {kernels, pipe}。

    kernels: {op_name: {avg_us, launch_count}}（同算子多行取均值、计次）
    pipe:    按任务时长加权的 mte2/mac/cube 比率（饱和视角的聚合）
    """
    per_op: dict[str, dict] = {}
    weighted = {"mte2": 0.0, "mac": 0.0, "cube": 0.0, "scalar": 0.0, "total": 0.0}
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("Op Name") or "").strip()
            if not name:
                continue
            try:
                dur = float((row.get("Task Duration(us)") or "0").strip() or 0)
            except ValueError:
                dur = 0.0
            entry = per_op.setdefault(name, {"sum_us": 0.0, "launch_count": 0})
            entry["sum_us"] += dur
            entry["launch_count"] += 1
            if dur <= 0:
                continue

            # aic_*_ratio 为该 kernel 内占比；cube 用 aic_core_utilization(%)（0-100）。
            weighted["mte2"] += _csv_ratio(row, "aic_mte2_ratio") * dur
            weighted["mac"] += _csv_ratio(row, "aic_mac_ratio") * dur
            weighted["scalar"] += _csv_ratio(row, "aic_scalar_ratio") * dur
            util_raw = (row.get("cube_utilization(%)") or row.get("aic_core_utilization(%)") or "").strip()
            try:
                cube = float(util_raw) if util_raw else 0.0
            except ValueError:
                cube = 0.0
            weighted["cube"] += (cube / 100.0) * dur
            weighted["total"] += dur

    kernels = {
        name: {
            "avg_us": round(v["sum_us"] / v["launch_count"], 1),
            "launch_count": v["launch_count"],
        }
        for name, v in sorted(per_op.items())
    }
    if weighted["total"] <= 0:
        return {"kernels": kernels, "pipe": None}
    pipe = {
        "mte2_ratio": round(weighted["mte2"] / weighted["total"], 3),
        "mac_ratio": round(weighted["mac"] / weighted["total"], 3),
        "cube_util": round(weighted["cube"] / weighted["total"], 3),
        "scalar_ratio": round(weighted["scalar"] / weighted["total"], 3),
    }
    return {"kernels": kernels, "pipe": pipe}


def bottleneck_tag(pipe: dict | None) -> str:
    """按写死规则给瓶颈标签；无 pipe 数据时 unknown。"""
    if not pipe:
        return "unknown"
    mte2 = pipe.get("mte2_ratio") or 0.0
    mac = pipe.get("mac_ratio") or 0.0
    cube = pipe.get("cube_util") or 0.0
    scalar = pipe.get("scalar_ratio") or 0.0
    if mte2 >= 0.85:
        return "MTE2-bound"
    if mac <= 0.55 and cube >= 0.95:
        return "MTE2-bound(tile 锁定)"
    if scalar >= 0.30:
        return "scalar-bound"
    if cube < 0.30:
        return "compute-idle"
    if mac >= 0.70:
        return "MAC-bound"
    return "mixed"


def main() -> int:
    parser = argparse.ArgumentParser(description="verify 产物 -> 一行结论 JSON")
    parser.add_argument("--verify-dir", required=True, help="verify 输出目录（含 perf_result.json）")
    parser.add_argument("--op-summary", default=None, help="msprof op_summary_*.csv 路径（默认在目录内自动发现）")
    args = parser.parse_args()

    verify_dir = Path(args.verify_dir)
    if not verify_dir.is_dir():
        sys.stdout.buffer.write((json.dumps(
        {"error": f"verify dir not found: {verify_dir}"}, indent=2) + "\n").encode("utf-8"))
        return 2

    perf_path = _find_perf_result(verify_dir)
    if perf_path is None:
        sys.stdout.buffer.write((json.dumps(
        {"error": f"perf_result.json not found under {verify_dir}"}, indent=2) + "\n").encode("utf-8"))
        return 2
    perf = json.loads(perf_path.read_text(encoding="utf-8"))

    result = {
        "speedup": perf.get("speedup_vs_torch"),
        "impl_avg_ms": (perf.get("implementation") or {}).get("avg_latency_ms"),
        "framework_avg_ms": (perf.get("framework") or {}).get("avg_latency_ms"),
        "precision": (
            "PASS" if perf.get("passed_cases") == perf.get("total_cases")
            and perf.get("total_cases", 0) > 0 else "FAIL"
        ),
        "passed_cases": perf.get("passed_cases"),
        "total_cases": perf.get("total_cases"),
        "kernels": {},
        "pipe": None,
    }
    # benchmark.py 内置 profiler 口径的 per-op 设备计时（无 msprof CSV 时的替代）。
    for side in ("implementation", "framework"):
        for name, op in ((perf.get(side) or {}).get("operators") or {}).items():
            result["kernels"].setdefault(
                name, {"avg_us": round(op.get("avg_us", 0.0), 1), "launch_count": 1}
            )

    csv_path = _find_op_summary(verify_dir, args.op_summary)
    if csv_path is not None:
        summarized = summarize_op_summary(csv_path)
        result["kernels"] = summarized["kernels"]
        result["pipe"] = summarized["pipe"]
        result["op_summary_csv"] = str(csv_path)

    result["bottleneck_tag"] = bottleneck_tag(result["pipe"])
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

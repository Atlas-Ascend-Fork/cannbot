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
"""b1_profile_table.py — 基线 profile 的 op 耗时/占比表（优化项F1）。

从 msprof op_summary CSV 确定性聚合出每个 op 的调用次数 / 总耗时 / 均值 / 占比，
作为 Round 1 B1 原子分解的量化锚点：LLM 只判断"哪些 op 可融合、如何拆原子"，
耗时与占比一律以本表为准，禁止凭感觉估算。

输入：--csv PATH...（一个或多个 op_summary CSV；--profile-dir 则自动 glob 其下
      op_summary_*.csv，多文件时聚合求和）
输出：markdown 表（默认 stdout）和/或 JSON（--format json / --out）。
      JSON：{total_us, ops: [{op_name, task_type, count, total_us, mean_us, pct}]}

排序：total_us 降序，同值按 op_name 字典序——确定性输出。纯标准库（E1）。
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

DURATION_COL = "Task Duration(us)"
NAME_COL = "Op Name"
TYPE_COL = "Task Type"


def iter_csv_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = [Path(p) for p in (args.csv or [])]
    if args.profile_dir:
        paths.extend(sorted(Path(args.profile_dir).glob("op_summary_*.csv")))
    return paths


def _accumulate_row(row: dict, stats: dict) -> int:
    """Accumulate one CSV row into stats; returns 1 if skipped, else 0."""
    name = (row.get(NAME_COL) or "").strip()
    try:
        dur = float(row.get(DURATION_COL) or 0.0)
    except ValueError:
        return 1
    entry = stats.setdefault(name, {"op_name": name, "task_type": "", "count": 0, "total_us": 0.0})
    entry["count"] += 1
    entry["total_us"] += dur
    if not entry["task_type"]:
        entry["task_type"] = (row.get(TYPE_COL) or "").strip()
    return 0


def aggregate(paths: list[Path]) -> dict:
    """按 op_name 聚合 count / total_us；缺失列或非数值行安全跳过。"""
    stats: dict[str, dict] = {}
    skipped_rows = 0
    used_files = 0
    for path in paths:
        if not path.is_file():
            continue
        used_files += 1
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or NAME_COL not in reader.fieldnames \
                    or DURATION_COL not in reader.fieldnames:
                skipped_rows += 1
                continue
            for row in reader:
                skipped_rows += _accumulate_row(row, stats)

    total_us = sum(e["total_us"] for e in stats.values())
    ops = sorted(stats.values(), key=lambda e: (-e["total_us"], e["op_name"]))
    for e in ops:
        e["mean_us"] = round(e["total_us"] / e["count"], 2) if e["count"] else 0.0
        e["total_us"] = round(e["total_us"], 2)
        e["pct"] = round(e["total_us"] / total_us * 100, 2) if total_us > 0 else 0.0
    return {
        "total_us": round(total_us, 2),
        "files_used": used_files,
        "rows_skipped": skipped_rows,
        "ops": ops,
    }


def to_markdown(data: dict) -> str:
    lines = [
        "## 基线 op 耗时表（b1_profile_table.py，msprof op_summary 聚合）",
        "",
        f"- 合计：{data['total_us']:.1f} us（{data['files_used']} 个 CSV，"
        f"跳过 {data['rows_skipped']} 行无效数据）",
        "",
        "| op_name | task_type | count | total_us | mean_us | 占比 |",
        "|---------|-----------|-------|----------|---------|------|",
    ]
    for e in data["ops"]:
        lines.append(
            f"| {e['op_name']} | {e['task_type'] or '-'} | {e['count']} "
            f"| {e['total_us']:.1f} | {e['mean_us']:.2f} | {e['pct']:.2f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="基线 profile op 耗时/占比表（F1）")
    parser.add_argument("--csv", nargs="*", default=None, help="op_summary CSV 路径（可多个）")
    parser.add_argument("--profile-dir", default=None, help="目录：自动 glob 其下 op_summary_*.csv")
    parser.add_argument("--format", choices=("md", "json"), default="md", help="输出格式（默认 md）")
    parser.add_argument("--out", default=None, help="输出文件路径（缺省 stdout）")
    args = parser.parse_args()

    paths = iter_csv_paths(args)
    if not paths:
        sys.stdout.buffer.write((json.dumps(
        {"error": "no input: pass --csv or --profile-dir"}, indent=2) + "\n").encode("utf-8"))
        return 2

    data = aggregate(paths)
    if data["files_used"] == 0:
        result = dict(data)
        result["error"] = "no readable op_summary CSV among inputs"
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2

    if args.format == "json":
        text = json.dumps(data, ensure_ascii=False) + "\n"
    else:
        text = to_markdown(data)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

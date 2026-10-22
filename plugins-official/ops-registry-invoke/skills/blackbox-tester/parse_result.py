#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""解析 TTK aclnn result.csv，统计 total/pass/fail/skip 并给出退出码门禁。

用法：
  parse_result.py <result.csv> [--expect-total N] [--by-layer <testcases_dir>] [--negative|--smoke]
退出码 0（默认正向门禁）当且仅当 total>0 且 pass==total 且 fail==skip==0。
给 --expect-total 时还需要 total==N。--negative 用于 L2 负向/预期失败套件；--smoke 用于基础设施冒烟。
"""

import argparse
import csv
import glob
import logging
import os
import re
import sys

LOG = logging.getLogger(__name__)
STATUS_KEYS = ("precision_status", "status", "result", "compare_result")
PASS_TOKENS = {"pass", "passed", "true", "success", "ok"}
SKIP_TOKENS = {"skip", "skipped", "soc_not_support", "not_support", "disabled"}
DUP_SUFFIX = re.compile(r"^_.+_dup\d+$")


def norm(value):
    return (value or "").strip().lower()


def classify(row):
    keys = {key.lower(): key for key in row}
    for candidate in STATUS_KEYS:
        if candidate not in keys:
            continue
        value = norm(row[keys[candidate]])
        if not value:
            continue
        if value in SKIP_TOKENS:
            return "skip"
        if value in PASS_TOKENS:
            return "pass"
        return "fail"
    return "fail"


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize(path):
    rows = _read_csv(path)
    stats = {
        "total": len(rows),
        "pass": 0,
        "fail": 0,
        "skip": 0,
        "fails": [],
        "passes": [],
    }
    for row in rows:
        status = classify(row)
        stats[status] += 1
        name = row.get("testcase_name") or row.get("case_name") or "?"
        if status != "pass":
            stats["fails"].append((name, status))
        else:
            stats["passes"].append(name)
    return stats


def smoke_ok(path):
    rows = _read_csv(path)
    if len(rows) != 1:
        return False, f"expected exactly 1 row, got {len(rows)}"
    keys = {key.lower(): key for key in rows[0]}
    key = keys.get("precision_status")
    status = (rows[0].get(key) or "").strip().upper() if key else ""
    if status not in {"PASS", "FAIL"}:
        return (
            False,
            f"precision_status must be PASS or FAIL, got {status or '<missing>'}",
        )
    return True, status


def _layer_files(testcases_dir):
    patterns = ("*_l[0-9]_functional.csv", "*_l[0-9]_exception.csv")
    paths = {
        file_name
        for pattern in patterns
        for file_name in glob.glob(os.path.join(testcases_dir, pattern))
    }
    return sorted(paths)


def _layer_name(path):
    match = re.search(
        r"_l(\d)_(?:functional|exception)\.csv$", os.path.basename(path), re.IGNORECASE
    )
    return f"L{match.group(1)}" if match else None


def load_layer_map(testcases_dir):
    """读取分层 CSV 并返回 ``{testcase_name: 'L0'|'L1'|...}``。"""
    layer_map = {}
    for path in _layer_files(testcases_dir):
        layer = _layer_name(path)
        if not layer:
            continue
        for row in _read_csv(path):
            name = row.get("testcase_name") or row.get("case_name")
            if name:
                layer_map[name] = layer
    if not layer_map:
        raise FileNotFoundError(f"no layer CSVs under {testcases_dir}")
    return layer_map


def resolve_layer(name, layer_map):
    """精确匹配，再去重名用例后缀做最长已知前缀归并；仍找不到返回 None。"""
    if name in layer_map:
        return layer_map[name]
    for candidate in sorted(layer_map, key=len, reverse=True):
        prefix_length = len(candidate)
        suffix = name[prefix_length:]
        if name.startswith(candidate) and DUP_SUFFIX.match(suffix):
            return layer_map[candidate]
    return None


def _read_layer_stats(path, layer_map):
    stats = {}
    unmapped = []
    for row in _read_csv(path):
        name = row.get("testcase_name") or row.get("case_name") or "?"
        layer = resolve_layer(name, layer_map)
        if layer is None:
            unmapped.append(name)
            continue
        current = stats.setdefault(layer, {"total": 0, "pass": 0, "fail": 0, "skip": 0})
        status = classify(row)
        current["total"] += 1
        current[status] += 1
    return stats, unmapped


def by_layer(path, testcases_dir):
    layer_map = load_layer_map(testcases_dir)
    stats, unmapped = _read_layer_stats(path, layer_map)
    for layer in sorted(stats):
        current = stats[layer]
        LOG.info(
            "  %s: total=%d pass=%d fail=%d skip=%d",
            layer,
            current["total"],
            current["pass"],
            current["fail"],
            current["skip"],
        )
    if unmapped:
        LOG.info(
            "  UNMAPPED: %d case(s) not in layer CSVs: %s", len(unmapped), unmapped[:10]
        )
    return unmapped


def _build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_csv")
    parser.add_argument("--expect-total", type=int, default=None)
    parser.add_argument(
        "--by-layer",
        default=None,
        metavar="TESTCASES_DIR",
        help="分层 CSV 目录，输出 L0/L1/L2 分层统计（不影响门禁）",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--negative", action="store_true", help="负向套件：算子应拒绝全部用例"
    )
    mode.add_argument(
        "--smoke", action="store_true", help="基础设施冒烟：恰好 1 行，精度 FAIL 不拦"
    )
    return parser


def _smoke_gate(path):
    ok, detail = smoke_ok(path)
    LOG.info("SMOKE-GATE: %s", f"PASS({detail})" if ok else f"FAIL({detail})")
    return 0 if ok else 1


def _negative_gate(stats, expect_total):
    for name in stats["passes"][:50]:
        LOG.info("  [UNEXPECTED-PASS 算子未拒绝非法输入] %s", name)
    ok = stats["total"] > 0 and stats["pass"] == 0
    if expect_total is not None and stats["total"] != expect_total:
        ok = False
        LOG.info("MISMATCH: total %d != expected %d", stats["total"], expect_total)
    LOG.info(
        "NEGATIVE-GATE: %s",
        "PASS(全部按预期被拒绝)" if ok else "FAIL(存在未被拒绝的非法用例)",
    )
    return 0 if ok else 1


def _positive_gate(stats, expect_total):
    for name, status in stats["fails"][:50]:
        LOG.info("  [%s] %s", status.upper(), name)
    ok = (
        stats["total"] > 0
        and stats["pass"] == stats["total"]
        and stats["fail"] == 0
        and stats["skip"] == 0
    )
    if expect_total is not None and stats["total"] != expect_total:
        ok = False
        LOG.info("MISMATCH: total %d != expected %d", stats["total"], expect_total)
    LOG.info("GATE: %s", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv=None):
    args = _build_parser().parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    stats = summarize(args.result_csv)
    LOG.info(
        "total=%d pass=%d fail=%d skip=%d",
        stats["total"],
        stats["pass"],
        stats["fail"],
        stats["skip"],
    )
    if args.by_layer:
        by_layer(args.result_csv, args.by_layer)
    if args.smoke:
        return _smoke_gate(args.result_csv)
    if args.negative:
        return _negative_gate(stats, args.expect_total)
    return _positive_gate(stats, args.expect_total)


if __name__ == "__main__":
    sys.exit(main())

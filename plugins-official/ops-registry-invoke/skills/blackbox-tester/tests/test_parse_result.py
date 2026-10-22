#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""parse_result 门禁与分层统计回归测试。"""

import csv
import os

import parse_result as pr  # noqa: E402  # 需 PYTHONPATH 指向 skill 根

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _write(tmp_path, rows, header):
    path = tmp_path / "r.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return str(path)


def test_all_pass_gate_ok(tmp_path):
    path = _write(
        tmp_path,
        [["c1", "PASS"], ["c2", "PASS"]],
        ["testcase_name", "precision_status"],
    )
    stats = pr.summarize(path)
    assert (stats["total"], stats["pass"], stats["fail"], stats["skip"]) == (2, 2, 0, 0)


def test_any_fail_gate_fail(tmp_path):
    path = _write(
        tmp_path,
        [["c1", "PASS"], ["c2", "FAIL"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.main([path]) == 1


def test_skip_counts_and_fails_gate(tmp_path):
    path = _write(
        tmp_path,
        [["c1", "PASS"], ["c2", "SKIP"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.summarize(path)["skip"] == 1
    assert pr.main([path]) == 1


def test_empty_is_fail(tmp_path):
    path = _write(tmp_path, [], ["testcase_name", "precision_status"])
    assert pr.main([path]) == 1


def test_smoke_accepts_one_pass_or_precision_fail(tmp_path):
    path = _write(tmp_path, [["c1", "PASS"]], ["testcase_name", "precision_status"])
    assert pr.main([path, "--smoke"]) == 0
    path = _write(tmp_path, [["c1", "FAIL"]], ["testcase_name", "precision_status"])
    assert pr.main([path, "--smoke"]) == 0


def test_smoke_rejects_infrastructure_status_or_wrong_count(tmp_path):
    path = _write(
        tmp_path, [["c1", "GOLDEN_FAILURE"]], ["testcase_name", "precision_status"]
    )
    assert pr.main([path, "--smoke"]) == 1
    path = _write(
        tmp_path,
        [["c1", "PASS"], ["c2", "PASS"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.main([path, "--smoke"]) == 1


def test_expect_total_mismatch_fails(tmp_path):
    path = _write(tmp_path, [["c1", "PASS"]], ["testcase_name", "precision_status"])
    assert pr.main([path, "--expect-total", "2"]) == 1


def test_real_fixture_parses(tmp_path):
    stats = pr.summarize(os.path.join(FIX, "result_sample.csv"))
    assert stats["total"] >= 1


def test_negative_gate_all_rejected_ok(tmp_path):
    path = _write(
        tmp_path,
        [["c1", "NO_OUTPUT"], ["c2", "FAIL"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.main([path, "--negative"]) == 0


def test_negative_gate_unexpected_pass_fails(tmp_path):
    path = _write(
        tmp_path,
        [["c1", "NO_OUTPUT"], ["c2", "PASS"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.main([path, "--negative"]) == 1


def test_negative_gate_empty_fails(tmp_path):
    path = _write(tmp_path, [], ["testcase_name", "precision_status"])
    assert pr.main([path, "--negative"]) == 1


def test_negative_gate_requires_full_expected_count(tmp_path):
    path = _write(
        tmp_path, [["c1", "NO_OUTPUT"]], ["testcase_name", "precision_status"]
    )
    assert pr.main([path, "--negative", "--expect-total", "2"]) == 1


def _write_layer_csvs(directory):
    os.makedirs(directory, exist_ok=True)
    levels = [
        ("l0", "functional", ["op_L0_001", "op_L0_002"]),
        ("l1", "functional", ["op_L1_001"]),
    ]
    for level, suffix, names in levels:
        path = os.path.join(directory, f"aclnnOp_{level}_{suffix}.csv")
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["testcase_name"])
            writer.writerows([[name] for name in names])
    return directory


def test_by_layer_counts(tmp_path):
    directory = _write_layer_csvs(str(tmp_path / "tc"))
    path = _write(
        tmp_path,
        [["op_L0_001", "PASS"], ["op_L0_002", "FAIL"], ["op_L1_001", "PASS"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.by_layer(path, directory) == []


def test_by_layer_resolves_dup_suffix(tmp_path):
    directory = _write_layer_csvs(str(tmp_path / "tc"))
    path = _write(
        tmp_path,
        [["op_L0_001", "PASS"], ["op_L0_001_aclnnOp_dup0", "FAIL"]],
        ["testcase_name", "precision_status"],
    )
    assert pr.by_layer(path, directory) == []


def test_by_layer_unmapped_reported(tmp_path):
    directory = _write_layer_csvs(str(tmp_path / "tc"))
    path = _write(
        tmp_path, [["ghost_case", "FAIL"]], ["testcase_name", "precision_status"]
    )
    assert pr.by_layer(path, directory) == ["ghost_case"]


def test_failure_words_containing_pass_tokens_do_not_pass(tmp_path):
    for status in ("NOT_PASS", "NOT_OK", "UNSUCCESSFUL", "PASS_WITH_FAILURE"):
        path = _write(
            tmp_path, [["bad", status]], ["testcase_name", "precision_status"]
        )
        assert pr.classify({"precision_status": status}) == "fail"
        assert pr.main([path]) == 1


def test_known_status_tokens_still_accept_case_and_whitespace():
    for value in ("PASS", " passed ", "True", "SUCCESS", "OK"):
        assert pr.classify({"status": value}) == "pass"
    for value in ("SKIP", " skipped ", "SOC_NOT_SUPPORT", "NOT_SUPPORT", "DISABLED"):
        assert pr.classify({"precision_status": value}) == "skip"

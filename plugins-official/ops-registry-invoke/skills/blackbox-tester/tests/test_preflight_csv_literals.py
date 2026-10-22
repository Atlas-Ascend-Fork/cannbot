#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""CSV syntax cannot become PASS when optional vendor checks are skipped."""

import csv

import pytest

import preflight


@pytest.mark.parametrize("symbols", [None, {"aclnnFoo", "aclnnFooGetWorkspaceSize"}])
@pytest.mark.parametrize(
    "literals",
    [
        ("garbage", "{}"),
        ("[(8,), (8,)]", "{}"),
        ("", "{}"),
        ("((8,), (8,))", "{'dim':"),
        ("((8,), (8,))", "[]"),
        ("((8,), (8,))", "None"),
    ],
)
def test_invalid_csv_literals_fail_main(
    tmp_path, monkeypatch, caplog, symbols, literals
):
    shapes, attributes = literals
    path = tmp_path / "cases.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(
            [
                ["testcase_name", "api_name", "tensor_view_shapes", "attributes"],
                ["broken_case", "aclnnFoo", shapes, attributes],
            ]
        )
    # Mock only vendor deployment discovery; parsing and public main stay real.
    monkeypatch.setattr(preflight, "so_symbols", lambda *_: symbols)
    include = tmp_path / "vendors/Foo/op_api/include"
    include.mkdir(parents=True)
    (include / "foo.h").write_text(
        "aclnnFooGetWorkspaceSize(const aclTensor *x, const aclTensor *out, "
        "uint64_t *workspaceSize, aclOpExecutor **executor);"
    )
    assert preflight.main([str(path), "--optype", "Foo", "--opp", str(tmp_path)]) == 1
    assert "broken_case" in caplog.text


@pytest.mark.parametrize("attributes", ["{}", "", "{'dim': 0}"])
def test_valid_literals_remain_accepted_without_vendor(
    tmp_path, monkeypatch, attributes
):
    path = tmp_path / "cases.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(
            [
                ["testcase_name", "api_name", "tensor_view_shapes", "attributes"],
                ["valid_case", "aclnnFoo", "((8,), (8,))", attributes],
            ]
        )
    monkeypatch.setattr(preflight, "so_symbols", lambda *_: None)
    assert preflight.main([str(path), "--optype", "Foo", "--opp", str(tmp_path)]) == 0

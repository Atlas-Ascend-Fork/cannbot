#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Preserve canonical automatic-offset placeholders through CSV merging."""

import ast
import csv

import pytest

from merge_cases import merge


@pytest.mark.parametrize(
    "shapes, offsets",
    [
        (((2,), (2,)), (None, 0)),
        ((None, (2,)), (None, 0)),
        ((((2,), None), (4,)), ((1, None), 0)),
        ((((2,), (3,)), (4,)), ((None, 2), 0)),
    ],
)
def test_merge_preserves_ttk_none_offset_placeholder(tmp_path, shapes, offsets):
    cases = tmp_path / "cases"
    cases.mkdir()
    with (cases / "op_l1_functional.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        csv.writer(handle).writerows(
            [
                ["testcase_name", "tensor_view_shapes", "tensor_view_offsets"],
                ["automatic_offset", repr(shapes), repr(offsets)],
            ]
        )
    positive = tmp_path / "positive.csv"
    assert merge(cases, positive, tmp_path / "negative.csv") == (1, 0)
    with positive.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert ast.literal_eval(row["tensor_view_shapes"]) == shapes
    assert ast.literal_eval(row["tensor_view_offsets"]) == offsets


@pytest.mark.parametrize("offset", [True, "not_an_offset"])
def test_other_invalid_offset_leaves_still_rejected(tmp_path, offset):
    cases = tmp_path / "cases"
    cases.mkdir()
    with (cases / "op_l0_functional.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        csv.writer(handle).writerows(
            [
                ["testcase_name", "tensor_view_shapes", "tensor_view_offsets"],
                ["bad", "((2,),)", repr((offset,))],
            ]
        )
    with pytest.raises(ValueError, match="offset"):
        merge(cases, tmp_path / "positive.csv", tmp_path / "negative.csv")

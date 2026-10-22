#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Validation failures must leave both existing output cohorts untouched."""

import csv

import pytest

from merge_cases import merge


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


@pytest.mark.parametrize("invalid", ["duplicate", "offset"])
@pytest.mark.parametrize("preexisting", [True, False])
def test_invalid_l2_does_not_replace_positive_output(tmp_path, invalid, preexisting):
    cases = tmp_path / "cases"
    cases.mkdir()
    write_csv(cases / "op_l0_functional.csv", [["testcase_name"], ["new-positive"]])
    rows = (
        [["testcase_name"], ["same"], ["same"]]
        if invalid == "duplicate"
        else [
            ["testcase_name", "tensor_view_shapes", "tensor_view_offsets"],
            ["negative", "((2,), (2,))", "((0,),)"],
        ]
    )
    write_csv(cases / "op_l2_exception.csv", rows)
    positive, negative = tmp_path / "positive.csv", tmp_path / "negative.csv"
    if preexisting:
        positive.write_text("previous positives")
        negative.write_text("previous negatives")
    with pytest.raises(ValueError):
        merge(cases, positive, negative)
    if preexisting:
        assert positive.read_text() == "previous positives"
        assert negative.read_text() == "previous negatives"
    else:
        assert not positive.exists() and not negative.exists()

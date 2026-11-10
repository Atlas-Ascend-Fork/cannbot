#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Column-name merging must reject ambiguous data rather than discard it."""

import csv

import pytest

from merge_cases import merge


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


@pytest.mark.parametrize(
    "header, row, diagnostic",
    [
        (
            ["testcase_name", "attributes", "attributes"],
            ["case", "{'axis': 1}", "{'keepDims': True}"],
            ":1: duplicate CSV header columns: attributes",
        ),
        (
            ["testcase_name", "attributes"],
            ["case", "{'axis': 1}", "unmapped value"],
            ":2: extra CSV values without a column name",
        ),
        (
            ["testcase_name", "testcase_name"],
            ["first", "second"],
            ":1: duplicate CSV header columns: testcase_name",
        ),
    ],
)
def test_ambiguous_csv_columns_are_rejected(tmp_path, header, row, diagnostic):
    cases = tmp_path / "cases"
    cases.mkdir()
    write_csv(cases / "op_l0_functional.csv", [header, row])
    with pytest.raises(ValueError, match=r"op_l0_functional\.csv") as error:
        merge(cases, tmp_path / "positive.csv", tmp_path / "negative.csv")
    assert str(error.value) == str(cases / "op_l0_functional.csv") + diagnostic

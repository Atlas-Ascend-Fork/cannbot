# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared leaf-level comparison result helpers for the accuracy policies."""

from __future__ import annotations

from npu_compare_common import (
    CaseCompareResult,
    InputInfo,
    OutputLeaf,
    case_result,
)


def unsupported_output_type_result(
    leaf: OutputLeaf,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
) -> CaseCompareResult:
    return case_result(
        passed=False,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=None,
        comparison_path="unsupported-output-type",
        message=(
            f"FAIL case '{case_id}' produced non-tensor output at {leaf.path}: "
            f"expected Tensor, got expected {type(leaf.golden).__name__} "
            f"and actual {type(leaf.actual).__name__}."
        ),
        diagnostics={
            "failure_stage": "unsupported_output_type",
            "output_path": leaf.path,
            "expected_type": type(leaf.golden).__name__,
            "actual_type": type(leaf.actual).__name__,
        },
    )

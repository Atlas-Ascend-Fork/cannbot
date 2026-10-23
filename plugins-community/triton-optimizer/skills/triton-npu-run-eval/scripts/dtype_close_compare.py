# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Direct dtype-aware close comparison for Helix operator results.

This policy deliberately does not use ``compute`` or input dtype. In
pseudocode, per case:

    leaves = traverse_matching_output_structure(actual, golden)
    if the structure differs:
        run assert_close on the full outputs to obtain its failure message
        return that failure

    for each leaf:
        fail if actual or golden is not a Tensor
        actual, golden = detach_and_move_to_cpu(leaf)
        rtol, atol = tolerance_table[golden.dtype or float32_fallback]
        replace rtol or atol with a finite, non-negative environment override
        try:
            torch.testing.assert_close(
                actual, golden, rtol=rtol, atol=atol, equal_nan=True
            )
        except AssertionError:
            return a Helix failure with PyTorch's message and the tolerances

    pass only if every leaf passes.

``assert_close`` owns shape and dtype checks, the close bound, NaN position
handling, and Inf comparison. Helix adds stable diagnostics, including the
selected tolerances and an optional maximum absolute difference. This module
implements per-case comparison only; public mode selection and artifact
validation belong to ``npu_compare.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import os

import torch

from compare_leaves import unsupported_output_type_result
from env_registry import HELIX_DTYPE_CLOSE_ATOL, HELIX_DTYPE_CLOSE_RTOL
from npu_compare_common import (
    CaseCompareResult,
    InputInfo,
    OutputLeaf,
    OutputStructureError,
    case_result,
    traverse_output_leaves,
)


DTYPE_CLOSE_TOLERANCES = {
    "float64": {"rtol": 1e-5, "atol": 1e-8},
    "complex128": {"rtol": 1e-5, "atol": 1e-8},
    "float32": {"rtol": 1e-4, "atol": 1e-5},
    "hifloat32": {"rtol": 1e-4, "atol": 1e-5},
    "complex64": {"rtol": 1e-4, "atol": 1e-5},
    "float16": {"rtol": 5e-4, "atol": 5e-5},
    "bfloat16": {"rtol": 1e-3, "atol": 1e-4},
    "float8_e4m3": {"rtol": 1e-2, "atol": 1e-3},
    "float8_e5m2": {"rtol": 1e-2, "atol": 1e-3},
    "fallback": {"rtol": 1e-4, "atol": 1e-5},
}


def compare_dtype_close_case(
    *,
    case_id: str,
    actual: object,
    golden: object,
    compute: bool,
) -> CaseCompareResult:
    input_info = InputInfo(input_type="no_tensor", input_dtype=None)
    traversal = traverse_output_leaves(actual, golden)
    if traversal.error is not None:
        return _structure_error_result(
            actual=actual,
            golden=golden,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            error=traversal.error,
        )
    leaf_results = [
        _compare_dtype_close_leaf(leaf, case_id=case_id, compute=compute, input_info=input_info)
        for leaf in traversal.leaves
    ]
    failed = next((result for result in leaf_results if not result.passed), None)
    if failed is not None:
        return failed
    return _dtype_close_pass_result(case_id, compute, input_info, leaf_results)


def _dtype_close_pass_result(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    leaf_results: list[CaseCompareResult],
) -> CaseCompareResult:
    if not leaf_results:
        return case_result(
            passed=True,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            output_dtype=None,
            comparison_path="dtype-close",
            message=f"PASS case '{case_id}' has no comparable outputs.",
            diagnostics={"output_path": "output", "leaf_count": 0},
        )
    first = leaf_results[0]
    output_dtype = (
        first.output_dtype if len({result.output_dtype for result in leaf_results}) == 1 else "multiple"
    )
    diagnostics: Mapping[str, object]
    if len(leaf_results) == 1:
        diagnostics = {**dict(first.diagnostics), "leaf_count": 1}
    else:
        diagnostics = {"output_path": "output", "leaf_count": len(leaf_results)}
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=output_dtype,
        comparison_path="dtype-close",
        message=f"PASS case '{case_id}' matched across {len(leaf_results)} output leaf/leaves.",
        diagnostics=diagnostics,
    )


def _compare_dtype_close_leaf(
    leaf: OutputLeaf,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
) -> CaseCompareResult:
    if not isinstance(leaf.actual, torch.Tensor) or not isinstance(leaf.golden, torch.Tensor):
        return unsupported_output_type_result(leaf, case_id=case_id, compute=compute, input_info=input_info)
    actual_cpu = _normalize_tensor(leaf.actual)
    golden_cpu = _normalize_tensor(leaf.golden)
    output_dtype = _output_dtype(golden_cpu)
    tolerances = _tolerances_for_output(golden_cpu)
    diagnostics: dict[str, object] = {
        "output_path": leaf.path,
        "output_dtype": output_dtype,
        "tensor_shape": tuple(golden_cpu.shape),
    }
    diagnostics.update(tolerances)
    max_diff = _max_abs_diff(actual_cpu, golden_cpu)
    if max_diff is not None:
        diagnostics["max_abs_diff"] = max_diff
    try:
        torch.testing.assert_close(
            actual_cpu,
            golden_cpu,
            atol=tolerances["atol"],
            rtol=tolerances["rtol"],
            equal_nan=True,
        )
    except AssertionError as exc:
        return case_result(
            passed=False,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            output_dtype=output_dtype,
            comparison_path="dtype-close",
            message=f"FAIL case '{case_id}' assert_close failed at {leaf.path}.",
            diagnostics={
                **diagnostics,
                "failure_stage": "assert_close",
                "assert_close_message": str(exc),
            },
        )
    return _dtype_close_leaf_pass(
        case_id, compute, input_info,
        output_dtype=output_dtype, output_path=leaf.path, diagnostics=diagnostics,
    )


def _dtype_close_leaf_pass(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    *,
    output_dtype: str,
    output_path: object,
    diagnostics: dict[str, object],
) -> CaseCompareResult:
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=output_dtype,
        comparison_path="dtype-close",
        message=f"PASS case '{case_id}' matched dtype-close output at {output_path}.",
        diagnostics=diagnostics,
    )


def _structure_error_result(
    *,
    actual: object,
    golden: object,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    error: OutputStructureError,
) -> CaseCompareResult:
    try:
        torch.testing.assert_close(actual, golden, equal_nan=True)
    except AssertionError as exc:
        return case_result(
            passed=False,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            output_dtype=None,
            comparison_path="dtype-close",
            message=f"FAIL case '{case_id}' assert_close failed at {error.path}.",
            diagnostics={
                "failure_stage": "assert_close",
                "output_path": error.path,
                "assert_close_message": str(exc),
            },
        )
    raise AssertionError(f"output traversal reported {error.kind} but assert_close passed")


def _normalize_tensor(value: torch.Tensor) -> torch.Tensor:
    return value.detach().cpu()


def _tolerances_for_output(value: torch.Tensor) -> dict[str, float]:
    output_dtype = _output_dtype(value)
    matched = DTYPE_CLOSE_TOLERANCES[_tolerance_key(output_dtype)]
    tolerances = {"atol": float(matched["atol"]), "rtol": float(matched["rtol"])}
    atol = _optional_env_float(HELIX_DTYPE_CLOSE_ATOL)
    rtol = _optional_env_float(HELIX_DTYPE_CLOSE_RTOL)
    if atol is not None:
        tolerances["atol"] = atol
    if rtol is not None:
        tolerances["rtol"] = rtol
    return tolerances


def _optional_env_float(name: str) -> float | None:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return None
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a float, got {raw_value!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative float, got {raw_value!r}")
    return value


def _output_dtype(value: torch.Tensor) -> str:
    return str(value.dtype).replace("torch.", "")


def _max_abs_diff(actual: torch.Tensor, golden: torch.Tensor) -> float | None:
    if actual.shape != golden.shape or actual.dtype != golden.dtype:
        return None
    if actual.numel() == 0:
        return 0.0
    try:
        diff = (actual - golden).abs()
    except RuntimeError:
        diff = (actual.to(dtype=torch.float32) - golden.to(dtype=torch.float32)).abs()
    return float(diff.max().item())


def _tolerance_key(output_dtype: str) -> str:
    if output_dtype.startswith("float8_e4m3"):
        return "float8_e4m3"
    if output_dtype.startswith("float8_e5m2"):
        return "float8_e5m2"
    if output_dtype in DTYPE_CLOSE_TOLERANCES:
        return output_dtype
    return "fallback"

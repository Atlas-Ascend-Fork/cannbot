# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""NPU-contract accuracy comparison for Helix operator results.

This is the compatibility/default policy. In pseudocode, per case:

    leaves = traverse_matching_output_structure(actual, golden)
    fail if the structure differs or a leaf is not a Tensor
    input_kind = infer_float_or_integer_input(inputs)

    for each leaf:
        actual, golden = detach_and_move_to_cpu(leaf)
        path = select(compute, input_kind, golden.dtype)

        if path == non_compute:
            fail unless shape and dtype match
            pass only if the raw tensor bytes match

        fail unless shapes match
        actual = cast(actual, golden.dtype)
        fail unless NaN masks, Inf masks, and Inf signs match

        if path == bool_output:
            pass only if values are equal
        if path == integer_compute:
            pass only if abs(actual - golden) <= 0
        if path == quantized_float_to_integer:
            pass only if abs(actual - golden) <= 1
        if path == floating_point_compute:
            finite_actual, finite_golden = finite_values(actual, golden)
            error_cap = atol[dtype] + rtol[dtype] * abs(finite_golden)
            fail if any abs(finite_actual - finite_golden) exceeds error_cap
            matched = small_value_rule OR relative_error_rule, per element
            fail if mean(matched) < 0.90
            fail if mean(relative_error) >= rel_threshold[dtype]
            otherwise pass

    pass only if every leaf passes; otherwise return the first failed leaf.

For floating/complex leaves, ``finite_values`` excludes NaN and Inf; complex
values are evaluated through their real and imaginary components. Unsupported
output dtypes fail explicitly. This module implements per-case comparison only;
public mode selection and artifact validation belong to ``npu_compare.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import torch

from compare_leaves import unsupported_output_type_result
from npu_compare_common import (
    CaseCompareResult,
    InputInfo,
    OutputLeaf,
    OutputStructureError,
    case_result,
    traverse_output_leaves,
)


FLOAT_FAMILY = {
    "float8_e4m3",
    "float8_e4m3fn",
    "float8_e4m3fnuz",
    "float8_e5m2",
    "float8_e5m2fnuz",
    "float16",
    "bfloat16",
    "float32",
    "float64",
}
COMPLEX_FAMILY = {"complex64", "complex128"}
INPUT_FLOAT_FAMILY = FLOAT_FAMILY | COMPLEX_FAMILY
OUTPUT_FLOAT_FAMILY = FLOAT_FAMILY | COMPLEX_FAMILY
INTEGER_FAMILY = {"bool", "uint8", "int8", "int16", "int32", "int64"}
DTYPE_PRIORITY = {
    "complex128": 0,
    "complex64": 1,
    "float64": 2,
    "float32": 3,
    "float16": 4,
    "bfloat16": 5,
    "float8_e4m3": 6,
    "float8_e4m3fn": 6,
    "float8_e4m3fnuz": 6,
    "float8_e5m2": 7,
    "float8_e5m2fnuz": 7,
    "int64": 8,
    "int32": 9,
    "int16": 10,
    "int8": 11,
    "uint8": 12,
    "bool": 13,
}
MATCH_THRESHOLDS = {
    "float16": {"small_value_threshold": 2 ** -11, "small_value_error": 2 ** -16, "rel_threshold": 2 ** -10},
    "bfloat16": {"small_value_threshold": 2 ** -8, "small_value_error": 2 ** -16, "rel_threshold": 2 ** -7},
    "float32": {"small_value_threshold": 2 ** -14, "small_value_error": 2 ** -30, "rel_threshold": 2 ** -13},
    "hifloat32": {"small_value_threshold": 2 ** -12, "small_value_error": 2 ** -28, "rel_threshold": 2 ** -11},
    "float8_e4m3": {"small_value_threshold": 2 ** -4, "small_value_error": 2 ** -6, "rel_threshold": 2 ** -3},
    "float8_e5m2": {"small_value_threshold": 2 ** -3, "small_value_error": 2 ** -5, "rel_threshold": 2 ** -2},
    "fallback": {"small_value_threshold": 2 ** -14, "small_value_error": 2 ** -30, "rel_threshold": 2 ** -13},
}
MAX_ERROR_THRESHOLDS = {
    "float16": {"atol": 9e-2, "rtol": 2 ** -10},
    "bfloat16": {"atol": 1e-1, "rtol": 2 ** -7},
    "float32": {"atol": 1e-3, "rtol": 2 ** -13},
    "hifloat32": {"atol": 1e-3, "rtol": 2 ** -13},
    "float8_e4m3": {"atol": 1e-3, "rtol": 2 ** -13},
    "float8_e5m2": {"atol": 1e-3, "rtol": 2 ** -13},
    "fallback": {"atol": 1e-3, "rtol": 2 ** -13},
}


def compare_npu_contract_case(
    *,
    case_id: str,
    actual: object,
    golden: object,
    inputs: object,
    compute: bool,
) -> CaseCompareResult:
    input_info = _infer_input_info(inputs)
    traversal = traverse_output_leaves(actual, golden)
    if traversal.error is not None:
        return _structure_error_result(case_id, compute, input_info, traversal.error)
    leaf_results = [
        compare_npu_contract_leaf(leaf, case_id=case_id, compute=compute, input_info=input_info)
        for leaf in traversal.leaves
    ]
    if not leaf_results:
        return case_result(
            passed=True,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            output_dtype=None,
            comparison_path="empty-output",
            message=f"PASS case '{case_id}' has no comparable outputs.",
            diagnostics={"case_id": case_id, "output_path": "output"},
        )
    failed = next((result for result in leaf_results if not result.passed), None)
    if failed is not None:
        return failed
    return _npu_contract_pass_result(case_id, compute, input_info, leaf_results)


def _npu_contract_pass_result(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    leaf_results: list[CaseCompareResult],
) -> CaseCompareResult:
    first = leaf_results[0]
    distinct_output_dtypes = {result.output_dtype for result in leaf_results}
    distinct_comparison_paths = {result.comparison_path for result in leaf_results}
    output_dtype = first.output_dtype if len(distinct_output_dtypes) == 1 else "multiple"
    comparison_path = first.comparison_path if len(distinct_comparison_paths) == 1 else "composite"
    diagnostics: Mapping[str, object]
    if len(leaf_results) == 1:
        diagnostics = {**dict(first.diagnostics), "leaf_count": 1}
    else:
        diagnostics = {
            "case_id": case_id,
            "compute": compute,
            "input_type": input_info.input_type,
            "input_dtype": input_info.input_dtype,
            "output_path": "output",
            "leaf_count": len(leaf_results),
        }
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=output_dtype,
        comparison_path=comparison_path,
        message=f"PASS case '{case_id}' matched across {len(leaf_results)} output leaf/leaves.",
        diagnostics=diagnostics,
    )


def _structure_error_result(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    error: OutputStructureError,
) -> CaseCompareResult:
    if error.kind == "key_mismatch":
        message = f"FAIL case '{case_id}' mapping keys differ at {error.path}."
        extra: dict[str, object] = {
            "expected_keys": list(error.expected_keys),
            "actual_keys": list(error.actual_keys),
        }
    elif error.kind == "length_mismatch":
        message = f"FAIL case '{case_id}' sequence length differs at {error.path}."
        extra = {
            "expected_length": error.expected_length,
            "actual_length": error.actual_length,
        }
    else:
        message = (
            f"FAIL case '{case_id}' expected {error.expected_type} at {error.path}, "
            f"got {error.actual_type}."
        )
        extra = {
            "expected_type": error.expected_type,
            "actual_type": error.actual_type,
        }
    failure_stage = error.kind if error.kind in ("key_mismatch", "length_mismatch") else "type_mismatch"
    return case_result(
        passed=False,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=None,
        comparison_path="structure-mismatch",
        message=message,
        diagnostics={
            "failure_stage": failure_stage,
            "output_path": error.path,
            **extra,
        },
    )


def compare_npu_contract_leaf(
    leaf: OutputLeaf,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
) -> CaseCompareResult:
    if not isinstance(leaf.actual, torch.Tensor) or not isinstance(leaf.golden, torch.Tensor):
        return unsupported_output_type_result(leaf, case_id=case_id, compute=compute, input_info=input_info)
    actual_cpu = _normalize_output_tensor(leaf.actual)
    golden_cpu = _normalize_output_tensor(leaf.golden)
    output_dtype = _dtype_name(golden_cpu.dtype)
    comparison_path = _select_comparison_path(compute, input_info.input_type, output_dtype)
    if comparison_path is None:
        return case_result(
            passed=False,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            output_dtype=output_dtype,
            comparison_path="unsupported-output-type",
            message=f"FAIL case '{case_id}' output dtype '{output_dtype}' is unsupported at {leaf.path}.",
            diagnostics={
                "failure_stage": "unsupported_output_type",
                "output_path": leaf.path,
                "output_dtype": output_dtype,
            },
        )
    return compare_npu_contract_output(
        actual_cpu=actual_cpu,
        golden_cpu=golden_cpu,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_path=leaf.path,
        output_dtype=output_dtype,
        comparison_path=comparison_path,
    )


def _normalize_output_tensor(value: torch.Tensor) -> torch.Tensor:
    return value.detach().cpu()


@dataclass(frozen=True)
class _LeafRequest:
    """Everything a per-leaf output comparison needs beyond its policy data."""

    actual_cpu: torch.Tensor
    golden_cpu: torch.Tensor
    case_id: str
    compute: bool
    input_info: InputInfo
    output_path: str
    output_dtype: str
    comparison_path: str


def compare_npu_contract_output(
    *,
    actual_cpu: torch.Tensor,
    golden_cpu: torch.Tensor,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    output_path: str,
    output_dtype: str,
    comparison_path: str,
) -> CaseCompareResult:
    req = _LeafRequest(
        actual_cpu=actual_cpu,
        golden_cpu=golden_cpu,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_path=output_path,
        output_dtype=output_dtype,
        comparison_path=comparison_path,
    )
    if comparison_path == "non-compute":
        return _compare_non_compute(req)
    precheck_failure = _do_prechecks(req)
    if precheck_failure is not None:
        return precheck_failure
    if comparison_path == "bool-output":
        return _compare_bool_output(req)
    if comparison_path == "integer-compute":
        return _compare_integer_output(req, bound=0)
    if comparison_path == "quantized-fp-to-int":
        return _compare_integer_output(req, bound=1)
    return _compare_floating_output(req)


def _compare_non_compute(req: _LeafRequest) -> CaseCompareResult:
    if tuple(req.actual_cpu.shape) != tuple(req.golden_cpu.shape):
        return _shape_mismatch_result(
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_path=req.output_path,
            output_dtype=req.output_dtype,
            comparison_path="non-compute",
            actual_shape=tuple(req.actual_cpu.shape),
            golden_shape=tuple(req.golden_cpu.shape),
        )
    if req.actual_cpu.dtype != req.golden_cpu.dtype:
        return _non_compute_dtype_mismatch_result(req)
    return _raw_bits_result(req)


def _non_compute_dtype_mismatch_result(req: _LeafRequest) -> CaseCompareResult:
    return case_result(
        passed=False,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path="non-compute",
        message=f"FAIL case '{req.case_id}' dtype mismatch at {req.output_path} for non-compute comparison.",
        diagnostics={
            "failure_stage": "dtype_mismatch",
            "output_path": req.output_path,
            "expected_dtype": _dtype_name(req.golden_cpu.dtype),
            "actual_dtype": _dtype_name(req.actual_cpu.dtype),
        },
    )


def _raw_bits_result(req: _LeafRequest) -> CaseCompareResult:
    if torch.equal(req.actual_cpu.contiguous().view(torch.uint8), req.golden_cpu.contiguous().view(torch.uint8)):
        return case_result(
            passed=True,
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_dtype=req.output_dtype,
            comparison_path="non-compute",
            message=f"PASS case '{req.case_id}' matched raw bits at {req.output_path}.",
            diagnostics={"output_path": req.output_path},
        )
    return case_result(
        passed=False,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path="non-compute",
        message=f"FAIL case '{req.case_id}' raw bits differ at {req.output_path}.",
        diagnostics={
            "failure_stage": "binary_equal",
            "output_path": req.output_path,
            "expected_dtype": _dtype_name(req.golden_cpu.dtype),
            "actual_dtype": _dtype_name(req.actual_cpu.dtype),
        },
    )


def _do_prechecks(req: _LeafRequest) -> CaseCompareResult | None:
    if tuple(req.actual_cpu.shape) != tuple(req.golden_cpu.shape):
        return _shape_mismatch_result(
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_path=req.output_path,
            output_dtype=req.output_dtype,
            comparison_path=req.comparison_path,
            actual_shape=tuple(req.actual_cpu.shape),
            golden_shape=tuple(req.golden_cpu.shape),
        )
    actual_cast = _cast_to_golden_dtype(req)
    nan_failure = _nan_mask_failure(req, actual_cast)
    if nan_failure is not None:
        return nan_failure
    return _inf_mask_failure(req, actual_cast)


def _cast_to_golden_dtype(req: _LeafRequest) -> torch.Tensor:
    if req.actual_cpu.dtype != req.golden_cpu.dtype:
        return req.actual_cpu.to(dtype=req.golden_cpu.dtype)
    return req.actual_cpu


def _nan_mask_failure(req: _LeafRequest, actual_cast: torch.Tensor) -> CaseCompareResult | None:
    nan_mask_actual = _nan_mask(actual_cast)
    nan_mask_golden = _nan_mask(req.golden_cpu)
    if torch.equal(nan_mask_actual, nan_mask_golden):
        return None
    return case_result(
        passed=False,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path=req.comparison_path,
        message=f"FAIL case '{req.case_id}' NaN locations differ at {req.output_path}.",
        diagnostics={
            "failure_stage": "nan_mask_mismatch",
            "output_path": req.output_path,
            "nan_mismatch_count": int(torch.count_nonzero(nan_mask_actual != nan_mask_golden).item()),
        },
    )


def _inf_mask_failure(req: _LeafRequest, actual_cast: torch.Tensor) -> CaseCompareResult | None:
    inf_mask_actual = _inf_mask(actual_cast)
    inf_mask_golden = _inf_mask(req.golden_cpu)
    if not torch.equal(inf_mask_actual, inf_mask_golden):
        return case_result(
            passed=False,
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_dtype=req.output_dtype,
            comparison_path=req.comparison_path,
            message=f"FAIL case '{req.case_id}' Inf locations differ at {req.output_path}.",
            diagnostics={
                "failure_stage": "inf_mask_mismatch",
                "output_path": req.output_path,
                "inf_mismatch_count": int(torch.count_nonzero(inf_mask_actual != inf_mask_golden).item()),
            },
        )
    if int(torch.count_nonzero(inf_mask_golden).item()) > 0 and not torch.equal(
        actual_cast[inf_mask_golden], req.golden_cpu[inf_mask_golden]
    ):
        return case_result(
            passed=False,
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_dtype=req.output_dtype,
            comparison_path=req.comparison_path,
            message=f"FAIL case '{req.case_id}' Inf values/signs differ at {req.output_path}.",
            diagnostics={
                "failure_stage": "inf_sign_mismatch",
                "output_path": req.output_path,
                "inf_mismatch_count": int(
                    torch.count_nonzero(actual_cast[inf_mask_golden] != req.golden_cpu[inf_mask_golden]).item()
                ),
            },
        )
    return None


def _compare_bool_output(req: _LeafRequest) -> CaseCompareResult:
    actual_cast = _cast_to_golden_dtype(req)
    if torch.equal(actual_cast, req.golden_cpu):
        return case_result(
            passed=True,
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_dtype=req.output_dtype,
            comparison_path="bool-output",
            message=f"PASS case '{req.case_id}' matched bool output at {req.output_path}.",
            diagnostics={"output_path": req.output_path},
        )
    return case_result(
        passed=False,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path="bool-output",
        message=f"FAIL case '{req.case_id}' bool outputs differ at {req.output_path}.",
        diagnostics={"failure_stage": "bool_equal", "output_path": req.output_path},
    )


def _compare_integer_output(req: _LeafRequest, *, bound: int) -> CaseCompareResult:
    actual_cast = _cast_to_golden_dtype(req)
    diff = (actual_cast.to(dtype=torch.int64) - req.golden_cpu.to(dtype=torch.int64)).abs()
    max_diff = int(diff.max().item()) if diff.numel() > 0 else 0
    if max_diff <= bound:
        return case_result(
            passed=True,
            case_id=req.case_id,
            compute=req.compute,
            input_info=req.input_info,
            output_dtype=req.output_dtype,
            comparison_path=req.comparison_path,
            message=f"PASS case '{req.case_id}' matched integer output at {req.output_path}.",
            diagnostics={"output_path": req.output_path, "max_abs_diff": max_diff, "error_bound": bound},
        )
    flat_index = int(torch.argmax(diff).item())
    return case_result(
        passed=False,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path=req.comparison_path,
        message=(
            f"FAIL case '{req.case_id}' integer comparison exceeded the error bound at {req.output_path}: "
            f"max_abs_diff={max_diff}, bound={bound}."
        ),
        diagnostics={
            "failure_stage": "integer_error_bound",
            "output_path": req.output_path,
            "max_abs_diff": max_diff,
            "max_abs_diff_index": _unravel_index(flat_index, tuple(req.golden_cpu.shape)),
            "error_bound": bound,
        },
    )


@dataclass(frozen=True)
class _FiniteComparison:
    """Precomputed finite-element views and stats for one floating leaf."""

    req: _LeafRequest
    thresholds: dict[str, float]
    finite_count: int
    finite_mask: torch.Tensor
    diff: torch.Tensor
    error_cap: torch.Tensor
    max_abs_diff: float
    max_abs_diff_index: tuple[int, ...] | tuple[()]
    matched_ratio: float
    mere: float


def _compare_floating_output(req: _LeafRequest) -> CaseCompareResult:
    actual_cast = _cast_to_golden_dtype(req)
    finite_mask = torch.isfinite(actual_cast) & torch.isfinite(req.golden_cpu)
    finite_count = int(torch.count_nonzero(finite_mask).item())
    thresholds = _thresholds_for_output_dtype(req.output_dtype)
    if finite_count == 0:
        return _no_finite_floating_result(req, thresholds)
    comp = _build_finite_comparison(req, actual_cast, finite_mask, finite_count, thresholds)
    if not bool(torch.all(comp.diff <= comp.error_cap).item()):
        return _max_error_cap_failure(comp)
    if comp.matched_ratio < 0.9:
        return _matched_ratio_failure(comp)
    if comp.mere >= thresholds["rel_threshold"]:
        return _mere_failure(comp)
    return _floating_pass_result(comp)


def _build_finite_comparison(
    req: _LeafRequest,
    actual_cast: torch.Tensor,
    finite_mask: torch.Tensor,
    finite_count: int,
    thresholds: dict[str, float],
) -> _FiniteComparison:
    actual_finite, golden_finite = _finite_float_views(actual_cast, req.golden_cpu, finite_mask)
    diff = (actual_finite - golden_finite).abs()
    abs_golden = golden_finite.abs()
    error_cap = thresholds["atol"] + thresholds["rtol"] * abs_golden
    max_flat_index = int(torch.argmax(diff).item())
    finite_indices = finite_mask.nonzero(as_tuple=False)
    max_diff_index = _indices_tensor_to_tuple(finite_indices[max_flat_index])
    small_mask = abs_golden < thresholds["small_value_threshold"]
    matched_small = diff <= thresholds["small_value_error"]
    matched_normal = diff / (abs_golden + 1e-7) <= thresholds["rel_threshold"]
    matched = torch.where(small_mask, matched_small, matched_normal)
    return _FiniteComparison(
        req=req,
        thresholds=thresholds,
        finite_count=finite_count,
        finite_mask=finite_mask,
        diff=diff,
        error_cap=error_cap,
        max_abs_diff=float(diff.max().item()),
        max_abs_diff_index=max_diff_index,
        matched_ratio=float(matched.to(dtype=torch.float32).mean().item()),
        mere=float((diff / (abs_golden + 1e-7)).mean().item()),
    )


def _floating_stats_diagnostics(
    comp: _FiniteComparison,
    failure_stage: str | None,
) -> dict[str, object]:
    diagnostics: dict[str, object] = {}
    if failure_stage is not None:
        diagnostics["failure_stage"] = failure_stage
    diagnostics.update(
        {
            "output_path": comp.req.output_path,
            "finite_count": comp.finite_count,
            "matched_ratio": comp.matched_ratio,
            "mere": comp.mere,
            "mere_threshold": comp.thresholds["rel_threshold"],
            "max_abs_diff": comp.max_abs_diff,
            "max_abs_diff_index": comp.max_abs_diff_index,
            "output_dtype": comp.req.output_dtype,
            "thresholds": dict(comp.thresholds),
        }
    )
    return diagnostics


def _floating_failure_result(
    req: _LeafRequest,
    message: str,
    diagnostics: Mapping[str, object],
) -> CaseCompareResult:
    return case_result(
        passed=False,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path="floating-point-compute",
        message=message,
        diagnostics=diagnostics,
    )


def _max_error_cap_failure(comp: _FiniteComparison) -> CaseCompareResult:
    req = comp.req
    cap_mask = comp.diff <= comp.error_cap
    failing_flat_index = int(torch.nonzero(~cap_mask, as_tuple=False)[0].item())
    finite_indices = comp.finite_mask.nonzero(as_tuple=False)
    failing_index = _indices_tensor_to_tuple(finite_indices[failing_flat_index])
    return _floating_failure_result(
        req,
        (
            f"FAIL case '{req.case_id}' max error cap failed at {req.output_path}: "
            f"diff={float(comp.diff[failing_flat_index].item())}, "
            f"cap={float(comp.error_cap[failing_flat_index].item())}."
        ),
        {
            "failure_stage": "max_error_cap",
            "output_path": req.output_path,
            "finite_count": comp.finite_count,
            "max_abs_diff": comp.max_abs_diff,
            "max_abs_diff_index": comp.max_abs_diff_index,
            "first_failing_index": failing_index,
            "max_error_cap_at_index": float(comp.error_cap[failing_flat_index].item()),
            "output_dtype": req.output_dtype,
            "thresholds": dict(comp.thresholds),
        },
    )


def _matched_ratio_failure(comp: _FiniteComparison) -> CaseCompareResult:
    req = comp.req
    return _floating_failure_result(
        req,
        (
            f"FAIL case '{req.case_id}' matched ratio failed at {req.output_path}: "
            f"matched_ratio={comp.matched_ratio}."
        ),
        _floating_stats_diagnostics(comp, "matched_ratio"),
    )


def _mere_failure(comp: _FiniteComparison) -> CaseCompareResult:
    req = comp.req
    return _floating_failure_result(
        req,
        (
            f"FAIL case '{req.case_id}' MERE failed at {req.output_path}: "
            f"mere={comp.mere}, threshold={comp.thresholds['rel_threshold']}."
        ),
        _floating_stats_diagnostics(comp, "mere"),
    )


def _floating_pass_result(comp: _FiniteComparison) -> CaseCompareResult:
    req = comp.req
    return case_result(
        passed=True,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path="floating-point-compute",
        message=f"PASS case '{req.case_id}' matched floating-point output at {req.output_path}.",
        diagnostics=_floating_stats_diagnostics(comp, None),
    )


def _no_finite_floating_result(
    req: _LeafRequest,
    thresholds: dict[str, float],
) -> CaseCompareResult:
    return case_result(
        passed=True,
        case_id=req.case_id,
        compute=req.compute,
        input_info=req.input_info,
        output_dtype=req.output_dtype,
        comparison_path="floating-point-compute",
        message=f"PASS case '{req.case_id}' had no finite floating-point elements at {req.output_path}.",
        diagnostics={
            "output_path": req.output_path,
            "finite_count": 0,
            "matched_ratio": 1.0,
            "mere": 0.0,
            "mere_threshold": thresholds["rel_threshold"],
            "output_dtype": req.output_dtype,
            "thresholds": dict(thresholds),
        },
    )


def _finite_float_views(
    actual_cast: torch.Tensor,
    golden_cpu: torch.Tensor,
    finite_mask: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    actual_finite = actual_cast[finite_mask]
    golden_finite = golden_cpu[finite_mask]
    if actual_finite.is_complex() or golden_finite.is_complex():
        return (
            torch.view_as_real(actual_finite.to(dtype=torch.complex64)).reshape(-1).to(dtype=torch.float32),
            torch.view_as_real(golden_finite.to(dtype=torch.complex64)).reshape(-1).to(dtype=torch.float32),
        )
    return (actual_finite.to(dtype=torch.float32), golden_finite.to(dtype=torch.float32))


def _infer_input_info(inputs: object) -> InputInfo:
    direct_values = _direct_input_values(inputs)
    direct_tensors = [value for value in direct_values if isinstance(value, torch.Tensor)]
    if direct_tensors:
        input_dtype = min(
            (_dtype_name(tensor.dtype) for tensor in direct_tensors),
            key=lambda name: DTYPE_PRIORITY.get(name, len(DTYPE_PRIORITY)),
        )
        return InputInfo(
            input_type="float" if input_dtype in INPUT_FLOAT_FAMILY else "int",
            input_dtype=input_dtype,
        )
    for value in direct_values:
        if isinstance(value, (list, tuple)):
            sequence_values = cast(Sequence[object], value)
            tensor_items = [item for item in sequence_values if isinstance(item, torch.Tensor)]
            if tensor_items and len(tensor_items) == len(sequence_values):
                input_dtype = _dtype_name(tensor_items[0].dtype)
                return InputInfo(
                    input_type="float" if input_dtype in INPUT_FLOAT_FAMILY else "int",
                    input_dtype=input_dtype,
                )
    return InputInfo(input_type="no_tensor", input_dtype=None)


def _direct_input_values(inputs: object) -> list[object]:
    if isinstance(inputs, Mapping):
        return list(cast(Mapping[object, object], inputs).values())
    if isinstance(inputs, tuple):
        return list(cast(tuple[object, ...], inputs))
    if isinstance(inputs, list):
        return list(cast(list[object], inputs))
    return [] if inputs is None else [inputs]


def _select_comparison_path(compute: bool, input_type: str, output_dtype: str) -> str | None:
    if not compute:
        return "non-compute"
    if output_dtype == "bool":
        return "bool-output"
    if output_dtype in INTEGER_FAMILY:
        if input_type == "float":
            return "quantized-fp-to-int"
        if input_type in {"int", "no_tensor"}:
            return "integer-compute"
        return None
    if output_dtype in OUTPUT_FLOAT_FAMILY:
        return "floating-point-compute"
    return None


def _thresholds_for_output_dtype(output_dtype: str) -> dict[str, float]:
    matched_key = _threshold_key(output_dtype)
    matched = MATCH_THRESHOLDS.get(matched_key, MATCH_THRESHOLDS["fallback"])
    max_error = MAX_ERROR_THRESHOLDS.get(matched_key, MAX_ERROR_THRESHOLDS["fallback"])
    return {
        "small_value_threshold": float(matched["small_value_threshold"]),
        "small_value_error": float(matched["small_value_error"]),
        "rel_threshold": float(matched["rel_threshold"]),
        "atol": float(max_error["atol"]),
        "rtol": float(max_error["rtol"]),
    }


def _shape_mismatch_result(
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    output_path: str,
    output_dtype: str,
    comparison_path: str,
    actual_shape: tuple[int, ...],
    golden_shape: tuple[int, ...],
) -> CaseCompareResult:
    return case_result(
        passed=False,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=output_dtype,
        comparison_path=comparison_path,
        message=f"FAIL case '{case_id}' shape mismatch at {output_path}: expected {golden_shape}, got {actual_shape}.",
        diagnostics={
            "failure_stage": "shape_mismatch",
            "output_path": output_path,
            "shape_expected": golden_shape,
            "shape_actual": actual_shape,
            "output_dtype": output_dtype,
        },
    )


def _nan_mask(tensor: torch.Tensor) -> torch.Tensor:
    if tensor.is_floating_point() or tensor.is_complex():
        return torch.isnan(tensor)
    return torch.zeros_like(tensor, dtype=torch.bool)


def _inf_mask(tensor: torch.Tensor) -> torch.Tensor:
    if tensor.is_floating_point() or tensor.is_complex():
        return torch.isinf(tensor)
    return torch.zeros_like(tensor, dtype=torch.bool)


def _indices_tensor_to_tuple(indices: torch.Tensor) -> tuple[int, ...]:
    flat_indices = indices.reshape(-1)
    return tuple(int(flat_indices[index].item()) for index in range(flat_indices.numel()))


def _unravel_index(flat_index: int, shape: tuple[int, ...]) -> tuple[int, ...] | tuple[()]:
    if not shape:
        return ()
    if len(shape) == 1:
        return (flat_index,)
    values: list[int] = []
    remaining = flat_index
    for size in reversed(shape):
        values.append(remaining % size)
        remaining //= size
    return tuple(reversed(values))


def _dtype_name(dtype: torch.dtype) -> str:
    return str(dtype).replace("torch.", "")


def _threshold_key(output_dtype: str) -> str:
    if output_dtype.startswith("float8_e4m3"):
        return "float8_e4m3"
    if output_dtype.startswith("float8_e5m2"):
        return "float8_e5m2"
    if output_dtype in {"float16", "bfloat16", "float32", "hifloat32"}:
        return output_dtype
    return "fallback"

# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Helix's independent implementation of CANN Bench precision criteria.

The criteria are derived from CANN Bench, but Helix implements this two-result
variant independently and does not import or copy CANN Bench code. In
pseudocode, per case:

    leaves = traverse_matching_output_structure(actual, golden)
    fail if the structure differs or a leaf is not a Tensor

    for each leaf:
        actual, golden = detach_and_move_to_cpu(leaf)
        fail unless shapes match

        if actual.dtype is bool or integer:
            # Integers: abs(actual - golden) <= max(threshold, 0), where threshold
            # comes from extra['precision_thresholds'][dtype] (default 0 = exact).
            # Bool stays exact.
            pass only if the values match within that absolute tolerance
            # Equal integer values may use different integer dtypes.

        fail if actual.dtype is complex or unsupported
        thresholds = table[actual.dtype or float32_fallback]
        target_golden = cast(golden, actual.dtype)
        actual64, golden64 = cast(actual, float64), cast(target_golden, float64)

        fail unless NaN positions match
        fail unless shared Inf values have the same sign
        replace a one-sided Inf with signed_finfo_max(actual.dtype)
        valid = values excluding matched Inf and non-finite relative errors
        pass if valid is empty

        relative_error = abs(actual64 - golden64) / (abs(golden64) + 1e-7)
        MERE, MARE = mean(relative_error[valid]), max(relative_error[valid])
        pass if MERE < threshold and MARE < 10 * threshold

        small = abs(golden64) < small_value_threshold
        cancel = actual_near_zero AND golden_in_cancel_range AND NOT small
        normal = valid AND NOT small AND NOT cancel
        # Normal / small / cancel each have an independent pass flag (cann-bench
        # style). Small/cancel allow ≤2× native errors (≤2 without native);
        # normal is strict unless native itself exceeds MARE there (ratio ≤2).
        pass if normal_passed and small_value_passed and cancel_passed
            otherwise fail; failure_stage names the failing region.

    Top-level sequence outputs listed in extra['ignore_output_indices']
    (proto.yaml compare: false) are skipped and treated as passed, matching
    cann-bench ignore_output_indices. Optional extra['index_gather'] then runs
    the official tie-order-independent check: x.gather(dim, idx) == values on
    the candidate outputs (issue #40).

    pass only if every leaf passes; otherwise return the first failed leaf.

The small/cancel bounds without a native reference use a zero baseline, so each
special region permits at most two candidate errors. Normal-region ratio
fallback requires a native reference that itself exceeds the MARE threshold
there (aligned with cann-bench compare.py issue #92). Fallback diagnostics show
normal-region MERE/MARE and retain overall metrics separately. ``compute`` and
input dtype do not select a rule. This module implements per-case comparison
only; public mode selection and artifact validation belong to ``npu_compare.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
import re
import sys
from typing import Optional

import torch

from npu_compare_common import (
    CaseCompareResult,
    InputInfo,
    OutputLeaf,
    OutputStructureError,
    OutputTraversal,
    case_result,
    traverse_output_leaves,
    unexpected_failure_result,
)


CANN_BENCH_THRESHOLDS = {
    "float16": {
        "threshold": 2 ** -10,
        "small_value_threshold": 2 ** -11,
        "small_value_error": 2 ** -16,
        "cancel_boundary": 2 ** -5,
        "cancel_zero_threshold": 2 ** -5,
    },
    "bfloat16": {
        "threshold": 2 ** -7,
        "small_value_threshold": 2 ** -8,
        "small_value_error": 2 ** -16,
        "cancel_boundary": 2 ** -3,
        "cancel_zero_threshold": 2 ** -3,
    },
    "float32": {
        "threshold": 2 ** -13,
        "small_value_threshold": 2 ** -14,
        "small_value_error": 2 ** -30,
        "cancel_boundary": 2 ** -8,
        "cancel_zero_threshold": 2 ** -8,
    },
    "float64": {
        "threshold": 2 ** -13,
        "small_value_threshold": 2 ** -14,
        "small_value_error": 2 ** -30,
        "cancel_boundary": 2 ** -8,
        "cancel_zero_threshold": 2 ** -8,
    },
    "hifloat32": {
        "threshold": 2 ** -11,
        "small_value_threshold": 2 ** -12,
        "small_value_error": 2 ** -28,
        "cancel_boundary": 2 ** -8,
        "cancel_zero_threshold": 2 ** -8,
    },
    "float8_e4m3": {
        "threshold": 2 ** -3,
        "small_value_threshold": 2 ** -4,
        "small_value_error": 2 ** -6,
        "cancel_boundary": 2 ** -1,
        "cancel_zero_threshold": 2 ** -1,
    },
    "float8_e5m2": {
        "threshold": 2 ** -2,
        "small_value_threshold": 2 ** -3,
        "small_value_error": 2 ** -5,
        "cancel_boundary": 1.0,
        "cancel_zero_threshold": 1.0,
    },
}
_FALLBACK_THRESHOLDS = CANN_BENCH_THRESHOLDS["float32"]
_INTEGER_DTYPES = frozenset(
    {
        torch.uint8,
        torch.uint16,
        torch.uint32,
        torch.uint64,
        torch.int8,
        torch.int16,
        torch.int32,
        torch.int64,
    }
)


@dataclass(frozen=True)
class _LeafContext:
    """Case and leaf identity shared by the per-leaf comparison helpers."""

    case_id: str
    compute: bool
    input_info: InputInfo
    output_path: str
    output_dtype: str | None


@dataclass(frozen=True)
class _FloatingMetrics:
    """Tensors, thresholds, and region counters behind one leaf verdict."""

    thresholds: dict[str, float]
    actual: torch.Tensor
    diff: torch.Tensor
    relative_error: torch.Tensor
    valid_mask: torch.Tensor
    stage: str
    mismatch_count: int = 0
    small_error_count: int = 0
    cancel_error_count: int = 0
    normal_mismatch_count: int = 0
    small_total_count: int = 0
    cancel_total_count: int = 0
    display_mask: torch.Tensor | None = None
    normal_mask: torch.Tensor | None = None


@dataclass(frozen=True)
class _RegionVerdict:
    """Native-reference counters and the three independent region pass flags."""

    native_small_error_count: int = 0
    native_cancel_error_count: int = 0
    native_normal_error_count: int = 0
    native_reference_available: bool = False
    special_fallback: bool = False
    small_value_passed: bool = True
    cancel_passed: bool = True
    normal_passed: bool = True


@dataclass(frozen=True)
class _RegionMasks:
    """Element masks delimiting the normal / small / cancel regions."""

    mismatch_mask: torch.Tensor
    small_mask: torch.Tensor
    cancel_mask: torch.Tensor
    normal_region_mask: torch.Tensor


@dataclass(frozen=True)
class _RegionCounts:
    """Candidate error and population counters per region."""

    small_error_count: int
    cancel_error_count: int
    small_total_count: int
    cancel_total_count: int
    normal_mismatch_count: int


@dataclass(frozen=True)
class _FloatingWork:
    """Working tensors shared by the floating region checks."""

    metrics: _FloatingMetrics
    actual_work: torch.Tensor
    golden_work: torch.Tensor
    golden_abs: torch.Tensor


@dataclass(frozen=True)
class _NativeRetryOutcome:
    """Native replay either replaced the leaf results or resolved early."""

    leaf_results: list[CaseCompareResult]
    early_result: CaseCompareResult | None


def compare_cann_bench_case(
    *,
    case_id: str,
    actual: object,
    golden: object,
    compute: bool,
    inputs: object = (),
    native_ref_operator: Optional[Callable[[object], object]] = None,
    extra: Mapping[str, object] | None = None,
) -> CaseCompareResult:
    precision_thresholds = _precision_thresholds_from_extra(extra)
    ignore_output_indices = _ignore_output_indices_from_extra(extra)
    input_info = InputInfo(input_type="no_tensor", input_dtype=None)
    traversal = traverse_output_leaves(actual, golden)
    if traversal.error is not None:
        return _structure_error_result(case_id, compute, input_info, traversal.error)
    leaf_results = [
        _compare_or_skip_leaf(
            leaf,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            precision_thresholds=precision_thresholds,
            ignore_output_indices=ignore_output_indices,
        )
        for leaf in traversal.leaves
    ]
    failed = next((result for result in leaf_results if not result.passed), None)
    if _requires_native_reference(leaf_results):
        retry = _native_reference_retry(
            traversal,
            golden,
            failed,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            inputs=inputs,
            native_ref_operator=native_ref_operator,
            precision_thresholds=precision_thresholds,
            ignore_output_indices=ignore_output_indices,
        )
        if retry.early_result is not None:
            return retry.early_result
        leaf_results = retry.leaf_results
        failed = next((result for result in leaf_results if not result.passed), None)
    if failed is not None:
        return failed
    return _finalize_cann_bench_case(
        case_id, compute, input_info, leaf_results, actual=actual, inputs=inputs, extra=extra
    )


def _finalize_cann_bench_case(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    leaf_results: list[CaseCompareResult],
    *,
    actual: object,
    inputs: object,
    extra: Mapping[str, object] | None,
) -> CaseCompareResult:
    index_gather_failure = _index_gather_failure_result(
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        actual=actual,
        inputs=inputs,
        extra=extra,
    )
    if index_gather_failure is not None:
        return index_gather_failure
    return _cann_bench_pass_result(case_id, compute, input_info, leaf_results)


def _native_reference_retry(
    traversal: OutputTraversal,
    golden: object,
    failed: CaseCompareResult | None,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    inputs: object,
    native_ref_operator: Optional[Callable[[object], object]],
    precision_thresholds: Mapping[str, float] | None,
    ignore_output_indices: frozenset[int] | None,
) -> _NativeRetryOutcome:
    """Re-run failed region-fallback leaves against a native reference."""
    if native_ref_operator is None:
        early = failed if failed is not None else _unexpected_failure(case_id, compute, input_info)
        return _NativeRetryOutcome(leaf_results=[], early_result=early)
    try:
        native = native_ref_operator(inputs)
    except Exception as exc:
        return _NativeRetryOutcome(
            leaf_results=[], early_result=_native_replay_fallback(case_id, failed, str(exc))
        )
    native_traversal = traverse_output_leaves(native, golden)
    if native_traversal.error is not None or not _native_leaves_match(
        traversal.leaves, native_traversal.leaves
    ):
        return _NativeRetryOutcome(
            leaf_results=[],
            early_result=_native_replay_fallback(
                case_id, failed, "native output structure or tensor shape differs"
            ),
        )
    try:
        return _compare_native_leaves(
            traversal,
            native_traversal,
            failed,
            case_id=case_id,
            compute=compute,
            input_info=input_info,
            precision_thresholds=precision_thresholds,
            ignore_output_indices=ignore_output_indices,
        )
    except Exception as exc:
        return _NativeRetryOutcome(
            leaf_results=[],
            early_result=_native_replay_fallback(
                case_id, failed, f"native output comparison failed: {exc}"
            ),
        )


def _compare_native_leaves(
    traversal: OutputTraversal,
    native_traversal: OutputTraversal,
    failed: CaseCompareResult | None,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    precision_thresholds: Mapping[str, float] | None,
    ignore_output_indices: frozenset[int] | None,
) -> _NativeRetryOutcome:
    native_leaf_results: list[CaseCompareResult] = []
    for leaf, native_leaf in zip(traversal.leaves, native_traversal.leaves):
        if not isinstance(native_leaf.actual, torch.Tensor):
            # Ignored outputs may still be non-tensor; skip path handles ignore first.
            if _is_ignored_output_leaf(leaf.path, ignore_output_indices):
                native_leaf_results.append(
                    _skipped_output_result(leaf, case_id, compute, input_info)
                )
                continue
            return _NativeRetryOutcome(
                leaf_results=[],
                early_result=_native_replay_fallback(
                    case_id, failed, "native output contains a non-tensor leaf"
                ),
            )
        native_leaf_results.append(
            _compare_or_skip_leaf(
                leaf,
                case_id=case_id,
                compute=compute,
                input_info=input_info,
                native=native_leaf.actual,
                precision_thresholds=precision_thresholds,
                ignore_output_indices=ignore_output_indices,
            )
        )
    return _NativeRetryOutcome(leaf_results=native_leaf_results, early_result=None)


def _cann_bench_pass_result(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    leaf_results: list[CaseCompareResult],
) -> CaseCompareResult:
    """Aggregate the per-leaf passes into the case-level pass result."""
    if not leaf_results:
        return _pass_result_no_leaves(case_id, compute, input_info)
    comparable = [item for item in leaf_results if not item.diagnostics.get("ignored")]
    if not comparable:
        return _pass_result_all_ignored(case_id, compute, input_info, len(leaf_results))
    first = comparable[0]
    output_dtype = (
        first.output_dtype if len({item.output_dtype for item in comparable}) == 1 else "multiple"
    )
    diagnostics: Mapping[str, object]
    if len(comparable) == 1 and len(leaf_results) == 1:
        diagnostics = {**dict(first.diagnostics), "leaf_count": 1}
    else:
        diagnostics = {
            "output_path": "output",
            "leaf_count": len(leaf_results),
            "ignored_leaf_count": len(leaf_results) - len(comparable),
        }
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=output_dtype,
        comparison_path="cann-bench",
        message=f"PASS case '{case_id}' matched across {len(comparable)} output leaf/leaves.",
        diagnostics=diagnostics,
    )


def _pass_result_no_leaves(case_id: str, compute: bool, input_info: InputInfo) -> CaseCompareResult:
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=None,
        comparison_path="cann-bench",
        message=f"PASS case '{case_id}' has no comparable outputs.",
        diagnostics={"output_path": "output", "leaf_count": 0},
    )


def _pass_result_all_ignored(
    case_id: str, compute: bool, input_info: InputInfo, leaf_count: int
) -> CaseCompareResult:
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=None,
        comparison_path="cann-bench",
        message=f"PASS case '{case_id}' skipped all outputs via ignore_output_indices.",
        diagnostics={
            "output_path": "output",
            "leaf_count": leaf_count,
            "ignored_leaf_count": leaf_count,
        },
    )


def _compare_or_skip_leaf(
    leaf: OutputLeaf,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    native: torch.Tensor | None = None,
    precision_thresholds: Mapping[str, float] | None = None,
    ignore_output_indices: frozenset[int] | None = None,
) -> CaseCompareResult:
    if _is_ignored_output_leaf(leaf.path, ignore_output_indices):
        return _skipped_output_result(leaf, case_id, compute, input_info)
    return _compare_cann_bench_leaf(
        leaf,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        native=native,
        precision_thresholds=precision_thresholds,
    )


def _skipped_output_result(
    leaf: OutputLeaf,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
) -> CaseCompareResult:
    output_dtype = _dtype_name(leaf.actual.dtype) if isinstance(leaf.actual, torch.Tensor) else None
    return case_result(
        passed=True,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=output_dtype,
        comparison_path="cann-bench",
        message=f"PASS case '{case_id}' skipped ignored output at {leaf.path}.",
        diagnostics={
            "output_path": leaf.path,
            "comparison_stage": "ignored_output",
            "ignored": True,
        },
    )


_TOP_LEVEL_OUTPUT_INDEX = re.compile(r"^output\[(\d+)\]")


def _leaf_top_level_index(path: str) -> int | None:
    """Map Helix leaf path 'output[i]...' to cann-bench top-level output index i."""
    match = _TOP_LEVEL_OUTPUT_INDEX.match(path)
    return int(match.group(1)) if match is not None else None


def _is_ignored_output_leaf(
    path: str,
    ignore_output_indices: frozenset[int] | None,
) -> bool:
    if not ignore_output_indices:
        return False
    index = _leaf_top_level_index(path)
    return index is not None and index in ignore_output_indices


def _ignore_output_indices_from_extra(
    extra: Mapping[str, object] | None,
) -> frozenset[int] | None:
    """Parse optional extra['ignore_output_indices'] (proto compare: false)."""
    if extra is None:
        return None
    raw = extra.get("ignore_output_indices")
    if raw is None:
        return None
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("extra['ignore_output_indices'] must be a sequence of integers")
    return frozenset(int(index) for index in raw)


def _index_gather_failure_result(
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    actual: object,
    inputs: object,
    extra: Mapping[str, object] | None,
) -> CaseCompareResult | None:
    """Run optional index_gather checks; return a failure result or None."""
    specs = _index_gather_specs_from_extra(extra)
    if not specs:
        return None
    attrs = _attrs_from_extra(extra)
    outputs = _as_tensor_sequence(actual)
    input_seq = _as_tensor_sequence(inputs)
    for spec in specs:
        ok, message = _validate_index_gather_spec(spec, outputs, input_seq, attrs)
        if not ok:
            return case_result(
                passed=False,
                case_id=case_id,
                compute=compute,
                input_info=input_info,
                output_dtype=None,
                comparison_path="cann-bench",
                message=f"FAIL case '{case_id}' {message}",
                diagnostics={
                    "failure_stage": "index_gather",
                    "output_path": f"output[{int(spec['index_output'])}]",
                    "index_gather_error": message,
                },
            )
    return None


def _index_gather_specs_from_extra(
    extra: Mapping[str, object] | None,
) -> tuple[Mapping[str, object], ...]:
    if extra is None:
        return ()
    raw = extra.get("index_gather")
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        return (raw,)
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("extra['index_gather'] must be a mapping or sequence of mappings")
    specs: list[Mapping[str, object]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise TypeError("extra['index_gather'] entries must be mappings")
        specs.append(item)
    return tuple(specs)


def _attrs_from_extra(extra: Mapping[str, object] | None) -> Mapping[str, object]:
    if extra is None:
        return {}
    attrs = extra.get("attrs")
    if attrs is None:
        return {}
    if not isinstance(attrs, Mapping):
        raise TypeError("extra['attrs'] must be a mapping")
    return attrs


def _as_tensor_sequence(value: object) -> list[object]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _validate_index_gather_spec(
    spec: Mapping[str, object],
    outputs: list[object],
    inputs: list[object],
    attrs: Mapping[str, object],
) -> tuple[bool, str]:
    try:
        index_output = int(spec["index_output"])
        value_output = int(spec["value_output"])
        input_index = int(spec["input_index"])
    except KeyError as exc:
        return False, f"index_gather: missing required field {exc.args[0]!r}"
    except (TypeError, ValueError):
        return False, "index_gather: index_output/value_output/input_index must be integers"

    if index_output < 0 or index_output >= len(outputs):
        return False, f"index_gather: missing index output #{index_output}"
    if value_output < 0 or value_output >= len(outputs):
        return False, f"index_gather: missing value output #{value_output}"
    if input_index < 0 or input_index >= len(inputs):
        return False, f"index_gather: missing source input #{input_index}"

    idx = outputs[index_output]
    values = outputs[value_output]
    source = inputs[input_index]
    if not isinstance(source, torch.Tensor):
        return False, f"index_gather: source input #{input_index} is not a Tensor"
    if not isinstance(idx, torch.Tensor):
        return False, f"index_gather: index output #{index_output} is not a Tensor"
    if not isinstance(values, torch.Tensor):
        return False, f"index_gather: value output #{value_output} is not a Tensor"

    if "dim" in spec:
        dim = int(spec["dim"])
    else:
        dim_attr = str(spec.get("dim_attr", "dim"))
        if dim_attr not in attrs:
            return False, (
                f"index_gather: missing dim attribute {dim_attr!r} "
                "(pass case attrs via extra['attrs'])"
            )
        dim = int(attrs[dim_attr])
    return _validate_index_output(source, dim, idx, values)


def _validate_index_output(
    x: torch.Tensor,
    dim: int,
    idx_candidate: torch.Tensor,
    values_candidate: torch.Tensor,
) -> tuple[bool, str]:
    """Candidate-index self-consistency: x.gather(dim, idx) must equal values.

    Mirrors cann-bench eval/index_check.py (issue #40). Tie order does not matter.
    """
    x_c = x.detach().cpu()
    idx_c = idx_candidate.detach().cpu().to(dtype=torch.int64)
    val_c = values_candidate.detach().cpu()

    if idx_c.dim() != x_c.dim():
        return False, (
            f"index_gather: index rank {idx_c.dim()} != input rank {x_c.dim()}"
        )
    dim_n = dim if dim >= 0 else x_c.dim() + dim
    if not (0 <= dim_n < x_c.dim()):
        return False, f"index_gather: dim={dim} out of range for rank {x_c.dim()}"
    if idx_c.shape != val_c.shape:
        return False, (
            f"index_gather: index shape {tuple(idx_c.shape)} != "
            f"value shape {tuple(val_c.shape)}"
        )
    for axis in range(x_c.dim()):
        if axis != dim_n and idx_c.size(axis) > x_c.size(axis):
            return False, (
                f"index_gather: size at dim {axis} ({idx_c.size(axis)}) exceeds "
                f"input ({x_c.size(axis)})"
            )
    dim_size = x_c.size(dim_n)
    if idx_c.numel() > 0:
        lo = int(idx_c.min().item())
        hi = int(idx_c.max().item())
        if lo < 0 or hi >= dim_size:
            return False, (
                f"index_gather: index out of range [{lo},{hi}] for dim size {dim_size}"
            )

    gathered = torch.gather(x_c, dim_n, idx_c).to(dtype=val_c.dtype)
    # NaN-aware equality: torch.equal treats NaN != NaN.
    if gathered.is_floating_point() or val_c.is_floating_point():
        both_nan = torch.isnan(gathered) & torch.isnan(val_c)
        equal = (gathered == val_c) | both_nan
    else:
        equal = gathered == val_c
    if not bool(equal.all().item()):
        mismatch = int((~equal).sum().item())
        return False, (
            f"index_gather: gathered values disagree with value output "
            f"at {mismatch} position(s)"
        )
    return True, ""


def _compare_cann_bench_leaf(
    leaf: OutputLeaf,
    *,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    native: torch.Tensor | None = None,
    precision_thresholds: Mapping[str, float] | None = None,
) -> CaseCompareResult:
    if not isinstance(leaf.actual, torch.Tensor) or not isinstance(leaf.golden, torch.Tensor):
        return _unsupported_output_type_result(leaf, case_id, compute, input_info)
    actual = leaf.actual.detach().cpu()
    golden = leaf.golden.detach().cpu()
    context = _LeafContext(
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_path=leaf.path,
        output_dtype=_dtype_name(actual.dtype),
    )
    if tuple(actual.shape) != tuple(golden.shape):
        return _failure_result(
            context,
            "shape_mismatch",
            f"FAIL case '{case_id}' shape mismatch at {leaf.path}.",
            {"shape_actual": tuple(actual.shape), "shape_expected": tuple(golden.shape)},
        )
    if actual.dtype == torch.bool:
        return _compare_exact_leaf(actual, golden, context)
    if actual.dtype in _INTEGER_DTYPES:
        return _compare_integer_leaf(
            actual,
            golden,
            context,
            precision_thresholds=precision_thresholds,
        )
    if actual.is_complex() or not actual.is_floating_point():
        return _failure_result(
            context,
            "unsupported_output_type",
            f"FAIL case '{case_id}' output dtype '{context.output_dtype}' is unsupported at {leaf.path}.",
            {"actual_dtype": context.output_dtype},
        )
    return _compare_floating_leaf(
        actual,
        golden,
        context,
        native,
        precision_thresholds=precision_thresholds,
    )


# Region-fallback failures that can still pass after a same-precision native replay.
# Aligns with cann-bench's three independent region checks (normal / small / cancel).
_NATIVE_RETRY_STAGES = frozenset(
    {"normal_value_mismatch", "small_value_mismatch", "cancel_mismatch"}
)


def _requires_native_reference(leaf_results: list[CaseCompareResult]) -> bool:
    failures = [result for result in leaf_results if not result.passed]
    if not failures:
        return False
    return all(
        result.diagnostics.get("failure_stage") in _NATIVE_RETRY_STAGES
        for result in failures
    )


def _native_leaves_match(
    leaves: tuple[OutputLeaf, ...],
    native_leaves: tuple[OutputLeaf, ...],
) -> bool:
    if len(leaves) != len(native_leaves):
        return False
    for leaf, native_leaf in zip(leaves, native_leaves):
        if leaf.path != native_leaf.path:
            return False
        if not isinstance(native_leaf.actual, torch.Tensor):
            return False
        if not isinstance(leaf.actual, torch.Tensor):
            return False
        if tuple(native_leaf.actual.shape) != tuple(leaf.actual.shape):
            return False
    return True


def _native_replay_fallback(
    case_id: str,
    result: CaseCompareResult | None,
    reason: str,
) -> CaseCompareResult:
    if result is None:
        raise RuntimeError("native replay fallback requires a failed comparison result")
    print(
        f"[WARNING] CANN Bench native reference replay unavailable for case '{case_id}': {reason}",
        file=sys.stderr,
    )
    return replace(
        result,
        diagnostics={
            **result.diagnostics,
            "native_reference_available": False,
            "native_reference_fallback_reason": reason,
        },
    )


def _unexpected_failure(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
) -> CaseCompareResult:
    return unexpected_failure_result(
        case_id,
        compute,
        input_info,
        comparison_path="cann-bench",
        message=f"FAIL case '{case_id}' CANN Bench comparison reached an invalid state.",
        diagnostics={"failure_stage": "internal_error"},
    )


def _compare_exact_leaf(
    actual: torch.Tensor,
    golden: torch.Tensor,
    context: _LeafContext,
) -> CaseCompareResult:
    mismatch_count = int(torch.count_nonzero(_exact_mismatch_mask(actual, golden)).item())
    if mismatch_count == 0:
        return _exact_match_pass_result(actual, context)
    return _failure_result(
        context,
        "exact_equal",
        f"FAIL case '{context.case_id}' exact {context.output_dtype} comparison failed at {context.output_path}.",
        {"mismatch_count": mismatch_count, "total_count": actual.numel()},
    )


def _exact_match_pass_result(actual: torch.Tensor, context: _LeafContext) -> CaseCompareResult:
    return case_result(
        passed=True,
        case_id=context.case_id,
        compute=context.compute,
        input_info=context.input_info,
        output_dtype=context.output_dtype,
        comparison_path="cann-bench",
        message=f"PASS case '{context.case_id}' matched exact {context.output_dtype} output at {context.output_path}.",
        diagnostics={"output_path": context.output_path, "tensor_shape": tuple(actual.shape)},
    )


def _compare_integer_leaf(
    actual: torch.Tensor,
    golden: torch.Tensor,
    context: _LeafContext,
    *,
    precision_thresholds: Mapping[str, float] | None = None,
) -> CaseCompareResult:
    """Integer abs-diff tolerance, matching cann-bench compare.py.

    Default threshold is 0 (exact). ``extra['precision_thresholds'][dtype]``
    overrides the allowed absolute difference (e.g. int8: 1).
    """
    threshold = _integer_threshold_for_dtype(str(context.output_dtype), precision_thresholds)
    if not _exact_mismatch_mask(actual, golden).any().item():
        return _exact_match_pass_result(actual, context)
    # Align with cann-bench: compare via int64 abs diff after casting golden.
    golden_cast = golden.to(dtype=actual.dtype)
    diff = torch.abs(actual.to(dtype=torch.int64) - golden_cast.to(dtype=torch.int64))
    mismatch_count = int(torch.count_nonzero(diff > max(threshold, 0.0)).item())
    if mismatch_count == 0:
        return case_result(
            passed=True,
            case_id=context.case_id,
            compute=context.compute,
            input_info=context.input_info,
            output_dtype=context.output_dtype,
            comparison_path="cann-bench",
            message=(
                f"PASS case '{context.case_id}' matched integer {context.output_dtype} output "
                f"within abs tolerance {threshold} at {context.output_path}."
            ),
            diagnostics={"output_path": context.output_path, "tensor_shape": tuple(actual.shape)},
        )
    return _failure_result(
        context,
        "integer_abs_tolerance",
        (
            f"FAIL case '{context.case_id}' integer {context.output_dtype} comparison exceeded "
            f"abs tolerance {threshold} at {context.output_path}."
        ),
        {"mismatch_count": mismatch_count, "total_count": actual.numel()},
    )


def _integer_threshold_for_dtype(
    output_dtype: str,
    precision_thresholds: Mapping[str, float] | None,
) -> float:
    if precision_thresholds:
        override = precision_thresholds.get(output_dtype.lower())
        if override is not None:
            return float(override)
    return 0.0


def _exact_mismatch_mask(actual: torch.Tensor, golden: torch.Tensor) -> torch.Tensor:
    if actual.dtype == torch.bool:
        return actual != golden.to(dtype=torch.bool)
    if actual.dtype not in _INTEGER_DTYPES or golden.dtype not in _INTEGER_DTYPES:
        return actual != golden
    if actual.dtype == golden.dtype:
        return actual != golden
    if actual.dtype == torch.uint64:
        if golden.dtype in _INTEGER_DTYPES - {torch.uint8, torch.uint16, torch.uint32, torch.uint64}:
            return (golden < 0) | (actual != golden.to(dtype=torch.uint64))
        return actual != golden.to(dtype=torch.uint64)
    if golden.dtype == torch.uint64:
        if actual.dtype in _INTEGER_DTYPES - {torch.uint8, torch.uint16, torch.uint32, torch.uint64}:
            return (actual < 0) | (actual.to(dtype=torch.uint64) != golden)
        return actual.to(dtype=torch.uint64) != golden
    return actual.to(dtype=torch.int64) != golden.to(dtype=torch.int64)


def _compare_floating_leaf(
    actual: torch.Tensor,
    golden: torch.Tensor,
    context: _LeafContext,
    native: torch.Tensor | None,
    *,
    precision_thresholds: Mapping[str, float] | None = None,
) -> CaseCompareResult:
    thresholds = _thresholds_for_dtype(str(context.output_dtype), precision_thresholds)
    normalized = _normalize_floating_operands(actual, golden, context)
    if isinstance(normalized, CaseCompareResult):
        return normalized
    actual_work, golden_work = normalized
    reconciled = _reconcile_special_values(actual_work, golden_work, actual.dtype, context)
    if isinstance(reconciled, CaseCompareResult):
        return reconciled
    actual_work, golden_work, matched_inf = reconciled
    diff = (actual_work - golden_work).abs()
    golden_abs = golden_work.abs()
    relative_error = diff / (golden_abs + 1e-7)
    valid_mask = ~(torch.isnan(relative_error) | torch.isinf(relative_error) | matched_inf)
    valid_count = int(torch.count_nonzero(valid_mask).item())
    metrics = _FloatingMetrics(
        thresholds=thresholds, actual=actual, diff=diff,
        relative_error=relative_error, valid_mask=valid_mask, stage="pending",
    )
    if valid_count == 0:
        return _no_finite_values_result(context, metrics)
    valid_relative_error = relative_error[valid_mask]
    mere = float(valid_relative_error.mean().item())
    mare = float(valid_relative_error.max().item())
    threshold = thresholds["threshold"]
    mare_threshold = 10.0 * threshold
    if mere < threshold and mare < mare_threshold:
        return _floating_result(
            True,
            context,
            f"PASS case '{context.case_id}' matched CANN Bench MERE/MARE at {context.output_path}.",
            replace(metrics, stage="mere_mare"),
            _RegionVerdict(),
        )
    work = _FloatingWork(
        metrics=metrics,
        actual_work=actual_work,
        golden_work=golden_work,
        golden_abs=golden_abs,
    )
    return _compare_floating_regions(context, work, native, mare_threshold)


def _no_finite_values_result(context: _LeafContext, metrics: _FloatingMetrics) -> CaseCompareResult:
    return case_result(
        passed=True,
        case_id=context.case_id,
        compute=context.compute,
        input_info=context.input_info,
        output_dtype=context.output_dtype,
        comparison_path="cann-bench",
        message=f"PASS case '{context.case_id}' had no finite output values at {context.output_path}.",
        diagnostics={
            **_floating_diagnostics(context.output_path, metrics, _RegionVerdict()),
            "failure_stage": None,
        },
    )


def _normalize_floating_operands(
    actual: torch.Tensor,
    golden: torch.Tensor,
    context: _LeafContext,
) -> tuple[torch.Tensor, torch.Tensor] | CaseCompareResult:
    try:
        golden_target = golden.to(dtype=actual.dtype)
        actual_work = actual.to(dtype=torch.float64).clone()
        golden_work = golden_target.to(dtype=torch.float64).clone()
    except RuntimeError as exc:
        return _failure_result(
            context,
            "unsupported_output_type",
            f"FAIL case '{context.case_id}' cannot normalize dtype '{context.output_dtype}' at {context.output_path}.",
            {"normalization_error": str(exc)},
        )
    return actual_work, golden_work


def _reconcile_special_values(
    actual_work: torch.Tensor,
    golden_work: torch.Tensor,
    actual_dtype: torch.dtype,
    context: _LeafContext,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor] | CaseCompareResult:
    """Check NaN/Inf placement and replace one-sided Inf with signed finfo max."""
    nan_actual = torch.isnan(actual_work)
    nan_golden = torch.isnan(golden_work)
    if not torch.equal(nan_actual, nan_golden):
        return _failure_result(
            context,
            "nan_mask_mismatch",
            f"FAIL case '{context.case_id}' NaN locations differ at {context.output_path}.",
            {"nan_mismatch_count": int(torch.count_nonzero(nan_actual != nan_golden).item())},
        )
    inf_actual = torch.isinf(actual_work)
    inf_golden = torch.isinf(golden_work)
    both_inf = inf_actual & inf_golden
    if bool(torch.any(both_inf).item()) and not torch.equal(
        torch.sign(actual_work[both_inf]), torch.sign(golden_work[both_inf])
    ):
        return _failure_result(
            context,
            "inf_sign_mismatch",
            f"FAIL case '{context.case_id}' Inf signs differ at {context.output_path}.",
            {},
        )
    one_sided_inf = inf_actual != inf_golden
    if bool(torch.any(one_sided_inf).item()):
        max_finite = float(torch.finfo(actual_dtype).max)
        actual_work[inf_actual & ~inf_golden] = torch.sign(actual_work[inf_actual & ~inf_golden]) * max_finite
        golden_work[inf_golden & ~inf_actual] = torch.sign(golden_work[inf_golden & ~inf_actual]) * max_finite
    return actual_work, golden_work, both_inf


def _compare_floating_regions(
    context: _LeafContext,
    work: _FloatingWork,
    native: torch.Tensor | None,
    mare_threshold: float,
) -> CaseCompareResult:
    masks = _floating_region_masks(work, mare_threshold)
    counts = _floating_region_counts(work, masks)
    native_counts = _native_region_error_counts(native, work, masks, mare_threshold)
    verdict = _floating_region_verdict(counts, native_counts, native_available=native is not None)
    passed = verdict.normal_passed and verdict.small_value_passed and verdict.cancel_passed
    stage = _floating_region_stage(verdict)
    comparison_source = "native reference" if verdict.native_reference_available else "special-value fallback"
    message = (
        f"PASS case '{context.case_id}' matched CANN Bench {comparison_source} at {context.output_path}."
        if passed
        else f"FAIL case '{context.case_id}' CANN Bench precision comparison failed at {context.output_path}."
    )
    final_metrics = replace(
        work.metrics,
        stage=stage,
        mismatch_count=int(torch.count_nonzero(masks.mismatch_mask).item()),
        small_error_count=counts.small_error_count,
        cancel_error_count=counts.cancel_error_count,
        normal_mismatch_count=counts.normal_mismatch_count,
        small_total_count=counts.small_total_count,
        cancel_total_count=counts.cancel_total_count,
        display_mask=_display_mask(
            valid_mask=work.metrics.valid_mask,
            small_mask=masks.small_mask,
            cancel_mask=masks.cancel_mask,
            normal_mismatch_count=counts.normal_mismatch_count,
            passed=passed,
        ),
        normal_mask=masks.normal_region_mask,
    )
    return _floating_result(passed, context, message, final_metrics, verdict)


def _floating_region_masks(work: _FloatingWork, mare_threshold: float) -> _RegionMasks:
    metrics = work.metrics
    thresholds = metrics.thresholds
    mismatch_mask = (metrics.relative_error > mare_threshold) & metrics.valid_mask
    small_mask = (work.golden_abs < thresholds["small_value_threshold"]) & metrics.valid_mask
    cancel_mask = (
        (work.actual_work.abs() < thresholds["cancel_zero_threshold"])
        & (work.golden_abs < thresholds["cancel_boundary"])
        & (work.golden_abs >= thresholds["small_value_threshold"])
        & metrics.valid_mask
    )
    normal_region_mask = ~small_mask & ~cancel_mask & metrics.valid_mask
    return _RegionMasks(
        mismatch_mask=mismatch_mask,
        small_mask=small_mask,
        cancel_mask=cancel_mask,
        normal_region_mask=normal_region_mask,
    )


def _floating_region_counts(work: _FloatingWork, masks: _RegionMasks) -> _RegionCounts:
    thresholds = work.metrics.thresholds
    return _RegionCounts(
        small_error_count=int(
            torch.count_nonzero(masks.small_mask & (work.metrics.diff > thresholds["small_value_error"])).item()
        ),
        cancel_error_count=int(torch.count_nonzero(masks.cancel_mask & masks.mismatch_mask).item()),
        small_total_count=int(torch.count_nonzero(masks.small_mask).item()),
        cancel_total_count=int(torch.count_nonzero(masks.cancel_mask).item()),
        normal_mismatch_count=int(
            torch.count_nonzero(masks.mismatch_mask & masks.normal_region_mask).item()
        ),
    )


def _native_region_error_counts(
    native: torch.Tensor | None,
    work: _FloatingWork,
    masks: _RegionMasks,
    mare_threshold: float,
) -> tuple[int, int, int]:
    if native is None:
        return 0, 0, 0
    thresholds = work.metrics.thresholds
    native_work = native.detach().cpu().to(dtype=torch.float64)
    native_diff = (native_work - work.golden_work).abs()
    native_relative_error = native_diff / (work.golden_abs + 1e-7)
    small_errors = int(
        torch.count_nonzero(masks.small_mask & (native_diff > thresholds["small_value_error"])).item()
    )
    cancel_errors = int(
        torch.count_nonzero(masks.cancel_mask & (native_relative_error > mare_threshold)).item()
    )
    # Align with cann-bench compare.py: normal-region CPU errors use the same
    # MARE threshold as the candidate (relative_error > 10 * threshold).
    normal_errors = int(
        torch.count_nonzero(masks.normal_region_mask & (native_relative_error > mare_threshold)).item()
    )
    return small_errors, cancel_errors, normal_errors


def _floating_region_verdict(
    counts: _RegionCounts,
    native_counts: tuple[int, int, int],
    *,
    native_available: bool,
) -> _RegionVerdict:
    native_small, native_cancel, native_normal = native_counts
    small_limit = 2 * max(native_small, 1)
    cancel_limit = 2 * max(native_cancel, 1)
    # Three independent region checks (cann-bench CompareResult style):
    # small_value_passed / cancel_passed / normal_passed, then AND.
    small_value_passed = counts.small_error_count <= small_limit
    cancel_passed = counts.cancel_error_count <= cancel_limit
    # Normal-region fallback (issue #92): only relax when same-precision native
    # itself exceeds MARE here. Clean / missing native stays strict.
    if counts.normal_mismatch_count == 0:
        normal_passed = True
    elif not native_available or native_normal == 0:
        normal_passed = False
    else:
        normal_passed = (counts.normal_mismatch_count / native_normal) <= 2.0
    return _RegionVerdict(
        native_small_error_count=native_small,
        native_cancel_error_count=native_cancel,
        native_normal_error_count=native_normal,
        native_reference_available=native_available,
        special_fallback=not native_available,
        small_value_passed=small_value_passed,
        cancel_passed=cancel_passed,
        normal_passed=normal_passed,
    )


def _floating_region_stage(verdict: _RegionVerdict) -> str:
    # failure_stage names the failing region; pass uses a single region_fallback label.
    # Native presence is reported via native_reference_available, not the stage name.
    if verdict.normal_passed and verdict.small_value_passed and verdict.cancel_passed:
        return "region_fallback"
    if not verdict.normal_passed:
        return "normal_value_mismatch"
    if not verdict.small_value_passed:
        return "small_value_mismatch"
    return "cancel_mismatch"


def _floating_result(
    passed: bool,
    context: _LeafContext,
    message: str,
    metrics: _FloatingMetrics,
    verdict: _RegionVerdict,
) -> CaseCompareResult:
    diagnostics = _floating_diagnostics(context.output_path, metrics, verdict)
    if not passed:
        diagnostics["failure_stage"] = metrics.stage
    return case_result(
        passed=passed,
        case_id=context.case_id,
        compute=context.compute,
        input_info=context.input_info,
        output_dtype=context.output_dtype,
        comparison_path="cann-bench",
        message=message,
        diagnostics=diagnostics,
    )


def _floating_diagnostics(
    output_path: str,
    metrics: _FloatingMetrics,
    verdict: _RegionVerdict,
) -> dict[str, object]:
    valid_count = int(torch.count_nonzero(metrics.valid_mask).item())
    overall_mere, overall_mare, max_diff, mean_diff = _overall_diff_metrics(metrics, valid_count)
    metrics_mask = metrics.valid_mask if metrics.display_mask is None else metrics.display_mask
    display_mere, display_mare = _relative_error_metrics(metrics.relative_error, metrics_mask)
    normal_mere, normal_mare = _relative_error_metrics(metrics.relative_error, metrics.normal_mask)
    return {
        "output_path": output_path,
        "tensor_shape": tuple(metrics.actual.shape),
        "thresholds": dict(metrics.thresholds),
        "mere": display_mere,
        "mare": display_mare,
        "overall_mere": overall_mere,
        "overall_mare": overall_mare,
        "normal_mere": normal_mere,
        "normal_mare": normal_mare,
        "max_diff": max_diff,
        "mean_diff": mean_diff,
        "mismatch_count": metrics.mismatch_count,
        "mismatch_ratio": metrics.mismatch_count / metrics.actual.numel() if metrics.actual.numel() else 0.0,
        "finite_count": valid_count,
        "small_value_error_count": metrics.small_error_count,
        "small_value_cpu_error_count": verdict.native_small_error_count,
        "small_value_total_count": metrics.small_total_count,
        "small_value_passed": verdict.small_value_passed,
        "small_value_fallback": verdict.special_fallback,
        "cancel_error_count": metrics.cancel_error_count,
        "cancel_cpu_error_count": verdict.native_cancel_error_count,
        "cancel_total_count": metrics.cancel_total_count,
        "cancel_passed": verdict.cancel_passed,
        "cancel_fallback": verdict.special_fallback,
        "native_reference_available": verdict.native_reference_available,
        "normal_mismatch_count": metrics.normal_mismatch_count,
        "normal_cpu_error_count": verdict.native_normal_error_count,
        "normal_passed": verdict.normal_passed,
        "comparison_stage": metrics.stage,
    }


def _overall_diff_metrics(
    metrics: _FloatingMetrics,
    valid_count: int,
) -> tuple[float, float, float, float]:
    if not valid_count:
        return 0.0, 0.0, 0.0, 0.0
    valid_diff = metrics.diff[metrics.valid_mask]
    valid_relative_error = metrics.relative_error[metrics.valid_mask]
    overall_mere = float(valid_relative_error.mean().item())
    overall_mare = float(valid_relative_error.max().item())
    max_diff = float(valid_diff.max().item())
    mean_diff = float(valid_diff.mean().item())
    return overall_mere, overall_mare, max_diff, mean_diff


def _display_mask(
    *,
    valid_mask: torch.Tensor,
    small_mask: torch.Tensor,
    cancel_mask: torch.Tensor,
    normal_mismatch_count: int,
    passed: bool,
) -> torch.Tensor:
    normal_mask = ~small_mask & ~cancel_mask & valid_mask
    if normal_mismatch_count > 0:
        return normal_mask if bool(torch.any(normal_mask).item()) else valid_mask
    if passed:
        return normal_mask
    return valid_mask


def _relative_error_metrics(
    relative_error: torch.Tensor,
    mask: torch.Tensor | None,
) -> tuple[float, float]:
    if mask is None or not bool(torch.any(mask).item()):
        return 0.0, 0.0
    selected = relative_error[mask]
    return float(selected.mean().item()), float(selected.max().item())


def _structure_error_result(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    error: OutputStructureError,
) -> CaseCompareResult:
    diagnostics: dict[str, object] = {"output_path": error.path, "failure_stage": error.kind}
    if error.kind == "key_mismatch":
        diagnostics.update(expected_keys=list(error.expected_keys), actual_keys=list(error.actual_keys))
        message = f"FAIL case '{case_id}' mapping keys differ at {error.path}."
    elif error.kind == "length_mismatch":
        diagnostics.update(expected_length=error.expected_length, actual_length=error.actual_length)
        message = f"FAIL case '{case_id}' sequence length differs at {error.path}."
    else:
        diagnostics.update(expected_type=error.expected_type, actual_type=error.actual_type)
        message = f"FAIL case '{case_id}' expected {error.expected_type} at {error.path}, got {error.actual_type}."
    return case_result(
        passed=False,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=None,
        comparison_path="structure-mismatch",
        message=message,
        diagnostics=diagnostics,
    )


def _unsupported_output_type_result(
    leaf: OutputLeaf,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
) -> CaseCompareResult:
    context = _LeafContext(
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_path=leaf.path,
        output_dtype=None,
    )
    return _failure_result(
        context,
        "unsupported_output_type",
        f"FAIL case '{case_id}' produced non-tensor output at {leaf.path}.",
        {"expected_type": type(leaf.golden).__name__, "actual_type": type(leaf.actual).__name__},
    )


def _failure_result(
    context: _LeafContext,
    stage: str,
    message: str,
    diagnostics: Mapping[str, object],
) -> CaseCompareResult:
    return case_result(
        passed=False,
        case_id=context.case_id,
        compute=context.compute,
        input_info=context.input_info,
        output_dtype=context.output_dtype,
        comparison_path="cann-bench" if stage != "unsupported_output_type" else "unsupported-output-type",
        message=message,
        diagnostics={"failure_stage": stage, "output_path": context.output_path, **diagnostics},
    )


def _precision_thresholds_from_extra(
    extra: Mapping[str, object] | None,
) -> Mapping[str, float] | None:
    """Parse optional extra['precision_thresholds'] for cann-bench MERE overrides."""
    if extra is None:
        return None
    raw = extra.get("precision_thresholds")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise TypeError("extra['precision_thresholds'] must be a mapping of dtype -> threshold")
    return {str(key).lower(): float(value) for key, value in raw.items()}


def _thresholds_for_dtype(
    output_dtype: str,
    precision_thresholds: Mapping[str, float] | None = None,
) -> dict[str, float]:
    key = _threshold_key(output_dtype)
    thresholds = {
        name: float(value)
        for name, value in CANN_BENCH_THRESHOLDS.get(key, _FALLBACK_THRESHOLDS).items()
    }
    if precision_thresholds:
        override = precision_thresholds.get(key.lower())
        if override is None:
            override = precision_thresholds.get(output_dtype.lower())
        if override is not None:
            thresholds["threshold"] = float(override)
    return thresholds


def _threshold_key(output_dtype: str) -> str:
    if output_dtype.startswith("float8_e4m3"):
        return "float8_e4m3"
    if output_dtype.startswith("float8_e5m2"):
        return "float8_e5m2"
    return output_dtype


def _dtype_name(dtype: torch.dtype) -> str:
    return str(dtype).replace("torch.", "")

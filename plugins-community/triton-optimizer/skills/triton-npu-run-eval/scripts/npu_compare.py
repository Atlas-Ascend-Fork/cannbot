# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable, Optional, cast

from dtype_close_compare import compare_dtype_close_case
from cann_bench_compare import compare_cann_bench_case
from npu_compare_common import (
    ArtifactCompareResult,
    CaseCompareResult,
    DEFAULT_ACCURACY_MODE,
    InputInfo,
    case_result,
    current_accuracy_mode,
    reset_current_accuracy_mode,
    resolve_accuracy_mode,
    set_current_accuracy_mode,
)
from npu_contract_compare import compare_npu_contract_case


@dataclass(frozen=True)
class _CaseRecord:
    case_id: str
    inputs: object
    result: object


def compare_case_result(
    *,
    case_id: str,
    actual: object,
    golden: object,
    inputs: object,
    compute: bool = True,
    accuracy_mode: str | None = None,
    native_ref_operator: Optional[Callable[[object], object]] = None,
    extra: Mapping[str, object] | None = None,
) -> CaseCompareResult:
    resolved_accuracy_mode = resolve_accuracy_mode(accuracy_mode)
    token = set_current_accuracy_mode(resolved_accuracy_mode)
    try:
        if resolved_accuracy_mode == "dtype-close":
            return compare_dtype_close_case(
                case_id=case_id,
                actual=actual,
                golden=golden,
                compute=compute,
            )
        if resolved_accuracy_mode == "cann-bench":
            return compare_cann_bench_case(
                case_id=case_id,
                actual=actual,
                golden=golden,
                compute=compute,
                inputs=inputs,
                native_ref_operator=native_ref_operator,
                extra=extra,
            )
        return compare_npu_contract_case(
            case_id=case_id,
            actual=actual,
            golden=golden,
            inputs=inputs,
            compute=compute,
        )
    finally:
        reset_current_accuracy_mode(token)


def compare_result_payloads(
    oracle_payload: object,
    actual_payload: object,
    accuracy_mode: str | None = None,
    native_ref_operator: Optional[Callable[[object], object]] = None,
    extra: Mapping[str, object] | None = None,
) -> ArtifactCompareResult:
    resolved_accuracy_mode = resolve_accuracy_mode(accuracy_mode)
    token = set_current_accuracy_mode(resolved_accuracy_mode)
    try:
        return _compare_result_payloads_in_current_mode(
            oracle_payload, actual_payload, native_ref_operator, extra
        )
    finally:
        reset_current_accuracy_mode(token)


def _compare_result_payloads_in_current_mode(
    oracle_payload: object,
    actual_payload: object,
    native_ref_operator: Optional[Callable[[object], object]],
    extra: Mapping[str, object] | None,
) -> ArtifactCompareResult:
    accuracy_mode = current_accuracy_mode()
    oracle_cases, oracle_error = _extract_case_records(oracle_payload, "oracle")
    if oracle_error is not None:
        return _payload_error("oracle", oracle_error, accuracy_mode)
    actual_cases, actual_error = _extract_case_records(actual_payload, "actual_payload")
    if actual_error is not None:
        return _payload_error("actual_payload", actual_error, accuracy_mode)
    if len(oracle_cases) != len(actual_cases):
        return _case_count_mismatch_result(oracle_cases, actual_cases, accuracy_mode)
    oracle_compute = _payload_compute_flag(oracle_payload)
    actual_compute = _payload_compute_flag(actual_payload)
    if accuracy_mode != "cann-bench" and oracle_compute != actual_compute:
        return _compute_kind_mismatch_result(oracle_compute, actual_compute, accuracy_mode)
    case_results = _compare_payload_cases(
        oracle_cases,
        actual_cases,
        oracle_compute,
        accuracy_mode=accuracy_mode,
        native_ref_operator=native_ref_operator,
        extra=extra,
    )
    return _aggregate_case_results(case_results, accuracy_mode)


def _case_count_mismatch_result(
    oracle_cases: list[_CaseRecord],
    actual_cases: list[_CaseRecord],
    accuracy_mode: str,
) -> ArtifactCompareResult:
    return ArtifactCompareResult(
        passed=False,
        failed_case_count=1,
        case_results=(),
        message=(
            "FAIL: payload case count mismatch: "
            f"oracle={len(oracle_cases)}, actual_payload={len(actual_cases)}"
        ),
        diagnostics={
            "oracle_case_count": len(oracle_cases),
            "actual_case_count": len(actual_cases),
            "accuracy_mode": accuracy_mode,
        },
    )


def _compute_kind_mismatch_result(
    oracle_compute: bool,
    actual_compute: bool,
    accuracy_mode: str,
) -> ArtifactCompareResult:
    return ArtifactCompareResult(
        passed=False,
        failed_case_count=1,
        case_results=(),
        message=(
            "FAIL: payload compute-kind mismatch: "
            f"oracle={oracle_compute}, actual_payload={actual_compute}"
        ),
        diagnostics={
            "oracle_compute": oracle_compute,
            "actual_compute": actual_compute,
            "accuracy_mode": accuracy_mode,
        },
    )


def _compare_payload_cases(
    oracle_cases: list[_CaseRecord],
    actual_cases: list[_CaseRecord],
    oracle_compute: bool,
    *,
    accuracy_mode: str,
    native_ref_operator: Optional[Callable[[object], object]],
    extra: Mapping[str, object] | None,
) -> list[CaseCompareResult]:
    case_results: list[CaseCompareResult] = []
    for index, (oracle_case, actual_case) in enumerate(zip(oracle_cases, actual_cases)):
        if oracle_case.case_id != actual_case.case_id:
            case_results.append(_case_id_mismatch(oracle_case.case_id, actual_case.case_id, index, oracle_compute))
            continue
        case_results.append(
            compare_case_result(
                case_id=oracle_case.case_id,
                actual=actual_case.result,
                golden=oracle_case.result,
                inputs=oracle_case.inputs,
                compute=oracle_compute,
                accuracy_mode=accuracy_mode,
                native_ref_operator=native_ref_operator,
                extra=extra,
            )
        )
    return case_results


def _aggregate_case_results(
    case_results: list[CaseCompareResult],
    accuracy_mode: str,
) -> ArtifactCompareResult:
    failed = [result for result in case_results if not result.passed]
    if failed:
        return ArtifactCompareResult(
            passed=False,
            failed_case_count=len(failed),
            case_results=tuple(case_results),
            message=(
                f"FAIL: {len(failed)} of {len(case_results)} case(s) failed. "
                f"First failure: {failed[0].message}"
            ),
            diagnostics={"case_count": len(case_results), "accuracy_mode": accuracy_mode},
        )
    message = (
        f"PASS: all {len(case_results)} case(s) matched the NPU accuracy contract."
        if accuracy_mode == DEFAULT_ACCURACY_MODE
        else f"PASS: all {len(case_results)} case(s) matched with accuracy mode '{accuracy_mode}'."
    )
    return ArtifactCompareResult(
        passed=True,
        failed_case_count=0,
        case_results=tuple(case_results),
        message=message,
        diagnostics={"case_count": len(case_results), "accuracy_mode": accuracy_mode},
    )


def _payload_error(payload: str, error: str, accuracy_mode: str) -> ArtifactCompareResult:
    return ArtifactCompareResult(
        passed=False,
        failed_case_count=1,
        case_results=(),
        message=f"FAIL: {error}",
        diagnostics={"payload": payload, "accuracy_mode": accuracy_mode},
    )


def _case_id_mismatch(
    oracle_case_id: str,
    actual_case_id: str,
    index: int,
    compute: bool,
) -> CaseCompareResult:
    return case_result(
        passed=False,
        case_id=oracle_case_id,
        compute=compute,
        input_info=InputInfo(input_type="no_tensor", input_dtype=None),
        output_dtype=None,
        comparison_path="payload-case-order",
        message=(
            "FAIL payload case order mismatch at index "
            f"{index}: oracle={oracle_case_id!r}, actual_payload={actual_case_id!r}"
        ),
        diagnostics={
            "failure_stage": "case_id_mismatch",
            "index": index,
            "oracle_case_id": oracle_case_id,
            "actual_case_id": actual_case_id,
        },
    )


def _extract_case_records(payload: object, label: str) -> tuple[list[_CaseRecord], str | None]:
    if not isinstance(payload, Mapping):
        return [], f"{label} payload must be a dict with a 'cases' entry"
    payload_map = cast(Mapping[str, object], payload)
    if "results" in payload_map:
        return [], (
            f"{label} payload uses the legacy payload format. "
            "Expected {'compute': <bool>, 'cases': [...]} instead of {'results': [...]}."
        )
    raw_cases = payload_map.get("cases")
    if not isinstance(raw_cases, list):
        return [], f"{label} payload 'cases' must be a list"
    records: list[_CaseRecord] = []
    for raw_case in cast(list[object], raw_cases):
        if not isinstance(raw_case, Mapping):
            return [], f"{label} payload cases must be mappings"
        case_map = cast(Mapping[str, object], raw_case)
        case_id = case_map.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            return [], f"{label} payload case is missing required string field 'id'"
        if "inputs" not in case_map:
            return [], f"{label} payload case '{case_id}' is missing required field 'inputs'"
        if "result" not in case_map:
            return [], f"{label} payload case '{case_id}' is missing required field 'result'"
        records.append(_CaseRecord(case_id=case_id, inputs=case_map["inputs"], result=case_map["result"]))
    return records, None


def _payload_compute_flag(payload: object) -> bool:
    if not isinstance(payload, Mapping):
        return True
    raw_compute = cast(Mapping[str, object], payload).get("compute")
    return raw_compute if isinstance(raw_compute, bool) else True

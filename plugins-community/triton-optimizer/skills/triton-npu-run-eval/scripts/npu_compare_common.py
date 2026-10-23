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

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
import os
from typing import cast

from env_registry import HELIX_ACCURACY_MODE


DEFAULT_ACCURACY_MODE = "npu-contract"
ACCURACY_MODES = frozenset({DEFAULT_ACCURACY_MODE, "dtype-close", "cann-bench"})
_CURRENT_ACCURACY_MODE: ContextVar[str | None] = ContextVar(
    "helix_current_accuracy_mode",
    default=None,
)


@dataclass(frozen=True)
class CaseCompareResult:
    passed: bool
    case_id: str
    compute: bool
    input_type: str
    input_dtype: str | None
    output_dtype: str | None
    comparison_path: str
    message: str
    diagnostics: Mapping[str, object]


@dataclass(frozen=True)
class ArtifactCompareResult:
    passed: bool
    failed_case_count: int
    case_results: tuple[CaseCompareResult, ...]
    message: str
    diagnostics: Mapping[str, object]


@dataclass(frozen=True)
class InputInfo:
    input_type: str
    input_dtype: str | None


@dataclass(frozen=True)
class OutputLeaf:
    path: str
    actual: object
    golden: object


@dataclass(frozen=True)
class OutputStructureError:
    path: str
    kind: str
    expected_type: str | None = None
    actual_type: str | None = None
    expected_keys: tuple[object, ...] = ()
    actual_keys: tuple[object, ...] = ()
    expected_length: int | None = None
    actual_length: int | None = None


@dataclass(frozen=True)
class OutputTraversal:
    leaves: tuple[OutputLeaf, ...]
    error: OutputStructureError | None


def resolve_accuracy_mode(accuracy_mode: str | None) -> str:
    raw_value = accuracy_mode if accuracy_mode is not None else os.environ.get(HELIX_ACCURACY_MODE)
    if raw_value is None or not raw_value.strip():
        return DEFAULT_ACCURACY_MODE
    normalized = raw_value.strip().lower()
    if normalized not in ACCURACY_MODES:
        supported = ", ".join(sorted(ACCURACY_MODES))
        raise ValueError(f"accuracy_mode must be one of {supported}, got {raw_value!r}")
    return normalized


def set_current_accuracy_mode(accuracy_mode: str) -> Token[str | None]:
    return _CURRENT_ACCURACY_MODE.set(accuracy_mode)


def reset_current_accuracy_mode(token: Token[str | None]) -> None:
    _CURRENT_ACCURACY_MODE.reset(token)


def current_accuracy_mode() -> str:
    current = _CURRENT_ACCURACY_MODE.get()
    if current is not None:
        return current
    return resolve_accuracy_mode(None)


def is_sequence_output(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def traverse_output_leaves(
    actual: object,
    golden: object,
    output_path: str = "output",
) -> OutputTraversal:
    """Pair matching output leaves without applying a comparison policy."""
    leaves: list[OutputLeaf] = []
    error = _traverse_output_leaves(actual, golden, output_path, leaves)
    return OutputTraversal(leaves=tuple(leaves), error=error)


def _traverse_output_leaves(
    actual: object,
    golden: object,
    output_path: str,
    leaves: list[OutputLeaf],
) -> OutputStructureError | None:
    if isinstance(golden, Mapping):
        return _traverse_mapping_leaves(actual, golden, output_path, leaves)
    if is_sequence_output(golden):
        return _traverse_sequence_leaves(actual, golden, output_path, leaves)
    leaves.append(OutputLeaf(path=output_path, actual=actual, golden=golden))
    return None


def _traverse_mapping_leaves(
    actual: object,
    golden: object,
    output_path: str,
    leaves: list[OutputLeaf],
) -> OutputStructureError | None:
    if not isinstance(actual, Mapping):
        return OutputStructureError(
            path=output_path,
            kind="type_mismatch",
            expected_type="mapping",
            actual_type=type(actual).__name__,
        )
    golden_map = cast(Mapping[object, object], golden)
    actual_map = cast(Mapping[object, object], actual)
    golden_keys = tuple(sorted(golden_map, key=str))
    actual_keys = tuple(sorted(actual_map, key=str))
    if set(golden_keys) != set(actual_keys):
        return OutputStructureError(
            path=output_path,
            kind="key_mismatch",
            expected_keys=golden_keys,
            actual_keys=actual_keys,
        )
    for key in golden_keys:
        error = _traverse_output_leaves(
            actual_map[key], golden_map[key], f"{output_path}.{key}", leaves
        )
        if error is not None:
            return error
    return None


def _traverse_sequence_leaves(
    actual: object,
    golden: object,
    output_path: str,
    leaves: list[OutputLeaf],
) -> OutputStructureError | None:
    if not is_sequence_output(actual):
        return OutputStructureError(
            path=output_path,
            kind="type_mismatch",
            expected_type="sequence",
            actual_type=type(actual).__name__,
        )
    golden_sequence = cast(Sequence[object], golden)
    actual_sequence = cast(Sequence[object], actual)
    if len(actual_sequence) != len(golden_sequence):
        return OutputStructureError(
            path=output_path,
            kind="length_mismatch",
            expected_length=len(golden_sequence),
            actual_length=len(actual_sequence),
        )
    for index, golden_item in enumerate(golden_sequence):
        error = _traverse_output_leaves(
            actual_sequence[index], golden_item, f"{output_path}[{index}]", leaves
        )
        if error is not None:
            return error
    return None


def unexpected_failure_result(
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    *,
    comparison_path: str,
    message: str,
    diagnostics: Mapping[str, object],
) -> CaseCompareResult:
    """Shared minimal failure-result builder for comparison policies."""
    return case_result(
        passed=False,
        case_id=case_id,
        compute=compute,
        input_info=input_info,
        output_dtype=None,
        comparison_path=comparison_path,
        message=message,
        diagnostics=diagnostics,
    )


def case_result(
    *,
    passed: bool,
    case_id: str,
    compute: bool,
    input_info: InputInfo,
    output_dtype: str | None,
    comparison_path: str,
    message: str,
    diagnostics: Mapping[str, object],
) -> CaseCompareResult:
    return CaseCompareResult(
        passed=passed,
        case_id=case_id,
        compute=compute,
        input_type=input_info.input_type,
        input_dtype=input_info.input_dtype,
        output_dtype=output_dtype,
        comparison_path=comparison_path,
        message=message,
        diagnostics={
            "case_id": case_id,
            "compute": compute,
            "input_type": input_info.input_type,
            "input_dtype": input_info.input_dtype,
            **diagnostics,
            "accuracy_mode": current_accuracy_mode(),
        },
    )

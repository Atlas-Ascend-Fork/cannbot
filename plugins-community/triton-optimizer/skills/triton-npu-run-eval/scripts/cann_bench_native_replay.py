# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Lazy CPU replay support for CANN Bench native-reference comparison."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from test_contract import (
    SCRIPT_DIR,
    bootstrap_torch_npu,
    load_module,
    require_callable,
    temporary_sys_path_entries,
)


def create_native_ref_operator(test_file: Path, operator_file: Path) -> Callable[[object], object]:
    """Return a cached, lazy CPU replay callable for one reference operator."""
    loaded_operator: object | None = None

    def replay(inputs: object) -> object:
        nonlocal loaded_operator
        if loaded_operator is None:
            loaded_operator = _load_operator_api(test_file, operator_file)
        arguments = _copy_to_cpu(inputs)
        if not isinstance(arguments, (tuple, list)):
            raise ValueError("Differential artifact case inputs must be a tuple or list")
        result = cast(Callable[..., object], loaded_operator)(*arguments)
        _synchronize_if_available()
        return result

    return replay


def snapshot_differential_inputs(inputs: object) -> object:
    """Detach and clone inputs before execution preserves replayable arguments."""
    return _copy_tensor_tree(inputs, move_to_cpu=False)


def _load_operator_api(test_file: Path, operator_file: Path) -> object:
    test_path = test_file.resolve()
    operator_path = operator_file.resolve()
    bootstrap_torch_npu(test_path.parent, operator_path.parent)
    with temporary_sys_path_entries(test_path.parent, operator_path.parent, SCRIPT_DIR):
        test_module = load_module(test_path, f"cann_bench_native_test_{test_path.stem}")
        build_operator_api = require_callable(test_module, "build_operator_api", test_path)
        operator_module = load_module(operator_path, f"cann_bench_native_operator_{operator_path.stem}")
        return build_operator_api(operator_module)


def _copy_to_cpu(value: object) -> object:
    return _copy_tensor_tree(value, move_to_cpu=True)


def _copy_tensor_tree(value: object, *, move_to_cpu: bool) -> object:
    tensor_type = _torch_tensor_type()
    if tensor_type is not None and isinstance(value, tensor_type):
        tensor = cast(Any, value).detach().clone()
        return tensor.cpu() if move_to_cpu else tensor
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {
            key: _copy_tensor_tree(item, move_to_cpu=move_to_cpu)
            for key, item in mapping.items()
        }
    if isinstance(value, tuple):
        tuple_value = cast(tuple[object, ...], value)
        copied: tuple[object, ...] = tuple(
            _copy_tensor_tree(item, move_to_cpu=move_to_cpu)
            for item in tuple_value
        )
        if hasattr(tuple_value, "_fields"):
            return cast(Any, type(tuple_value))(*copied)
        return copied
    if isinstance(value, list):
        return [
            _copy_tensor_tree(item, move_to_cpu=move_to_cpu)
            for item in cast(list[object], value)
        ]
    return value


def _torch_tensor_type() -> type[object] | None:
    try:
        import torch
    except ImportError:
        return None
    tensor_type = getattr(torch, "Tensor", None)
    return cast(type[object], tensor_type) if isinstance(tensor_type, type) else None


def _synchronize_if_available() -> None:
    try:
        import torch
    except ImportError:
        return
    synchronize = getattr(getattr(torch, "npu", None), "synchronize", None)
    if callable(synchronize):
        synchronize()

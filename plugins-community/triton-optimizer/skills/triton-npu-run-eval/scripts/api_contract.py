# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared generated-harness metadata and public-entrypoint contract."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final


CANONICAL_API_KINDS: Final = frozenset({"torch-function", "torch-module"})
API_KIND_ALIASES: Final = {
    "triton-wrapper": "torch-function",
    "tilelang-wrapper": "torch-function",
    "torch-function": "torch-function",
    "torch-module": "torch-module",
}


def normalize_api_kind(raw_api_kind: object) -> str:
    """Normalize canonical and legacy metadata values to the public contract."""
    if not isinstance(raw_api_kind, str):
        raise ValueError(f"unsupported api-kind: {raw_api_kind}")
    normalized = API_KIND_ALIASES.get(raw_api_kind.strip())
    if normalized is None:
        raise ValueError(f"unsupported api-kind: {raw_api_kind}")
    return normalized


def parse_metadata(metadata_file: Path) -> dict[str, str]:
    """Parse a generated harness's leading metadata comment block."""
    metadata: dict[str, str] = {}
    for line in metadata_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            if metadata:
                break
            continue
        if not stripped.startswith("#"):
            break
        body = stripped[1:].strip()
        if ":" not in body:
            continue
        key, value = body.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def resolve_operator_api(
    operator_module: object, metadata: Mapping[str, str], operator_path: Path
) -> object:
    """Resolve the declared public operator entrypoint into an invokable object."""
    api_name = metadata.get("api-name")
    api_kind = metadata.get("api-kind")
    if not api_name:
        raise ValueError(f"Test metadata is missing required 'api-name' entry: {operator_path}")
    if api_kind is None:
        raise ValueError(f"Test metadata is missing required 'api-kind' entry: {operator_path}")
    try:
        normalized_api_kind = normalize_api_kind(api_kind)
    except ValueError as exc:
        raise ValueError(
            f"Test metadata has unsupported 'api-kind' entry '{api_kind}': {operator_path}"
        ) from exc
    candidate = getattr(operator_module, api_name, None)
    if candidate is None:
        raise ValueError(f"Runtime operator file is missing required API '{api_name}': {operator_path}")
    if normalized_api_kind == "torch-module":
        if not callable(candidate):
            raise ValueError(f"Runtime operator API '{api_name}' is not callable: {operator_path}")
        try:
            return candidate()
        except TypeError as exc:
            raise RuntimeError(
                "torch-module entrypoints must support no-argument construction; "
                "constructor arguments are not supported in generated harnesses"
            ) from exc
    return candidate

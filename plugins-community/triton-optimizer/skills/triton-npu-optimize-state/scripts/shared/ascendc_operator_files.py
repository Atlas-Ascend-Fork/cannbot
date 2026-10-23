# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Small helpers for the supported single-file AscendC operator pair."""

from __future__ import annotations

import ast
from pathlib import Path


def ascendc_source_path(operator_api_path: Path) -> Path:
    return operator_api_path.with_suffix(".asc")


def imports_ascendc_ops(operator_api_path: Path) -> bool:
    try:
        tree = ast.parse(operator_api_path.read_text(encoding="utf-8"), filename=str(operator_api_path))
    except (OSError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "ascendc_ops" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "ascendc_ops":
            return True
    return False


def is_ascendc_api(operator_api_path: Path) -> bool:
    return (
        operator_api_path.suffix == ".py"
        and operator_api_path.is_file()
        and imports_ascendc_ops(operator_api_path)
    )


def is_ascendc_operator(operator_api_path: Path) -> bool:
    return is_ascendc_api(operator_api_path) and ascendc_source_path(operator_api_path).is_file()

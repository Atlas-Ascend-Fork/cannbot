#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Language routing shared by request freezing and dependency preflight."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

BACKENDS = ("ascendc", "cannbot_dsl")
DSL_EXECUTION_MODES = ("jit", "aot")


def validate_backend(request: dict[str, Any], *, validate_live: bool = True) -> str:
    # Legacy requests keep their AscendC meaning; never infer from a .py suffix.
    backend = request.get("backend", "ascendc")
    if backend not in BACKENDS:
        raise ValueError(f"invalid performance backend: {backend}")
    dsl = request.get("dsl")
    if backend == "ascendc":
        if dsl is not None:
            raise ValueError("dsl configuration requires backend=cannbot_dsl")
        return backend
    if not isinstance(dsl, dict):
        raise ValueError("cannbot_dsl requires dsl configuration")
    if dsl.get("execution_mode") not in DSL_EXECUTION_MODES:
        raise ValueError("dsl.execution_mode must be jit or aot")
    entry = dsl.get("entrypoint")
    if not isinstance(entry, str) or not re.fullmatch(
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", entry
    ):
        raise ValueError("dsl.entrypoint must be module:callable (including dotted names)")
    root = dsl.get("repo_root")
    if not isinstance(root, str) or not Path(root).is_absolute():
        raise ValueError("dsl.repo_root must be an absolute path")
    if validate_live and not Path(root).is_dir():
        raise ValueError(f"DSL repository is unavailable: {root}")
    if dsl.get("workload_scope", "network_cases") != "network_cases":
        raise ValueError("dsl.workload_scope must be network_cases")
    return backend

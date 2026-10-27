#!/usr/bin/env python3

# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Shared helpers for triton-auto-evolve session hooks (SessionStart / SessionEnd)."""

from __future__ import annotations

import os
from pathlib import Path


def is_worker_mode() -> bool:
    """Return True if running as a per-round sub-agent worker.

    Workers receive all required context via manifest.json and must not touch
    the orchestrator's .triton-agent/ runtime tree.
    """
    return os.environ.get("TRITON_OPTIMIZER_MODE", "").lower() == "worker"


def resolve_workspace(payload: dict[str, object]) -> Path | None:
    """Resolve the workspace directory from the hook payload cwd."""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).expanduser().resolve()
    return None

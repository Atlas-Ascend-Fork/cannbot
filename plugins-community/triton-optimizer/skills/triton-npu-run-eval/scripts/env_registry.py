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

import os
from typing import Optional

# Shared HELIX contract envs
HELIX_ACCURACY_MODE = "HELIX_RUN_TEST_ACCURACY_MODE"
HELIX_DTYPE_CLOSE_ATOL = "HELIX_RUN_TEST_ATOL"
HELIX_DTYPE_CLOSE_RTOL = "HELIX_RUN_TEST_RTOL"
HELIX_PYTHON = "HELIX_PYTHON"
HELIX_SSH_TIMEOUT_SECONDS = "HELIX_SSH_TIMEOUT_SECONDS"
HELIX_SCP_TIMEOUT_SECONDS = "HELIX_SCP_TIMEOUT_SECONDS"
HELIX_EVAL_TIMEOUT_SECONDS = "HELIX_EVAL_TIMEOUT_SECONDS"
HELIX_SIMULATOR_SOC_VERSION = "HELIX_SIMULATOR_SOC_VERSION"
HELIX_BENCH_OUTPUT_DIR = "HELIX_BENCH_OUTPUT_DIR"
HELIX_BENCH_COPY_FILES = "HELIX_BENCH_COPY_FILES"
HELIX_BENCH_DEFER_PARSE = "HELIX_BENCH_DEFER_PARSE"
HELIX_PREWARM_TRITON = "HELIX_PREWARM_TRITON"
HELIX_PREWARM_WORKERS = "HELIX_PREWARM_WORKERS"
HELIX_OPTIMIZE_DELETE_PT_FILES = "HELIX_OPTIMIZE_DELETE_PT_FILES"
HELIX_REMOTE = "HELIX_REMOTE"
HELIX_REMOTE_WORKDIR = "HELIX_REMOTE_WORKDIR"
HELIX_DEBUG = "HELIX_DEBUG"


# Mirrors the true half of the CLI's boolean validation whitelist
# (src/helix/environment.py::_boolean); anything else is treated as off.
_FLAG_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in _FLAG_TRUE_VALUES


def bench_defer_parse_enabled() -> bool:
    return env_flag(HELIX_BENCH_DEFER_PARSE)


def prewarm_enabled() -> bool:
    return env_flag(HELIX_PREWARM_TRITON)


def bench_output_dir() -> Optional[str]:
    value = os.environ.get(HELIX_BENCH_OUTPUT_DIR, "").strip()
    return value or None


# Runtime control envs shared with toolchain / backend
TRITON_ALL_BLOCKS_PARALLEL = "TRITON_ALL_BLOCKS_PARALLEL"
TRITON_ALWAYS_COMPILE = "TRITON_ALWAYS_COMPILE"
TRITON_AUTOTUNE_PARALLEL_COMPILE = "TRITON_AUTOTUNE_PARALLEL_COMPILE"
TRITON_CACHE_DIR = "TRITON_CACHE_DIR"
TORCH_DEVICE_BACKEND_AUTOLOAD = "TORCH_DEVICE_BACKEND_AUTOLOAD"
ASCEND_RT_VISIBLE_DEVICES = "ASCEND_RT_VISIBLE_DEVICES"

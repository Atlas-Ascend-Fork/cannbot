# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Stable Helix-facing API for the triton-npu-run-eval run-test workflow."""

from __future__ import annotations


__all__ = (
    "parse_metadata",
    "handle_run_test_command",
    "run_local_test",
    "run_remote_test",
    "run_remote_differential_comparison",
)


from api_contract import parse_metadata
from run_test_command import handle_run_test_command
from run_test_local_api import run_local_test
from run_test_remote_api import (
    run_remote_differential_comparison,
    run_remote_test,
)



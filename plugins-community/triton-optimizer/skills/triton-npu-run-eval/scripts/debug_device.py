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
from collections.abc import Mapping

from env_registry import ASCEND_RT_VISIBLE_DEVICES, HELIX_DEBUG
_DEBUG_PREFIX = "[HELIX_DEBUG]"


def debug_enabled(env: Mapping[str, str] | None = None) -> bool:
    current_env = os.environ if env is None else env
    raw = current_env.get(HELIX_DEBUG, "")
    return raw.strip().lower() in {"true", "1"}


def maybe_print_visible_devices(env: Mapping[str, str] | None = None) -> None:
    current_env = os.environ if env is None else env
    if not debug_enabled(current_env):
        return
    value = current_env.get(ASCEND_RT_VISIBLE_DEVICES, "<unset>")
    print(f"{_DEBUG_PREFIX} {ASCEND_RT_VISIBLE_DEVICES}={value}")

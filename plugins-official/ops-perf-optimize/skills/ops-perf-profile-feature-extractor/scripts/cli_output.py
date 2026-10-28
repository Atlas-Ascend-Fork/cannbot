# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared command output helper for the ops-perf-profile-feature-extractor scripts."""

from __future__ import annotations

import sys
from typing import Optional, TextIO


def emit(*values: object, file: Optional[TextIO] = None, sep: str = " ", end: str = "\n") -> None:
    """Write command output without depending on the builtin print()."""
    stream = file if file is not None else sys.stdout
    stream.write(sep.join(str(value) for value in values) + end)

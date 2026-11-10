# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Shared subprocess entry point for version-management regression fixtures."""

import subprocess
import sys
from support import SCRIPTS


def run_code_versions(work, action, *args):
    """Run the version CLI for real-Git test fixtures."""
    command = [
        sys.executable,
        str(SCRIPTS / "code_versions.py"),
        "--work-dir",
        str(work),
        action,
        *map(str, args),
    ]
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8")

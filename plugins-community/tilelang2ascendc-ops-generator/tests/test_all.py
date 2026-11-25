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
"""运行 tests/ 下的全部 UT。

用法：python3 tests/test_all.py
"""

import logging
import subprocess
import sys
from pathlib import Path


LOGGER = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    root = Path(__file__).resolve().parent
    modules = sorted(
        path
        for path in root.rglob("test_*.py")
        if path.parent != root or path.name != "test_all.py"
    )
    failed = []
    for path in modules:
        relative = path.relative_to(root)
        LOGGER.info("\n=== %s ===", relative)
        result = subprocess.run(
            [sys.executable, "-B", str(path)], cwd=root, shell=False
        )
        if result.returncode:
            failed.append(str(relative))
    LOGGER.info(
        "\nUT modules: %s passed, %s failed", len(modules) - len(failed), len(failed)
    )
    if failed:
        LOGGER.error("Failed: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

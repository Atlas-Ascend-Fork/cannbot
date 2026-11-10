# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Shared CLI and subprocess setup for Node integration test categories."""
import argparse
import logging
import subprocess
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def run_node_tests(entry, source, test_names, *, assemble=False):
    """Validate the source checkout, optionally build packages, then run Node tests."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Run this plugin's Node integration contracts.")
    parser.add_argument('--harness-skill', type=Path)
    parser.parse_args()
    root = Path(entry).resolve().parent
    repository = root.parents[3]
    if not (repository / source).is_file():
        LOGGER.error(
            "%s integration tests require the complete CANNBot source checkout; "
            "run this category from plugins-official/ops-direct-invoke/tests in that checkout.", root.name
        )
        return 2
    if assemble:
        build = subprocess.run(
            ['node', str(repository / 'script/scripts/assemble-plugins.js'), 'dist'], cwd=repository / 'script'
        )
        if build.returncode:
            return build.returncode
    tests = [str(root / name) for name in test_names]
    return subprocess.run(['node', '--test', *tests], cwd=repository).returncode

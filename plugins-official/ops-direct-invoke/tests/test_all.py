#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Discover every UT category's test.py, run all, and fail if any category fails."""
import argparse
import logging
import subprocess
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness-skill', type=Path, help='override the shared harness Skill location')
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    root = Path(__file__).absolute().parent
    categories = []
    for path in root.iterdir():
        if path.is_dir() and path.name != 'helpers' and not path.name.startswith(('.', '_')):
            categories.append(path)
    categories.sort()
    if not categories:
        LOGGER.error('No UT categories found.')
        return 1
    failed = []
    for category in categories:
        LOGGER.info('\n=== %s ===', category.name)
        entry = category / 'test.py'
        if not entry.is_file():
            LOGGER.error('Missing required test entry: %s', entry)
            failed.append(category.name)
            continue
        command = [sys.executable, '-B', str(entry)]
        if args.harness_skill:
            command.extend(['--harness-skill', str(args.harness_skill.resolve())])
        try:
            result = subprocess.run(command, cwd=root)
            if result.returncode:
                failed.append(category.name)
        except OSError as error:
            LOGGER.error('%s', error)
            failed.append(category.name)
    LOGGER.info('\nUT categories: %s passed, %s failed', len(categories) - len(failed), len(failed))
    if failed:
        LOGGER.error('Failed: %s', ', '.join(failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

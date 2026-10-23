# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared path-resolution and import-path helpers for command scripts."""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Iterator


def require_existing_path(raw_path: str, label: str) -> Path:
    """Resolve raw_path to an existing path, raising ValueError otherwise."""
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"{label} path does not exist: {path}")
    return path


def resolve_existing_path(parser: argparse.ArgumentParser, raw_path: str, label: str) -> Path:
    try:
        return require_existing_path(raw_path, label)
    except ValueError as exc:
        # parser.error is NoReturn (it exits the CLI); returning it keeps every
        # branch of this function an explicit return.
        return parser.error(str(exc))


def resolve_optional_existing_path(
    parser: argparse.ArgumentParser, raw_path: str | None, label: str
) -> Path | None:
    if raw_path is None:
        return None
    return resolve_existing_path(parser, raw_path, label)


@contextlib.contextmanager
def temporary_sys_path_entry(path: str) -> Iterator[None]:
    added = False
    if path not in sys.path:
        sys.path.insert(0, path)
        added = True
    try:
        yield
    finally:
        if added:
            sys.path.remove(path)

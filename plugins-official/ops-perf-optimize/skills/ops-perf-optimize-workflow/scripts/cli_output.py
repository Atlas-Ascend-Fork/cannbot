# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Shared command output helper for the ops-perf-optimize workflow scripts."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, TextIO


def emit(
    *values: object,
    file: Optional[TextIO] = None,
    sep: str = " ",
    end: str = "\n",
    flush: bool = False,
) -> None:
    """Write command output without depending on the builtin print()."""
    stream = file if file is not None else sys.stdout
    stream.write(sep.join(str(value) for value in values) + end)
    if flush:
        stream.flush()


def atomic_json(path: Path, value: Any) -> None:
    """Write JSON through a fsynced temporary file and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_cli(parser_factory: Any) -> int:
    """Run a workflow CLI command and render failures as one JSON object."""
    args = parser_factory().parse_args()
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError) as error:
        emit(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 2

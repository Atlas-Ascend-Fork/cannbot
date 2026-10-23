# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""torch_npu runtime quirks: warning suppression and interpreter bootstrap."""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from env_registry import TORCH_DEVICE_BACKEND_AUTOLOAD


TORCH_NPU_COLLECT_ENV_MODULE_PATTERN = r"torch_npu\.utils\.collect_env"
TORCH_NPU_OWNER_MISMATCH_MESSAGE_PATTERN = r"Warning: The .* owner does not match the current owner\."


def suppress_torch_npu_owner_mismatch_warning() -> None:
    warnings.filterwarnings(
        "ignore",
        message=TORCH_NPU_OWNER_MISMATCH_MESSAGE_PATTERN,
        category=UserWarning,
        module=TORCH_NPU_COLLECT_ENV_MODULE_PATTERN,
    )


@contextmanager
def temporary_sys_path_entries(*paths: Path) -> Iterator[None]:
    added: list[str] = []
    try:
        for path in paths:
            text = str(path)
            if text not in sys.path:
                sys.path.insert(0, text)
                added.append(text)
        yield
    finally:
        for text in reversed(added):
            if text in sys.path:
                sys.path.remove(text)


def bootstrap_torch_npu(*import_paths: Path) -> None:
    """Import torch and torch_npu before dynamically loaded user code runs.

    On Ascend, if the first torch import happens from inside dynamic module
    execution, torch backend discovery can race with torch_npu initialization
    and later leave Triton with no active NPU driver. torch_npu itself is
    optional; torch is not. When import paths are given, the torch import is
    retried with those paths on sys.path; without them the ImportError
    surfaces immediately, which is the fail-fast behavior runtimes with a
    mandatory torch install want.
    """
    suppress_torch_npu_owner_mismatch_warning()
    loaded_torch = sys.modules.get("torch")
    if loaded_torch is not None and hasattr(loaded_torch, "npu"):
        return
    previous = os.environ.get(TORCH_DEVICE_BACKEND_AUTOLOAD)
    os.environ[TORCH_DEVICE_BACKEND_AUTOLOAD] = "0"
    try:
        try:
            importlib.import_module("torch")
        except ImportError:
            if not import_paths:
                raise
            with temporary_sys_path_entries(*(path.resolve() for path in import_paths)):
                importlib.import_module("torch")
        try:
            importlib.import_module("torch_npu")
        except ImportError:
            pass
    finally:
        if previous is None:
            os.environ.pop(TORCH_DEVICE_BACKEND_AUTOLOAD, None)
        else:
            os.environ[TORCH_DEVICE_BACKEND_AUTOLOAD] = previous

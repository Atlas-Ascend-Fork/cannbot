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
"""Regression for the log parser's standalone output-path CLI contract."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/log_parser.py"


@pytest.mark.parametrize("path_kind", ["filename", "nested", "absolute"])
def test_log_parser_cli_output_paths(tmp_path, path_kind):
    raw = tmp_path / "raw.log"
    raw.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "hello"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = {
        "filename": Path("readable.log"),
        "nested": Path("nested/readable.log"),
        "absolute": tmp_path / "absolute/readable.log",
    }[path_kind]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(raw), str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / output).read_text(encoding="utf-8") == "[回复] hello\n"

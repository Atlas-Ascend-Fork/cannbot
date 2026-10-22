#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Kernel-origin evidence must belong to the exact requested operator."""

import pytest

import check_op_binpath as checker


@pytest.mark.parametrize(
    "line",
    [
        "Op[{op}] bin path is {path}",
        "OpName:[{op}] bin file path[{path}]",
        "Available bin for op {op} is {path}",
    ],
)
@pytest.mark.parametrize("mixed", [False, True])
def test_name_prefix_collision_does_not_count_as_requested_kernel(
    tmp_path, line, mixed
):
    vendor = tmp_path / "vendors" / "AddCustom"
    path = vendor / "kernel.o"
    other = tmp_path / "builtin" / "other.o" if mixed else path
    lines = [line.format(op="AddCustomGrad", path=other)]
    if mixed:
        lines.append(line.format(op="AddCustom", path=path))
    log = tmp_path / "debug.log"
    log.write_text("\n".join(lines))
    args = [str(log), "--optype", "AddCustom", "--expect-dir", str(vendor)]
    assert checker.main(args) == (0 if mixed else 2)
    assert checker.main(args + ["--require"]) == (0 if mixed else 1)


@pytest.mark.parametrize(
    "token, expected",
    [
        ("AddCustom_0", 0),
        ("aclnnAddCustom_0_AddCustomAiCore", 0),
        ("AddCustomGrad_0", 2),
    ],
)
def test_cann_instance_names_preserve_operator_boundary(tmp_path, token, expected):
    vendor = tmp_path / "vendors" / "AddCustom"
    log = tmp_path / "debug.log"
    log.write_text(f"OpName:[{token}] bin file path[{vendor}/kernel.o]\n")
    assert (
        checker.main([str(log), "--optype", "AddCustom", "--expect-dir", str(vendor)])
        == expected
    )

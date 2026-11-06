# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Integer precision metrics must retain the full 64-bit difference."""

import json
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from precision import dual_inspect


@pytest.mark.parametrize(
    "dtype, actual, golden",
    [
        (torch.int64, -(2**63), 0),
        (torch.int64, -(2**63), 2**63 - 1),
        (torch.uint64, 2**64 - 1, 0),
        (torch.int64, 2**53 + 1, 2**53),
        (torch.int64, 2**62 + 12345, -(2**62)),
        (torch.int64, 2**54 + 1, 0),
        (torch.int8, -128, 127),
    ],
)
def test_integer_error_metrics_use_exact_subtraction(dtype, actual, golden):
    a = torch.tensor([actual], dtype=dtype)
    b = torch.tensor([golden], dtype=dtype)
    result = dual_inspect(a, b, b, "integer-output")
    error = actual - golden
    assert not result.passed
    assert result.ans_vs_golden.mismatch_rate == 1
    assert result.ans_vs_golden.ae_max == abs(error)
    assert result.ans_vs_golden.ae_mean == float(abs(error))
    assert result.ans_vs_golden.mean == float(error)
    assert isinstance(result.ans_vs_golden.ae_max, int)
    assert json.loads(json.dumps(result.to_dict()))["ans_vs_golden"]["ae_max"] == abs(
        error
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_integer_metrics_preserve_scalar_broadcast(reverse):
    a = torch.tensor([1, 3], dtype=torch.int64)
    b = torch.tensor(2, dtype=torch.int64)
    if reverse:
        a, b = b, a
    result = dual_inspect(a, b, b, "broadcast-output")
    assert result.ans_vs_golden.ae_mean == 1
    assert result.ans_vs_golden.mean == 0
    assert result.ans_vs_golden.std == pytest.approx(2**0.5)

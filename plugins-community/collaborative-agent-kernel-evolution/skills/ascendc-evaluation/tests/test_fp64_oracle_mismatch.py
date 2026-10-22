# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Precision judgments must retain float64 oracle differences."""

import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from precision import dual_inspect


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
@pytest.mark.parametrize(
    "delta, atol", [(2**-40, 0), (2**-30, 2**-32), (2**-30, 2**-28)]
)
def test_mismatch_judgment_preserves_fp64_oracle(dtype, delta, atol):
    ans = torch.tensor([1.0], dtype=dtype)
    oracle = torch.tensor([1.0 + delta], dtype=torch.float64)
    tol = {"atol": atol, "rtol": 0, "sv_th": 1e-5, "sv_err": 0, "ulp_tol": 2}
    result = dual_inspect(ans, ans, oracle, "oracle-difference", tolerances=tol)
    expected_match = delta <= atol
    assert result.ans_vs_golden.ae_max == delta
    assert result.passed == expected_match
    assert result.ans_vs_golden.mismatch_rate == (0 if expected_match else 1)

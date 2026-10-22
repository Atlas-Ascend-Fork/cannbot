# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""ULP distances must count representable steps across zero."""

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ulp import ulp_distance_bitwise, ulp_metrics


@pytest.mark.parametrize("dtype", [torch.bfloat16, torch.float16, torch.float32])
def test_bitwise_ulp_steps_through_zero(dtype):
    tiny = torch.nextafter(
        torch.tensor(0.0, dtype=dtype), torch.tensor(1.0, dtype=dtype)
    )
    a = torch.stack([-tiny, -tiny, tiny, torch.tensor(-0.0, dtype=dtype)])
    b = torch.stack(
        [
            torch.tensor(0.0, dtype=dtype),
            tiny,
            torch.tensor(0.0, dtype=dtype),
            torch.tensor(0.0, dtype=dtype),
        ]
    )
    np.testing.assert_array_equal(ulp_distance_bitwise(a, b, dtype), [1, 2, 1, 0])
    result = ulp_metrics(a[:2], b[:2], dtype, ulp_tol=2)
    assert result["ulp_max"] == 2
    assert result["ulp_miss_rate"] == 0


@pytest.mark.parametrize("dtype", [torch.bfloat16, torch.float16, torch.float32])
def test_same_sign_neighbor_and_flushed_subnormals(dtype):
    a = torch.tensor([-1.0, 1.0], dtype=dtype)
    b = torch.nextafter(a, torch.zeros_like(a))
    np.testing.assert_array_equal(ulp_distance_bitwise(a, b, dtype), [1, 1])
    tiny = torch.nextafter(
        torch.tensor(0.0, dtype=dtype), torch.tensor(1.0, dtype=dtype)
    )
    np.testing.assert_array_equal(ulp_distance_bitwise(-tiny, tiny, dtype, False), [0])

# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
from easyasc.a5 import *


@kernel()
def matmul_float_mmad_kernel(x: GMTensor, y: GMTensor, z: GMTensor, M: Var, N: Var, K: Var):
    l1x = Tensor(DT.float, [M, K], Position.L1)
    l1y = Tensor(DT.float, [N, K], Position.L1)
    l0c = Tensor(DT.float, [M, N], Position.L0C)
    with auto_sync():
        l1x <<= x[:, :]
        l1y <<= y[:, :]
        matmul(l0c, l1x, l1y, m=M, n=N, k=K, is_init=True)
        z[:, :] <<= l0c
    return z


def main():
    import torch

    # Keep dimensions aligned for direct NZ views in this minimal sample.
    M = 32
    N = 48
    K = 16

    torch.manual_seed(0)
    x = torch.randn((M, K), dtype=torch.float32)
    y = torch.randn((N, K), dtype=torch.float32)
    z = torch.zeros((M, N), dtype=torch.float32)

    z_kernel = OpExec(matmul_float_mmad_kernel, simulator=True)(x, y, z, M, N, K)
    z_ref = x @ y.t()
    torch.testing.assert_close(z_kernel, z_ref, rtol=1e-5, atol=1e-5)
    print(f"max_abs_diff={torch.abs(z_kernel - z_ref).max().item():.6e}")

if __name__ == "__main__":
    main()

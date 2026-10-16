# Write Your First Kernel

This walkthrough builds the same mental model used by the smallest kernel examples in `agent/example/kernels/`.

## 1. Start from the exact reference

Always write the golden formula first:

```python
z_ref = x @ y.t()
```

That reference is not optional. It decides:

- operand layout
- accumulation dtype
- output dtype
- whether you need transpose views

For a first kernel, keep the formula simple and use float inputs and outputs.

## 2. Declare the kernel signature

Kernel inputs and outputs are `GMTensor` arguments. Scalar dimensions are `Var` arguments.

```python
@kernel()
def matmul_float_mmad_kernel(x: GMTensor, y: GMTensor, z: GMTensor, M: Var, N: Var, K: Var):
    ...
```

Important rule:

- the kernel signature is the contract of the generated operator
- every user-visible input and output must be represented by `GMTensor` parameters

## 3. Allocate on-chip tensors

For a minimal matmul, you need:

```python
l1x = Tensor(DT.float, [M, K], Position.L1)
l1y = Tensor(DT.float, [N, K], Position.L1)
l0c = Tensor(DT.float, [M, N], Position.L0C)
```

These lines do not allocate Python arrays. They emit DSL-side tensor declarations into the active kernel.

## 4. Describe the data movement

Move the global-memory tensors into L1:

```python
l1x <<= x[:, :]
l1y <<= y[:, :]
```

Then invoke the matmul shortcut:

```python
matmul(l0c, l1x, l1y, m=M, n=N, k=K, is_init=True)
```

Finally write the result back:

```python
z[:, :] <<= l0c
return z
```

The full kernel is:

```python
from easyasc.a5 import *


@kernel()
def matmul_float_mmad_kernel(x: GMTensor, y: GMTensor, z: GMTensor, M: Var, N: Var, K: Var):
    l1x = Tensor(DT.float, [M, K], Position.L1)
    l1y = Tensor(DT.float, [N, K], Position.L1)
    l0c = Tensor(DT.float, [M, N], Position.L0C)

    l1x <<= x[:, :]
    l1y <<= y[:, :]
    matmul(l0c, l1x, l1y, m=M, n=N, k=K, is_init=True)
    z[:, :] <<= l0c
    return z
```

## 5. Execute through `OpExec`

Use PyTorch tensors as runtime inputs:

```python
import torch

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
```

The placeholder output tensor `z` is still required by the current kernel contract, even in simulator mode.

## 6. What `OpExec` is doing for you

At a high level, the call:

```python
OpExec(matmul_float_mmad_kernel, simulator=True)(x, y, z, M, N, K)
```

does the following:

1. checks the tensor/scalar argument ordering
2. converts input tensors into `GMTensor` objects
3. binds scalar values as `Var`
4. runs the kernel body to emit instructions
5. executes those instructions in the simulator
6. maps output `GMTensor` objects back into PyTorch tensors

## 7. Evolve from the first kernel

Once the baseline works, the next useful steps are:

1. add tiling with `DBuff`
2. add a vec-side postprocess in UB
3. introduce `auto_sync()` around the pipelined region
4. add explicit mutexes when ownership crosses from cube to vec or vec to cube

Good next files to study:

- `agent/example/kernels/a5/basic_cube_vec_mix.py`
- `agent/example/kernels/a5/matmul_half_splitn_bias10p2_vf.py`
- `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul.py`

## 8. Common first mistakes

- using a vec op on a non-UB tensor
- forgetting that kernel parameters must be `GMTensor` or `Var`
- changing the kernel body before confirming the PyTorch reference
- skipping `shape_bindings` when repeated scalar values make dimension inference ambiguous

## 9. A practical progression path

If you are new to this repository, this sequence works well:

1. `agent/example/kernels/a5/matmul_float_mmad.py`
2. `agent/example/kernels/a5/basic_cube_vec_mix.py`
3. `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul.py`
4. `agent/example/kernels/a5/vec_cube_vec_scale2_abs_add1_matmul.py`

Each step adds only one major idea on top of the previous one.

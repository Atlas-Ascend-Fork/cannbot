# Quick Start

This guide is for readers who want to run an existing kernel first and understand the rest of the framework second.

## 1. Environment

This repository is not currently packaged as an installable Python project. The common workflow is to work directly from the repo root.

Example environment (not required):

```bash
# example only — adjust to your local setup
conda activate torch210npu
```

If that environment is not available on your machine, use the default Python environment that already has the required dependencies. Before reading archived runtime/docs or running examples, run `bash agent/scripts/init.sh` to restore the archived trees.

Minimum expectations from the current source tree:

- Python type hints stay compatible with Python 3.8
- `torch` must be importable for `OpExec`
- the repository root should be your working directory when running examples

## 2. First successful run

Run the smallest matmul example:

```bash
python agent/example/kernels/a5/matmul_float_mmad.py
```

What this file does:

1. imports the public API from `easyasc.a5`
2. defines a `@kernel`
3. constructs sample PyTorch tensors
4. launches the kernel through `OpExec(..., simulator=True)`
5. compares the kernel output with `x @ y.t()`

If the run succeeds, you have verified that:

- the Python DSL can build the kernel
- the simulator can execute it
- output tensors can be read back into PyTorch

## 3. Minimal kernel anatomy

The shortest example in the repository is `agent/example/kernels/a5/matmul_float_mmad.py`:

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

Read this as a dataflow description:

- `x` and `y` live in global memory
- `l1x` and `l1y` are on-chip L1 tensors
- `l0c` holds the float accumulation tile
- `<<=` emits the data-move or writeback instruction for the source and destination pair

## 4. `OpExec` in one minute

`OpExec` is the main execution entry point:

```python
z_kernel = OpExec(matmul_float_mmad_kernel, simulator=True)(x, y, z, M, N, K)
```

Important rules:

- all `torch.Tensor` arguments must come before scalar arguments
- scalar arguments are converted into `Var` objects internally
- when `simulator=True`, input tensors are cloned into simulator-visible `GMTensor.data`
- returned `GMTensor` outputs are converted back into PyTorch tensors

## 5. Simulator mode vs generation mode

Use simulator mode first:

```python
OpExec(kernel_fn, simulator=True)(...)
```

Use generation mode when you want emitted artifacts:

```python
OpExec(kernel_fn, out_dir="my_kernel", simulator=False, gen_only=True)(...)
```

High-level difference:

- simulator mode executes the kernel through the V2 runtime under `easyasc/simulator_v2/`
- generation mode emits C++ and wrapper artifacts through the parser and template path

## 6. When you need `shape_bindings`

The runtime tries to infer which scalar `Var` belongs to each tensor dimension. This becomes ambiguous when multiple scalar arguments have the same integer value.

Example:

```python
out = OpExec(kernel_fn, simulator=True)(
    x,
    y,
    z,
    m,
    n,
    k,
    shape_bindings={
        0: [0, 2],
        1: [1, 2],
        2: [0, 1],
    },
)
```

Each key is the tensor argument index. Each list maps tensor dimensions to scalar argument indices or `None`.

If you see an error like:

```text
Ambiguous scalar match for tensor #... dim #...
```

add explicit `shape_bindings` before changing the kernel body.

## 7. What to read next

- [Programming Model](02_programming_model.md)
- [Write Your First Kernel](03_write_your_first_kernel.md)
- [Simulator and Trace](05_simulator_and_trace.md)

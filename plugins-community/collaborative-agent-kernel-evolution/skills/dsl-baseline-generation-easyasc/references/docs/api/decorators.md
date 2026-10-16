# Decorators

This page documents the public decorators shared across the `easyasc` authoring surface.

These decorators define the main authoring contexts used by the framework:

- kernel entry points
- reusable helper functions
- auto-sync-marked regions
- reusable micro modules

## 1. `kernel()`

- Purpose: Wrap a Python function as a kernel entry point and return a `KernelBase`-backed callable.
- Parameters:
  - no required decorator arguments in normal use; the usual form is `@kernel()`
- Restrictions:
  - the decorated function must be callable
  - when the kernel is invoked through the framework, its bound arguments must resolve to `GMTensor` and `Var`
  - kernel code should be written inside the decorated function body, not outside it
- Example:

```python
from easyasc.a5 import *


@kernel()
def copy_kernel(x: GMTensor, y: GMTensor, M: Var, N: Var):
    ub = Tensor(DT.float, [M, N], Position.UB)
    ub <<= x[:, :]
    y[:, :] <<= ub
    return y
```

## 2. `func()`

- Purpose: Apply the same Python-to-DSL transformation as `@kernel`, but keep the function as a helper instead of a kernel entry point.
- Parameters:
  - no required decorator arguments in normal use; the usual form is `@func()`
- Restrictions:
  - use it for reusable instruction-emitting helpers inside an active kernel or micro context
  - it does not create a kernel wrapper and cannot be executed as a standalone kernel
- Example:

```python
@func()
def zero_l1(buf: Tensor):
    set_constant_to_l1(buf, 0.0)
```

## 3. `auto_sync()`

- Purpose: Mark a region or helper call so the parser can later insert supported same-side synchronization events.
- Parameters:
  - no required decorator arguments in normal use; the usual forms are `@auto_sync()` and `with auto_sync():`
- Restrictions:
  - only valid inside kernel code
  - does not solve cube-to-vec or vec-to-cube ownership by itself
  - only the hard-coded pipe pairs in `asc_autosync.py` are handled
- Example:

```python
with auto_sync():
    l1x <<= x[:, :]
    matmul(l0c, l1x, l1y)
```

## 4. `vf()`

- Purpose: Wrap a function as a reusable micro module.
- Parameters:
  - no decorator arguments; the form is `@vf()`
- Restrictions:
  - only available from `easyasc.a5`
  - micro functions only accept UB `Tensor` inputs and `Var`-like scalar inputs
  - micro code uses `Reg`, `RegList`, and `MaskReg`, not cube-side `Tensor` math
- Example:

```python
@vf()
def add_one(src: Tensor, dst: Tensor):
    r = Reg(DT.float)
    r <<= src[0]
    r <<= r + 1.0
    dst[0] <<= r
```

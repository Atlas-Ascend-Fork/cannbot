# Troubleshooting

This page focuses on the failure modes you are most likely to hit while authoring or running kernels in this repository.

## 1. `Invalid argument order: torch.Tensor must come before int/float`

Cause:

- `OpExec.__call__` expects all tensor arguments first and scalar arguments after them

Fix:

- pass runtime tensors first
- move `M`, `N`, `K`, and other scalars to the end of the argument list

## 2. `Ambiguous scalar match for tensor #... dim #...`

Cause:

- two or more scalar arguments share the same runtime value
- `OpExec` cannot infer which scalar should bind to the tensor dimension

Fix:

- add explicit `shape_bindings`

Example:

```python
shape_bindings={
    0: [0, 2],
    1: [1, 2],
    2: [0, 1],
}
```

## 3. `shape_bindings[...] mismatches tensor dim value`

Cause:

- an explicit `shape_bindings` entry points at a scalar whose value does not equal the real tensor dimension

Fix:

- verify each tensor dimension against the scalar index you selected

## 4. `trace is only supported when simulator=True`

Cause:

- `trace=...` was passed while generation mode was selected

Fix:

- enable tracing only with `simulator=True`

## 5. `VecOP only supports UB position`

Cause:

- a vec operation was applied to a tensor outside `UB`

Fix:

- move the data into a UB tensor before the vec stage

## 6. `MicroModule only accepts Tensor inputs in UB`

Cause:

- a `@vf` function was called with a tensor from `L1`, `L0C`, or global memory

Fix:

- call micro helpers only with UB tensors and scalar inputs

## 7. `GMTensor has not bound a mutex yet`

Cause:

- `lock()`, `ready()`, `wait()`, or `free()` was called on a `GMTensor` without first attaching a mutex

Fix:

- call `bind_cv_mutex(...)` or `bind_vc_mutex(...)` first
- or use an explicit `CvMutex` / `VcMutex` object directly

## 8. The kernel runs but the math is wrong

Checklist:

1. confirm the exact PyTorch formula
2. confirm cast order
3. confirm operand layout and transpose placement
4. reduce the shape and rerun in simulator mode
5. inspect tail writeback logic
6. if synchronization is involved, add a simulator trace

In this repository, wrong math is often caused by:

- a misplaced cast
- the wrong `y` layout for `x @ y.t()`
- tail slices written with the wrong subblock bounds
- a cross-side handoff that relied on `auto_sync()` alone

## 9. The kernel deadlocks or appears stuck

Most likely causes:

- producer/consumer ordering is incomplete
- a mutex lifecycle is unbalanced
- an event or wait path is attached to the wrong side

What to do:

1. shrink the shape
2. isolate one tile
3. use simulator trace output
4. compare your flow with a smaller existing kernel that uses the same topology

## 10. Generation mode fails but simulator mode works

This usually means the issue is in one of these layers:

- parser lowering
- generated artifact assumptions
- local build or runtime scripts
- environment-specific toolchain setup

Do not skip the simulator stage when investigating. First prove the kernel logic is correct there, then inspect generation-specific behavior.

## 11. Useful comparison files

When you are stuck, compare against:

- `agent/example/kernels/a5/matmul_float_mmad.py` for the shortest baseline
- `agent/example/kernels/a5/basic_cube_vec_mix.py` for cube -> vec
- `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul.py` for vec -> cube
- `testcases/simulator/trace/test_trace.py` for simulator tracing
- `testcases/simulator/opexec/test_torchplugin_shape_bindings.py` for shape-binding failures

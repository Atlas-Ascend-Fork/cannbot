# OpExec options

`OpExec` is the runtime entry. Constructor signature (from `easyasc/torchplugin.py:413`):

```python
OpExec(
    op_func,                  # @kernel-decorated callable (KernelBase)
    out_dir="",               # base name for codegen output dir; defaults to kernel name
    cann_path=None,           # CANN install root; falls back to ASCEND_HOME_PATH env
    custom_op_path=None,      # extra custom-OPP root; defaults to "./"
    profile=False,            # enable profiling-leaning runtime behavior (gen mode)
    gen_only=False,           # emit code only; do NOT run b.sh / r.sh
    simulator=False,          # True = V2 simulator path; False = codegen path
    skip_compile=False,       # gen mode: skip b.sh
    trace=None,               # simulator mode: dump trace to file path
    debug=False,
)
```

Then call:

```python
out = OpExec(kernel, ...)(*tensor_args, *scalar_args, shape_bindings=None)
```

## Two paths

| Flag | Path |
|------|------|
| `simulator=True` | V2 simulator runs in-process. No code generation. Returns torch.Tensor outputs. |
| `simulator=False` (default) | Code generation. Writes `<out_dir>/op_host/`, `<out_dir>/op_kernel/`, `<out_dir>_aclnn_test/`, and `b.sh`/`r.sh` in the current working directory. By default also runs them. |

## Argument order

All `GMTensor`-typed kernel parameters (inputs + outputs) must precede all `Var`-typed parameters. Mixing fails at OpExec validation time.

## Common option combinations

```python
# Smoke: software simulation, fast iteration, no toolchain needed
OpExec(kernel, simulator=True)(*inputs)

# Inspect generated code only (no compile, no run)
OpExec(kernel, out_dir="my_op", simulator=False, gen_only=True)(*inputs)

# Full codegen + build + run
OpExec(kernel, out_dir="my_op", simulator=False)(*inputs)

# Codegen + build, but don't run
OpExec(kernel, out_dir="my_op", simulator=False, skip_compile=False)(*inputs)
# (no skip_compile=False shortcut for "build only" — easyasc always runs r.sh after b.sh
#  in non-gen-only mode; if you don't want execution, use gen_only=True and run b.sh by hand)

# Profiling-flavored build
OpExec(kernel, out_dir="my_op", simulator=False, profile=True)(*inputs)

# Trace simulator pipe events
OpExec(kernel, simulator=True, trace="trace.txt")(*inputs)
```

## `shape_bindings`

Pass to `__call__`, not the constructor:

```python
OpExec(kernel, simulator=True)(
    x, y, z, m, n, k,
    shape_bindings={
        0: [0, 2],      # tensor index 0: dim 0 ↔ scalar 0, dim 1 ↔ scalar 2
        1: [1, 2],
        2: [0, 1],
    },
)
```

Required when two scalar args carry the same int value at runtime and OpExec can't infer which scalar a tensor dim is bound to. Symptom: `Ambiguous scalar match for tensor #... dim #...`.

## Output handling

- `simulator=True` → tensor data is read back from `GMTensor.data` and converted to torch.Tensor; the returned value matches the kernel's `return` (single tensor or tuple).
- `simulator=False` (default `gen_only=False`) → after r.sh, output binaries are read back into torch.Tensors.
- `simulator=False, gen_only=True` → no run, no readback. Caller invokes b.sh/r.sh manually if desired.

## Exit / artifact cheat-sheet (codegen mode)

| Want | Set |
|------|-----|
| run end-to-end, get tensors back | default (`simulator=False`) |
| inspect source only | `simulator=False, gen_only=True` |
| build but don't run | not supported via flag — use `gen_only=True` then `bash b.sh` |
| run without rebuilding | `simulator=False, skip_compile=True` |

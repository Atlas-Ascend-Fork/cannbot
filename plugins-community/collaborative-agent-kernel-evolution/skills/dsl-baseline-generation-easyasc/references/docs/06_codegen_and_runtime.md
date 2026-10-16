# Code Generation and Runtime

This document explains what happens after a kernel has emitted instruction IR.

## 1. The execution split

The current framework supports two major execution paths through `OpExec`:

- simulator path
- generation path

Both paths start the same way:

1. bind `torch.Tensor` and scalar inputs
2. convert them into `GMTensor` and `Var` objects
3. execute the Python kernel body to emit instructions

After that, the paths diverge.

## 2. Simulator path

When `simulator=True`:

- `GMTensor.data` is populated from the input tensors
- the kernel runs through `KernelBase.run_sim()`, which currently dispatches to `_run_sim_v2()`
- the kernel first builds a V2 `KernelProgram`, then executes it through `easyasc/simulator_v2/`
- outputs are read back from `GMTensor.data`
- `OpExec` does not call `generate()` on this path, so simulator runs do not emit code artifacts even if `out_dir` or `gen_only=True` is provided

This path is the recommended default while authoring new kernels.

## 3. Generation path

When `simulator=False`, `OpExec` uses the generation flow:

- input binaries are written under `<base>_aclnn_test/input`
- parser lowering emits code artifacts
- optional build and run scripts are invoked
- output binaries are loaded back into PyTorch tensors unless `gen_only=True`
- if you only want to validate or inspect emitted code, use `simulator=False, gen_only=True`

The base directory is either:

- `out_dir`, if provided
- otherwise the kernel name

## 4. What `KernelBase` contributes

`KernelBase` is the wrapper created by `@kernel`.

Its responsibilities include:

- storing emitted instructions
- tracking used micro modules
- collecting output `GMTensor` objects
- inserting cross-side ready/wait scaffolding for registered mutexes
- dumping generated cube and vec code

It also auto-inserts some framework-owned instructions before the user body begins.

For simulator work specifically, `KernelBase` also owns:

- automatic V2 bridge selection via `build_simulator_v2_program()`
- optional custom program/config hooks through `_simulator_v2_program_builder` and `_simulator_v2_config_builder`

## 5. How the parser lowers code

The parser pipeline does three high-level things:

1. split the instruction stream into cube-side and vec-side streams
2. insert autosync events for supported same-side pipe pairs
3. translate each side into generated code with op-specific handlers

Key modules:

- `easyasc/parser/asc.py`
- `easyasc/parser/asc_autosync.py`
- `easyasc/parser/asc_pruning.py`
- `easyasc/parser/asc_handlers/`

## 6. Generated artifacts

`KernelBase.dump_kernel()` writes:

- `<path>_cube.h`
- `<path>_vec.h`
- `<path>.cpp`

The generated C++ wrapper:

- includes tensor and helper headers
- includes generated micro headers when needed
- dispatches to cube and vec entry functions
- reads scalar tiling values from generated runtime data

## 7. Build and run script hooks

When generation mode is not `gen_only`, `OpExec` can run:

- `b.sh` for build
- `r.sh` for runtime execution

Their logs are written to files such as:

- `b.sh.log`
- `r.sh.log`

This is why generation mode assumes you are working from the repository root and already have the relevant local toolchain setup.

## 8. `shape_bindings`

`shape_bindings` belongs to `OpExec.__call__`, not to the kernel itself.

Use it when:

- two or more scalar arguments share the same runtime integer value
- the runtime cannot infer which scalar belongs to which tensor dimension

If a binding is explicit, the runtime checks that the chosen scalar value really matches the tensor dimension and raises an error when it does not.

## 9. Useful `OpExec` options

- `out_dir`: output directory prefix
- `profile`: request profiling-oriented behavior in generation mode
- `gen_only`: emit artifacts but do not run the generated path
- `simulator`: use the simulator instead of generation mode
- `skip_compile`: skip `b.sh` in generation mode
- `trace`: emit a simulator trace to a file

`gen_only` only affects generation mode. It does not force code emission when `simulator=True`.

## 10. Recommended order of use

For new kernel work:

1. `simulator=True`
2. `simulator=True, trace=...` if synchronization needs inspection
3. `simulator=False, gen_only=True`
4. full generation and runtime flow

That progression aligns with the implementation and minimizes the number of moving parts you debug at once.

# Programming Model

This document explains the framework's authoring model rather than the hardware model.

## 1. Public entry surfaces

The repository exposes two main user-facing import surfaces.

### `easyasc.a5`

Use `a5` for most new kernels. It exports:

- decorators: `@kernel`, `@func`, `@auto_sync`, `@vf`
- tensor types: `GMTensor`, `Tensor`, `DBuff`, `TBuff`
- scalar and register types: `Var`, `Reg`, `RegList`, `MaskReg`
- cube, vec, and micro stub helpers
- execution entry point: `OpExec`
- high-level shortcut helpers such as `matmul`

### `easyasc.a2`

`a2` is the public DSL surface for the A2-style architecture and instruction sequences. It should not be read as a smaller compatibility layer of `a5`; instead, `a2` and `a5` are parallel architecture-specific entry surfaces that target different instruction families. `a2` still exposes `@kernel`, `GMTensor`, `Tensor`, `DBuff`, `Var`, `OpExec`, and the A2-side cube/vec operations.

## 2. Authoring layers

The framework is easiest to understand as five layers.

1. Python authoring layer
   - you write functions with decorators and DSL objects
2. Instruction IR layer
   - object creation, moves, math ops, loops, and synchronization emit `Instruction` objects
3. Split and lowering layer
   - the parser classifies IR into cube-side and vec-side streams
4. Execution layer
   - either the simulator runs the streams or the generator emits code
5. Validation layer
   - outputs are compared against a PyTorch reference

## 3. Core data objects

### `GMTensor`

`GMTensor` represents a kernel parameter in global memory. Kernel inputs and outputs must be declared as `GMTensor` parameters in the `@kernel` function signature.

Typical uses:

- kernel input tensors
- kernel output tensors
- synchronization anchor through `bind_cv_mutex()` or `bind_vc_mutex()`

### `Tensor`

`Tensor` represents an on-chip tensor. It always has:

- a data type
- a 2D shape
- a memory position such as `L1`, `L0A`, `L0B`, `L0C`, or `UB`

The destination and source positions determine which instruction is emitted by `<<=`.

Examples:

- `l1 <<= gm[:, :]` emits a GM-to-L1 move
- `ub <<= l0c` emits an `l0c_to_ub` path
- `l1 <<= ub` emits a UB-to-L1 path

### `DBuff` and `TBuff`

These are buffered tensor helpers that carry slot identity and are commonly used for pipelined or double-buffered code. Their slot lineage matters to the synchronization logic.

### `Var`

`Var` represents scalar values such as:

- tensor dimensions
- loop indices
- symbolic shape values
- counters

When you pass Python integers or floats to `OpExec`, they are wrapped into `Var` objects internally.

### `Reg`, `RegList`, `MaskReg`

These are register-level objects mainly used in `a5` micro and vector code:

- `Reg`: scalar or vector-width register abstraction
- `RegList`: fixed-length register groups for row-wise vector work
- `MaskReg`: micro-side mask register abstraction

## 4. Decorators

### `@kernel`

Wraps a Python function in `KernelBase`. At call time it:

- binds argument names
- emits `create_gm_tensor` instructions for `GMTensor` parameters
- creates internal helper buffers such as `_l0a` and `_l0b`
- records the final output `GMTensor` set

### `@vf`

Builds a `MicroModule`. A `@vf` function can only consume `Tensor` inputs in `UB` and `Var`-like scalar inputs. When called from a kernel, it emits a `call_micro` instruction and contributes generated code to the final output.

### `@func`

Applies the same Python-to-DSL source transformation as `@kernel`, but it does not create a kernel wrapper. Use it for helper routines that should emit instructions inside the current kernel or micro context.

### `@auto_sync` and `with auto_sync():`

These do not perform synchronization immediately. They emit `start_auto_sync` and `end_auto_sync` markers. The parser later rewrites marked regions into event-based handshakes for supported same-side pipe pairs.

## 5. Python syntax that gets rewritten

The framework rewrites certain Python constructs before execution.

Important examples:

- assignments to `Var`, `Tensor`, `DBuff`, `TBuff`, `Reg`, `RegList`, and related constructors gain generated names when possible
- Python `and`, `or`, and `not` inside transformed functions are rewritten into bitwise forms
- Python `if / elif / else` is rewritten into `with If(...):`, `with Elif(...):`, and `with Else():`
- native Python `break` / `continue` inside DSL `range(...)` loops are rewritten into `break_()` / `continue_()`

This is why the repository prefers writing kernel control flow inside decorated functions rather than building instructions manually.

For control-flow conditions that emit DSL instructions while being evaluated, such as `GetSubBlockIdx() == 0`, native Python syntax is still supported:

- `elif GetSubBlockIdx() == 0:`
- `else: if GetSubBlockIdx() == 0:`

The framework delays `elif` condition evaluation until after the previous branch has closed, so these patterns do not need a manual `with Else(): with If(...):` workaround.

## 6. Loop model

The custom `range` from `easyasc.flowcontrol` is not the built-in `range`. It emits loop instructions into the active kernel or micro context.

Example:

```python
for m in range(m_begin, m_end, BLK):
    ...
```

This emits `start_loop` and `end_loop` instructions instead of executing a normal Python loop over concrete integers.

`unroll(...)` is the plain built-in range and is meant for authoring-time expansion.

Native Python `break` / `continue` are supported inside transformed DSL `range(...)` loops and are rewritten into `break_loop` / `continue_loop` instructions. They are not allowed inside `unroll(...)` loops.

## 7. Memory positions

The main positions exposed to authors are:

- `Position.L1`
- `Position.L0A`
- `Position.L0B`
- `Position.L0C`
- `Position.UB`

The framework uses these positions to validate legal moves and to decide which backend stub function to emit.

Examples:

- vec ops are UB-only
- `Tensor.T` is only allowed for L1 tensors
- micro modules only accept UB tensors

## 8. Pipes and sides

The current implementation distinguishes cube-side and vec-side execution.

Conceptually:

- cube-side pipe families include `MTE2`, `MTE1`, `M`, and `FIX`
- vec-side pipe families include `MTE2`, `V`, and `MTE3`

This split matters because:

- the parser generates separate cube and vec code
- `auto_sync()` only inserts same-side handshakes for hard-coded pipe pairs
- cross-side ownership still requires explicit mutexes

## 9. Shape inference model

`OpExec` constructs `GMTensor` shapes from:

- the real PyTorch tensor shapes
- the scalar argument list
- optional `shape_bindings`

If multiple scalar arguments have the same value, inference can become ambiguous. The runtime intentionally fails fast instead of guessing.

## 10. Recommended mental model

When writing kernels in this repository, think in this order:

1. exact mathematical contract
2. memory layout
3. pipeline topology
4. tile ownership
5. synchronization boundaries
6. tail-safe writeback
7. validation against PyTorch

That order matches how the current codebase is structured and how most sample kernels are written.

# Detailed API Reference

This directory contains the detailed API reference for the public `easyasc` authoring surface.

Scope of this reference:

- symbols exported from `easyasc.a2`
- symbols exported from `easyasc.a5`
- the main public helper classes that those two modules expect users to work with

Out of scope:

- internal helpers whose names start with `_`
- parser-only, simulator-only, or codegen-only internals that are not part of the authoring surface

## Read This First

The same function name can mean different things in `a2` and `a5`.

Examples:

- `easyasc.a2.add`: UB vector add on `Tensor`
- `easyasc.a5.add`: micro register add on `Reg`
- `easyasc.a2.abs`: UB vector unary op
- `easyasc.a5.abs`: micro register unary op
- `easyasc.a2.compare`: vector compare that writes to a UB mask tensor
- `easyasc.a5.compare`: micro compare that writes to `MaskReg`

When reading the pages below, always keep the import surface in mind.

## File Map

- [Decorators](decorators.md)
  - `kernel`, `func`, `auto_sync`, and `vf`
- [Flow Control](flow_control.md)
  - `range`, `unroll`, `break_`, `continue_`, `If`, `Elif`, and `Else`
  - native Python `if/elif/else` and `break`/`continue` rewrite notes
- [OpExec](op_exec.md)
  - `OpExec`
- [Shortcuts](shortcuts.md)
  - `matmul`
  - `maximum` and `minimum`
- [Shared Scalar Helper Functions](scalars.md)
  - worker-query helpers such as `GetCubeIdx` and `GetVecNum`
  - arithmetic/alignment helpers such as `CeilDiv`, `Align128`, `Min`, and `Max`
- [Datatypes](datatype.md)
  - `DT`, `Datatype`, and `DataTypeValue`
  - predefined dtype members, `.size`, `.C0`, and singleton usage rules
- [Positions](position.md)
  - `Position` and `PositionType`
  - local-memory domains, `.cpp` mappings, and singleton usage rules
- [Pipes](pipe.md)
  - `Pipe` and `PipeType`
  - local execution pipes, `S` / `ALL`, and synchronization usage rules
- [Var](var.md)
  - `Var`
  - scalar arithmetic, comparison `Expr`, and scalar IO helpers
- [Tensor and Buffer Types](tensor_buffer.md)
  - `Tensor`, `GMTensor`, `DBuff`, and `TBuff`
  - view semantics, assignment dispatch, slicing, and slot-buffer behavior
- [Register and Mask Types](register.md)
  - `Reg`, `RegList`, `MaskReg`
  - `MaskType` and `MaskTypeValue`
  - builder methods, proxy semantics, and mask attachment
- [Synchronization](synchronize.md)
  - `CvMutex`, `VcMutex`, raw cross-side/all-core sync ops, `setflag` / `waitflag`, `SEvent`, and `DEvent`
  - cross-side token flow, collective waits, local flag behavior, and local event behavior
- [Barriers](barrier.md)
  - `barrier(pipe)` and `bar_*` helpers
  - single-pipe ordering vs `Pipe.ALL` drain behavior
- [Atomic Context Managers](atomic.md)
  - `atomic_add`, `atomic_max`, and `atomic_min`
  - atomic writeback scope mechanics and supported GM-store paths
- [Miscellaneous Helpers](helpers.md)
  - `sim_print`, `dump_tensor`, `inline`, and `clean_dcache`
  - simulator-only debugging helpers, a backend escape hatch, and cache-maintenance helper
- [Cube Data Movement and Compute](cube.md)
  - cube data movement, packed-layout conversion, and `mmad`
  - `DualMode` / `DualModeType` and `l0c_to_ub` routing
- [A2 Vector Math](a2_vec_math.md)
  - binary, unary, scalar, duplication, and group vector operators
- [A2 and Shared Vec Data Movement](vec_data_movement.md)
  - GM/UB/L1 transfer helpers
  - `gm_to_ub_pad`, `ub_to_gm_pad`, `ub_to_ub`
  - `ub_to_l1_nd2nz`, `ub_to_l1_nz`
- [A2 Vec Control and Access Helpers](a2_vec_control.md)
  - vec cast, compare, select, gather/scatter, and vec masks
- [A2 Vec Sort and Merge Helpers](vec_sort.md)
  - `sort32`
  - `mergesort4`
  - `mergesort_2seq`
- [A5 Micro Math](a5_micro_math.md)
  - register-level math, compare/select, and reduction-style micro helpers
- [A5 Micro Data Movement](a5_micro_data_movement.md)
  - UB/register transfer helpers
  - gather/scatter helpers
  - interleave helpers
- [A5 Micro Cast](a5_micro_cast.md)
  - `CastConfig` and `RegLayout`
  - `RoundMode` and `RoundModeType`
  - micro `cast()` and `Reg.astype()`
  - `pack4()` in fp8/int8 cast pipelines
- [A5 Micro Compare and Select](a5_micro_compare_select.md)
  - `compare` and `select`
  - compare modes, execution masks, and alias-safe select semantics
- [A5 Micro Mask Operations](a5_micro_mask_operations.md)
  - mask boolean ops, routing, pack/unpack, and `update_mask`

## Recommended Reading Order

If you are new to the framework:

1. read [decorators.md](decorators.md)
2. read [flow_control.md](flow_control.md)
3. read [op_exec.md](op_exec.md)
4. read [shortcuts.md](shortcuts.md)
5. read [scalars.md](scalars.md)
6. read [datatype.md](datatype.md)
7. read [position.md](position.md)
8. read [pipe.md](pipe.md)
9. read [var.md](var.md)
10. read [tensor_buffer.md](tensor_buffer.md)
11. read [register.md](register.md)
12. read [synchronize.md](synchronize.md)
13. read [barrier.md](barrier.md)
14. read [atomic.md](atomic.md)
15. read [helpers.md](helpers.md)
16. choose either:
   - `a2` path: [a2_vec_math.md](a2_vec_math.md), [vec_data_movement.md](vec_data_movement.md), [a2_vec_control.md](a2_vec_control.md), and [vec_sort.md](vec_sort.md)
   - `a5` path: [a5_micro_math.md](a5_micro_math.md), [a5_micro_data_movement.md](a5_micro_data_movement.md), [a5_micro_cast.md](a5_micro_cast.md), [a5_micro_compare_select.md](a5_micro_compare_select.md), and [a5_micro_mask_operations.md](a5_micro_mask_operations.md)
17. return to [cube.md](cube.md) when your kernel starts crossing cube memory domains or needs exact packed-layout behavior

## Import Surface Summary

### `easyasc.a2`

Use `a2` when you want:

- kernel authoring against the A2-style architecture and instruction sequences
- direct vec function calls such as `add`, `abs`, `gather`, and `compare`
- the A2-specific public DSL surface, which is parallel to `a5` rather than a compatibility subset of it

### `easyasc.a5`

Use `a5` when you want:

- everything from the main kernel authoring path
- `@vf` micro helpers
- `Reg`, `RegList`, `MaskReg`, and `CastConfig`
- micro-level register and mask operations
- `ub_to_l1_nd2nz` / `ub_to_l1_nz`

## Conventions Used In This Reference

- `UB`, `L1`, `L0A`, `L0B`, and `L0C` refer to `Position` values.
- "Inference" means the function computes a missing parameter from the current tensor shape or slice metadata.
- "Context restriction" means the function only works inside a `@kernel`, `@vf`, or other active DSL context.

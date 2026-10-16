# Atomic Context Managers

This page documents the atomic writeback context managers shared by `easyasc.a2` and `easyasc.a5`.

These APIs live in `easyasc/stub_functions/atomic.py`.

## 1. Overview

Atomic helpers are context managers, not ordinary one-shot functions.

Typical use:

```python
with atomic_add():
    out[:, :] <<= ub
```

What this means conceptually:

- enter the block: turn on one atomic writeback mode
- emit supported GM writeback instructions inside the block
- leave the block: turn atomic mode back off

Important mental model:

- the context manager does not make every enclosed instruction atomic
- it changes the writeback mode seen by later supported GM-store instructions

In the current implementation, the main supported atomic consumers are:

- `l0c_to_gm_nz2nd`
- `ub_to_gm_pad`

So atomic context managers are really "atomic GM writeback mode scopes".

## 2. Supported APIs

### `atomic_add(cond=None, dtype=DT.float)`

- Purpose: enable atomic add writeback inside the enclosed region.
- Parameters:
  - `cond`: optional conditional mode placeholder
  - `dtype`: atomic dtype
- Current restrictions:
  - only valid in kernel context
  - `cond` is not implemented
  - only `DT.float` is supported

Example:

```python
with atomic_add():
    out[:, :] <<= ub
```

### `atomic_max(dtype=DT.float)`

- Purpose: enable atomic max writeback inside the enclosed region.
- Parameters:
  - `dtype`: atomic dtype
- Current restrictions:
  - only valid in kernel context
  - only `DT.float` is supported

Example:

```python
with atomic_max():
    out[:, :] <<= ub
```

### `atomic_min(dtype=DT.float)`

- Purpose: enable atomic min writeback inside the enclosed region.
- Parameters:
  - `dtype`: atomic dtype
- Current restrictions:
  - only valid in kernel context
  - only `DT.float` is supported

Example:

```python
with atomic_min():
    out[:, :] <<= ub
```

## 3. Constructor and Validation Rules

### Common dtype rule

All three context managers currently enforce:

- `dtype` must be a `DataTypeValue`
- `dtype` must be exactly `DT.float`

So these are rejected today:

- `atomic_add(dtype=DT.half)`
- `atomic_max(dtype=DT.int)`
- `atomic_min(dtype=DT.bfloat16)`

### `atomic_add` conditional rule

`atomic_add` has one extra parameter:

- `cond`

Current behavior:

- if `cond is not None`, the constructor raises `NotImplementedError`

So conditional atomic add is part of the shape of the API, but not implemented yet.

## 4. Runtime Mechanism

### Entering the context

When you enter one of these context managers:

- the active kernel receives an `Instruction("atomic_add")`, `Instruction("atomic_max")`, or `Instruction("atomic_min")`
- global atomic state is updated:
  - `globvars.atomic_enabled = True`
  - `globvars.atomic_type = dtype`

That means the context manager itself does not perform a write. It only changes the mode for later emitted instructions.

### Leaving the context

On successful exit:

- the active kernel receives `Instruction("atomic_end")`
- global atomic state is reset:
  - `globvars.atomic_enabled = False`
  - `globvars.atomic_type = None`

If the block exits with an exception:

- `__exit__` returns `False`
- the original exception propagates

## 5. Where Atomic State Is Actually Consumed

The important part is not the `with` block itself. The important part is which later store instructions consult the current atomic state.

In the current codebase, the main writeback stubs that do this are:

### `l0c_to_gm_nz2nd`

When atomic mode is enabled and the destination GM dtype differs from the current cached atomic dtype:

- the stub emits `Instruction("set_atomic_type", dtype=dst.dtype)`
- it updates the cached `globvars.atomic_type`

Then the later `l0c_to_gm_nz2nd` instruction is emitted with the active atomic mode attached in simulator dispatch.

### `ub_to_gm_pad`

This behaves the same way:

- if atomic mode is enabled and `globvars.atomic_type is not dst.dtype`
- the stub emits `Instruction("set_atomic_type", dtype=dst.dtype)`
- then it emits `ub_to_gm_pad`

Practical implication:

- atomic scopes matter only when they enclose supported GM writeback operations
- enclosing unrelated compute or local-only operations does not magically make those operations atomic

## 6. Simulator Behavior

### Main-loop state

Both cube and vec simulators keep three atomic-state fields:

- `atomic_enabled`
- `atomic_dtype`
- `atomic_mode`

The mode changes when they see:

- `atomic_add` -> mode becomes `"add"`
- `atomic_max` -> mode becomes `"max"`
- `atomic_min` -> mode becomes `"min"`
- `set_atomic_type` -> updates `atomic_dtype`
- `atomic_end` -> clears all atomic state

### Which writeback paths apply atomic behavior

Current simulator atomic behavior is implemented in:

- `FIXPipe` for `l0c_to_gm_nz2nd`
- `MTE3Pipe` for `ub_to_gm_pad`

Those pipe executors:

- check `instruction.atomic_enabled`
- verify or compare `instruction.atomic_dtype`
- read `instruction.atomic_mode`
- apply the requested atomic op against the existing GM destination values

Supported atomic modes in the simulator:

- `add`
- `max`
- `min`

If the mode is missing, the simulator currently defaults to `add` and logs a warning.

### Numeric behavior

The simulator computes atomic updates as:

- `add`: `dst = dst + src`
- `max`: `dst = maximum(dst, src)`
- `min`: `dst = minimum(dst, src)`

For these atomic paths, the simulator:

- may use an internal compute dtype before casting back to the destination dtype
- preserves NaN behavior according to the underlying torch operation used by that mode

### Dtype mismatch behavior

If the writeback destination dtype string does not match the attached atomic dtype string:

- the simulator logs a warning

In normal framework use, the store stub tries to avoid this by emitting `set_atomic_type` when needed.

## 7. Codegen Behavior

The parser lowers these instructions to backend atomic-mode setters:

- `atomic_add` -> `SetAtomicAdd<float>();`
- `atomic_max` -> `SetAtomicMax<float>();`
- `atomic_min` -> `SetAtomicMin<float>();`
- `set_atomic_type(dtype)` -> `SetAtomicType<...>();`
- `atomic_end` -> `SetAtomicNone();`

So codegen and simulator follow the same high-level model:

1. enter one atomic mode
2. optionally retarget atomic dtype for a writeback
3. emit writeback ops
4. end atomic mode

## 8. Examples

### Vec-side atomic add writeback

```python
with atomic_add():
    out[:, :] <<= ub
```

Mental model:

- inside the block, `ub_to_gm_pad` writeback is performed as atomic add if that is the writeback path used by the assignment

### Cube-side atomic max writeback

```python
with atomic_max():
    z[:, :] <<= l0c
```

Mental model:

- inside the block, `l0c_to_gm_nz2nd` writeback is performed as atomic max if that is the writeback path used by the assignment

### Switching dtype automatically

```python
with atomic_add():
    out_f32[:, :] <<= ub_f32
```

If the destination dtype differs from the currently cached atomic dtype, the writeback stub inserts `set_atomic_type(dst.dtype)` automatically before the GM store instruction.

## 9. What Atomic Context Managers Do Not Replace

Do not confuse atomic scopes with:

- barriers
  - barriers order pipe progress
- events
  - events synchronize source and destination pipes
- mutexes
  - mutexes transfer ownership across cube and vec

Atomic scopes only change how a supported GM writeback combines with the existing destination contents.

## 10. Practical Guidance

- Use atomic scopes only around the smallest writeback region that really needs them.
- Expect atomic mode to matter only for supported GM store paths, not arbitrary enclosed instructions.
- Keep in mind that only `DT.float` is supported today.
- Do not rely on `cond` in `atomic_add`; it is currently unimplemented.
- If your destination is GM and multiple writers must merge values, atomic scopes are the right primitive; if your problem is ordering or ownership, use barriers, events, or mutexes instead.

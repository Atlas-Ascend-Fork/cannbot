# Barriers

This page documents the barrier helpers shared by `easyasc.a2` and `easyasc.a5`.

These APIs live in `easyasc/stub_functions/barrier.py` and emit `Instruction("barrier", pipe=...)` into the active kernel.

## 1. Overview

Barrier helpers are explicit pipe-ordering tools.

Typical examples:

```python
bar_v()
bar_m()
bar_all()
```

What a barrier does conceptually:

- it says "do not let later work on this scheduling path run ahead of earlier work on the selected pipe domain"

What a barrier does not do:

- it is not a cube/vec ownership primitive like `CvMutex` or `VcMutex`
- it is not a ready/valid event object like `SEvent` or `DEvent`
- it does not move data by itself

Use barriers when you need explicit pipe ordering beyond normal FIFO behavior, `auto_sync()`, or ownership handoff primitives.

## 2. Core API

### `barrier(pipe)`

- Purpose: emit a barrier instruction for one selected `PipeType`.
- Parameters:
  - `pipe`: a `PipeType` such as `Pipe.V`, `Pipe.M`, or `Pipe.ALL`
- Restrictions:
  - `pipe` must be `PipeType`
  - only valid in kernel context

Example:

```python
barrier(Pipe.V)
barrier(Pipe.ALL)
```

Current lowering:

- the parser lowers this to `PipeBarrier<PIPE_...>();`

Examples:

- `barrier(Pipe.V)` -> `PipeBarrier<PIPE_V>();`
- `barrier(Pipe.MTE2)` -> `PipeBarrier<PIPE_MTE2>();`
- `barrier(Pipe.ALL)` -> `PipeBarrier<PIPE_ALL>();`

## 3. Convenience Helpers

These helpers are fixed-argument wrappers around `barrier(pipe)`.

### `bar_m()`

- Equivalent to:

```python
barrier(Pipe.M)
```

- Typical use:
  - explicitly serialize cube compute work

### `bar_v()`

- Equivalent to:

```python
barrier(Pipe.V)
```

- Typical use:
  - explicitly serialize vec compute work

### `bar_mte3()`

- Equivalent to:

```python
barrier(Pipe.MTE3)
```

- Typical use:
  - explicitly serialize UB -> GM or UB -> L1 style output-side transfer work

### `bar_mte2()`

- Equivalent to:

```python
barrier(Pipe.MTE2)
```

- Typical use:
  - explicitly serialize GM -> L1 or GM -> UB style input-side transfer work

### `bar_mte1()`

- Equivalent to:

```python
barrier(Pipe.MTE1)
```

- Typical use:
  - explicitly serialize L1 -> L0 staging work

### `bar_fix()`

- Equivalent to:

```python
barrier(Pipe.FIX)
```

- Typical use:
  - explicitly serialize cube output-side publication work such as `l0c_to_ub` or `l0c_to_gm_nz2nd`

### `bar_all()`

- Equivalent to:

```python
barrier(Pipe.ALL)
```

- Typical use:
  - wait until all supported local pipes reach the barrier point

## 4. Mechanism and Mental Model

There are two useful cases to understand:

### Case 1: `barrier(Pipe.X)` for one normal pipe

Examples:

- `Pipe.MTE2`
- `Pipe.MTE1`
- `Pipe.M`
- `Pipe.V`
- `Pipe.FIX`
- `Pipe.MTE3`

Mechanically:

- the DSL emits one `barrier` instruction tagged with that pipe
- the parser lowers it to `PipeBarrier<PIPE_X>();`
- on generated backend code, the emitted `PipeBarrier<PIPE_X>();` is preserved
- in the current V2 simulator main loop, non-`ALL` barriers are preserved as control
  instructions but do not drain pipe queues by themselves

Practical meaning:

- treat this as a backend-level ordering marker, not as a simulator-enforced drain point

This is a pipe-local ordering primitive, not a cross-pipe handshake.

### Case 2: `barrier(Pipe.ALL)`

This is the stronger, special case.

Current simulator behavior is more explicit than a normal single-pipe barrier:

- the cube simulator expands `barrier(Pipe.ALL)` into waits on:
  - `MTE2`
  - `MTE1`
  - `M`
  - `FIX`
- the vec simulator expands `barrier(Pipe.ALL)` into waits on:
  - `MTE2`
  - `V`
  - `MTE3`

The current simulator does that by:

1. issuing a synthetic `setflag(src_pipe, Pipe.S, event_id=8)` onto each participating source pipe
2. waiting on the main loop until each synthetic flag becomes visible
3. consuming those flags one by one

That means `barrier(Pipe.ALL)` is modeled as:

- "every relevant local pipe must report back to the main loop before execution continues"

This is why it is much stronger than a single-pipe barrier.

## 5. What Problem a Barrier Solves

Barriers are useful when:

- you already know the work is on one pipe domain
- you need explicit ordering at that pipe boundary
- you do not want to introduce event objects or mutex ownership

Examples:

- force vec work on `Pipe.V` to finish before a later phase reads its result
- force `Pipe.MTE2` staging to complete before assuming the data producer side is drained
- force every local pipe to drain before reading a scalar or writing debug output on the main loop

## 6. What a Barrier Does Not Replace

Do not use a barrier as a substitute for:

- `CvMutex` / `VcMutex`
  - those solve cross cube/vec ownership handoff
- `SEvent` / `DEvent`
  - those solve explicit source-pipe to destination-pipe ready/valid synchronization
- `auto_sync()`
  - that synthesizes same-side events for known pipeline boundaries

Barrier is usually the bluntest tool in this family.

## 7. Examples

### Vec-side explicit pipe barrier

```python
gm_to_ub_pad(ub, x[m:m + blk, :], ...)
bar_v()
add(ub_out, ub, 1.0)
```

Mental model:

- if you know your later logic must not outpace the vec pipe phase, a `Pipe.V` barrier is an explicit stop point

### Full local drain on the vec side

```python
seed.SetValueTo(ub)
ub <<= src
bar_all()
val.GetValueFrom(ub)
val += one
val.SetValueTo(ub)
```

This matches the current simulator regression test for `barrier(Pipe.ALL)`: the scalar read and update after the barrier only happen after queued pipe work has drained.

### Cube-side explicit compute barrier

```python
mmad(l0c, l0a, l0b, M=M, N=N, K=K, is_init=True)
bar_m()
l0c_to_ub(ub, l0c)
```

Mental model:

- do not begin the next cube-output phase until the cube compute pipe reaches the barrier point

## 8. Practical Guidance

- Start with the narrowest barrier that matches the real dependency.
- Prefer `bar_m()`, `bar_v()`, or another single-pipe barrier over `bar_all()` when one pipe is enough.
- Treat `bar_all()` as a strong local drain point, not a casual synchronization hint.
- If the dependency is really source-pipe -> destination-pipe ordering, prefer events or `auto_sync()`.
- If the dependency is really cube/vec ownership, prefer `CvMutex` or `VcMutex`.

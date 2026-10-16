# Pipes

This page documents the pipe objects used throughout `easyasc`.

Two names matter here:

- `Pipe`: the public pipe namespace that kernel authors normally use
- `PipeType`: the concrete value object passed to barriers, flags, events, and cross-side synchronization helpers

In normal kernel code, you usually write `Pipe.MTE2`, `Pipe.V`, `Pipe.FIX`, `Pipe.S`, and similar names.

## 1. Overview

`Pipe` describes which execution pipeline or scheduling domain an operation belongs to.

Typical examples:

```python
barrier(Pipe.V)
setflag(Pipe.MTE2, Pipe.V, 0)
waitflag(Pipe.MTE2, Pipe.S, 0)
cv = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.V)
evt = SEvent(Pipe.MTE2, Pipe.V)
```

Where `Pipe` is used most often:

- barriers such as `barrier(Pipe.V)` or `barrier(Pipe.ALL)`
- flag helpers such as `setflag(src, dst, event_id)` and `waitflag(src, dst, event_id)`
- cross-side synchronization helpers such as `cube_ready(..., pipe=...)`, `wait_cube(..., pipe=...)`, `wait_vec(..., pipe=...)`
- explicit event objects such as `SEvent(src_pipe, dst_pipe)` and `DEvent(src_pipe, dst_pipe)`

Unlike `Position`, `Pipe` is not about where tensor storage lives. It is about which pipeline an instruction is associated with.

## 2. `Pipe`

### What it is

- `Pipe` is the public enum-like namespace exported by `easyasc.a2` and `easyasc.a5`
- each member is a predefined `PipeType` singleton

Available members:

| Public name | Meaning | Typical role |
| --- | --- | --- |
| `Pipe.MTE2` | load / input-side transfer pipe | GM -> L1 or GM -> UB style producers |
| `Pipe.MTE1` | L1 -> L0 transfer pipe | cube staging between L1 and L0 |
| `Pipe.M` | cube compute pipe | `mmad` and cube compute stages |
| `Pipe.V` | vec compute pipe | vec ops and micro-adjacent vec stages |
| `Pipe.FIX` | cube-side output / fix pipe | `l0c_to_ub`, `l0c_to_l1`, `l0c_to_gm_nz2nd` style consumers |
| `Pipe.MTE3` | store / output-side transfer pipe | UB -> GM and UB -> L1 style producers |
| `Pipe.S` | main-loop scheduling pipe | wait-side scheduling domain and special synchronization target |
| `Pipe.ALL` | all-pipe barrier domain | full barrier across local pipes |

### Why you should prefer `Pipe.*`

- it is the stable public authoring surface
- it gives you the singleton objects that the framework expects
- many internal checks compare pipes by identity or expect exact `PipeType` instances

This is the safe pattern:

```python
pipe = Pipe.V
```

and this is not recommended:

```python
pipe = PipeType("V")
```

Even though `PipeType("V") == Pipe.V` is true, it is not the same singleton object, so identity-based code or exact exported-member assumptions may not behave the same way.

## 3. `PipeType`

### `PipeType(name)`

- Purpose: represent one concrete pipe value
- Constructor parameter:
  - `name`: pipe name such as `"V"` or `"MTE2"`

You usually do not instantiate this class directly. The framework already provides the standard instances through `Pipe`.

### `__str__()` and `__repr__()`

- `str(pipe)` returns the plain pipe name
- `repr(pipe)` returns `PipeType('...')`

Examples:

```python
str(Pipe.MTE2)   # "MTE2"
repr(Pipe.S)     # "PipeType('S')"
```

### Equality and hashing

- equality compares pipe names
- comparing with a non-`PipeType` raises `TypeError`
- `PipeType` is hashable, so it can be used as a dict key or set member

Examples:

```python
Pipe.V == Pipe.V
Pipe.MTE2 == Pipe.MTE2
```

But:

```python
Pipe.V == "V"   # raises TypeError
```

## 4. Practical Meaning of Each Pipe

### `Pipe.MTE2`

- commonly the input-side transfer pipe
- in current autosync classification, this pipe owns:
  - `gm_to_l1_nd2nz`
  - `set_constant_to_l1`
  - `gm_to_ub_pad`

Typical interpretation:

- data is being brought into on-chip memory from an upstream source

Common examples:

```python
evt = SEvent(Pipe.MTE2, Pipe.V)
setflag(Pipe.MTE2, Pipe.V, 0)
```

### `Pipe.MTE1`

- commonly the L1 -> L0 transfer pipe
- in current autosync classification, this pipe owns:
  - `l1_to_l0`

Typical interpretation:

- a cube-side staging step is moving prepared L1 tiles into L0 input buffers

Common examples:

```python
evt = DEvent(Pipe.MTE2, Pipe.MTE1)
barrier(Pipe.MTE1)
```

### `Pipe.M`

- cube compute pipe
- in current autosync classification, this pipe owns:
  - `mmad`

Typical interpretation:

- matmul or cube compute is in flight

Common examples:

```python
evt = DEvent(Pipe.MTE1, Pipe.M)
barrier(Pipe.M)
```

### `Pipe.V`

- vec compute pipe
- vec-side explicit ops that are not claimed by `MTE2`, `MTE1`, `M`, `FIX`, or `MTE3` are treated as `V`-pipe work in autosync classification

Typical interpretation:

- elementwise vec compute, reductions, comparisons, sort helpers, and similar vec-side operations

Common examples:

```python
barrier(Pipe.V)
evt = SEvent(Pipe.MTE2, Pipe.V)
```

### `Pipe.FIX`

- cube-side output / fix pipe
- in current autosync classification, this pipe owns:
  - `l0c_to_gm_nz2nd`
  - `l0c_to_l1`
  - `l0c_to_ub`

Typical interpretation:

- cube results are being published out of `L0C` toward later stages

Common examples:

```python
cv = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.V)
barrier(Pipe.FIX)
```

### `Pipe.MTE3`

- commonly the output-side transfer pipe
- in current autosync classification, this pipe owns:
  - `ub_to_gm_pad`
  - `ub_to_l1_nd2nz`
  - `ub_to_l1_nz`

Typical interpretation:

- vec-side output or repacked UB data is being written onward to GM or L1

Common examples:

```python
evt = SEvent(Pipe.V, Pipe.MTE3)
vc = VcMutex(1, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)
```

### `Pipe.S`

- special scheduling pipe used as a main-loop synchronization domain
- this is not a normal producer pipe for `setflag` / `waitflag` source selection

Important current restrictions:

- `setflag(src, dst, ...)` forbids `src == Pipe.S`
- `waitflag(src, dst, ...)` forbids `src == Pipe.S`
- `Pipe.S` is still valid as a destination in flag waits and is also the default wait pipe for several cross-side helpers

Typical interpretation:

- "wait on the main loop" rather than "wait inside a normal compute/transfer pipe"

Common examples:

```python
waitflag(Pipe.MTE2, Pipe.S, 0)
wait_cube(flag_id=0, pipe=Pipe.S)
wait_vec(flag_id=0, pipe=Pipe.S)
```

This is why many synchronization helpers default to `Pipe.S` on the wait side: they want the blocking behavior to occur in the main scheduling loop.

### `Pipe.ALL`

- special all-pipe domain used for barriers
- not a normal source or destination pipe for flag events

Important current restrictions:

- `setflag` forbids `src == Pipe.ALL`
- `setflag` forbids `dst == Pipe.ALL`
- `waitflag` forbids `src == Pipe.ALL`
- `waitflag` forbids `dst == Pipe.ALL`

Typical use:

```python
barrier(Pipe.ALL)
```

Interpretation:

- wait until all queued local pipe work reaches the barrier point

## 5. How Pipes Show Up in Framework Behavior

### Autosync pipe partitioning

The current autosync logic groups operations into these main same-side pipe boundaries:

- vec side:
  - `MTE2 -> V`
  - `V -> MTE3`
- cube side:
  - `MTE2 -> MTE1`
  - `MTE1 -> M`
  - `M -> FIX`

That is why these pipe names appear repeatedly in event pairs, traces, and generated code.

### Flags and explicit events

`setflag(src, dst, event_id)` and `waitflag(src, dst, event_id)` use `PipeType` values to identify a source pipe and a destination pipe.

`SEvent(src_pipe, dst_pipe)` and `DEvent(src_pipe, dst_pipe)` do the same thing at the object level.

So when you write:

```python
SEvent(Pipe.MTE2, Pipe.V)
```

you are saying:

- producer side: `MTE2`
- consumer side: `V`

### Barriers

`barrier(pipe)` also takes a `PipeType`.

Examples:

```python
barrier(Pipe.M)
barrier(Pipe.V)
barrier(Pipe.ALL)
```

The pipe controls whether the barrier is local to one pipe or global across all local pipes.

### Cross-side waits and ready signals

The pipe on `cube_ready`, `vec_ready`, `wait_cube`, `wait_vec`, and the allcore variants does not change the logical flag id. It changes where that synchronization instruction is scheduled.

Common defaults in the current API surface:

- `cube_ready(..., pipe=Pipe.FIX)`
- `vec_ready(..., pipe=Pipe.MTE3)`
- `wait_cube(..., pipe=Pipe.S)`
- `wait_vec(..., pipe=Pipe.S)`

That matches the common mixed-pipeline shape:

- cube publishes after its output-side work
- vec publishes after its output-side work
- waits often happen on the main loop

## 6. Codegen Meaning

The parser lowers `PipeType` values by name.

Current pipe lowering uses forms such as:

```python
PIPE_MTE2
PIPE_V
PIPE_S
PIPE_ALL
```

Examples:

- `barrier(Pipe.V)` lowers to `PipeBarrier<PIPE_V>();`
- `setflag(Pipe.MTE2, Pipe.V, 0)` lowers to `SetFlag<PIPE_MTE2, PIPE_V>(0);`

So `Pipe` values are not just labels for docs. They become concrete backend template arguments.

## 7. Practical Guidance

- Use predefined `Pipe.*` members in normal kernel code.
- Do not hand-construct `PipeType(...)` unless you are extending framework internals.
- Use `Pipe.S` for wait-side main-loop scheduling when the API expects that pattern.
- Use `Pipe.ALL` only for all-pipe barriers, not for flags.
- Think of `MTE2` as input-side movement, `MTE1` as L1 -> L0 movement, `M` as cube compute, `V` as vec compute, `FIX` as cube output-side movement, and `MTE3` as vec output-side movement.
- When reading autosync output or traces, the canonical same-side handoff pairs are `MTE2 -> V`, `V -> MTE3`, `MTE2 -> MTE1`, `MTE1 -> M`, and `M -> FIX`.

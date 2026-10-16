# Mixed Pipeline and Synchronization

This repository supports kernels that cross cube and vec execution, but the synchronization model is intentionally explicit.

## 1. Pipeline topologies

Most kernels in the repository fit one of these shapes:

- cube only: `GM -> L1 -> L0C -> GM`
- cube -> vec: `... -> L0C -> UB -> vec -> GM`
- vec -> cube: `GM -> UB -> vec -> L1 -> L0C -> GM`
- vec -> cube -> vec
- cube -> vec -> cube
- cube -> vec -> cube -> vec

Choose the topology first. It determines:

- which buffers you need
- which side owns each stage
- whether `auto_sync()` is enough
- where explicit mutex handoff is required

## 2. What `auto_sync()` actually does

`auto_sync()` is not a universal synchronization feature. In the current implementation it:

- emits region markers during authoring
- rewrites supported same-side producer/consumer pairs during parser lowering
- inserts event creation plus `event_wait` / `event_set` instructions for those pairs

It does not, by itself, transfer ownership between cube and vec.

## 3. Same-side pipe pairs supported by `auto_sync()`

Current hard-coded autosync coverage is organized around these pairs:

- vec side:
  - `MTE2 -> V`
  - `V -> MTE3`
- cube side:
  - `MTE2 -> MTE1`
  - `MTE1 -> M`
  - `M -> FIX`

If an operation is outside those classified pairs, current `auto_sync()` will not build a handshake for it.

## 4. When you need explicit mutexes

Use explicit mutexes when ownership crosses between cube and vec.

The two main types are:

- `CvMutex`: cube producer, vec consumer
- `VcMutex`: vec producer, cube consumer

Typical patterns in this repository:

- cube -> vec handoff around `l0c_to_ub` followed by a `@vf` or vec stage
- vec -> cube handoff around `ub_to_l1_nd2nz` or `ub_to_l1_nz` followed by `matmul`

## 5. Cube -> vec example

The compact pattern in `agent/example/kernels/a5/basic_cube_vec_mix.py` looks like this:

```python
cvmutex = CvMutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.V)

cvmutex.lock()
xbuf[cnt] <<= l0c[cnt]
cvmutex.ready()

cvmutex.wait()
simple_micro(xbuf[cnt], outbuf[cnt], ...)
cvmutex.free()
```

Read the lifecycle as:

1. producer acquires a slot
2. producer fills the slot
3. producer marks the slot ready
4. consumer waits for readiness
5. consumer processes the slot
6. consumer releases the slot

## 6. Vec -> cube example

The inverse pattern appears in vec-preprocess kernels:

1. UB data is produced on the vec side
2. a `VcMutex` guards the publish boundary
3. the vec side writes or republishes into L1
4. cube-side matmul consumes the published tile

This is the right mental model for files such as:

- `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul.py`
- `agent/example/kernels/a5/vec_cube_abs_sqrt_matmul_nz.py`

## 7. Tail-safe writeback rule

Mixed kernels frequently compute a full local tile but write back only a valid subset.

The common vec-side subblock pattern is:

```python
valid_m = Min(BLK, m2 - m)
half_rows = CeilDiv(valid_m, 2)
sb_idx = GetSubBlockIdx()
row_begin = sb_idx * half_rows
row_end = Min(row_begin + half_rows, valid_m)
row_count = row_end - row_begin
z[m + row_begin:m + row_end, :] <<= outbuf[cnt][0:row_count, :]
```

Why this matters:

- GM boundaries must respect the logical tail
- local UB or L0C tiles usually stay at fixed full sizes
- two vector subblocks can safely split the valid rows

## 8. Buffer ownership rules

A stable pattern across repository kernels is:

- GM boundaries use `valid_m`, `valid_n`, `valid_k`
- local buffers keep constant tile size
- counters advance monotonically and often match DBuff parity
- producer and consumer stay close to the buffer handoff site

Do not let a buffer's lifetime extend far beyond its producer/consumer pair unless you have a clear reason.

## 9. Practical guidance

Use this checklist when synchronization starts getting confusing:

1. identify the producing side
2. identify the consuming side
3. list the exact source and destination buffers
4. decide whether the boundary is same-side or cross-side
5. use `auto_sync()` only for same-side ordering
6. use `CvMutex` or `VcMutex` for cross-side ownership

## 10. Files worth studying

- `agent/example/kernels/a5/basic_cube_vec_mix.py`
- `agent/example/kernels/a5/vec_cube_vec_scale2_abs_add1_matmul.py`
- `agent/example/kernels/a5/test_mla_entire.py`

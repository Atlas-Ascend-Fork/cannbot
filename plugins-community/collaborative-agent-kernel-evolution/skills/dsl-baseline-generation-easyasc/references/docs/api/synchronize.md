# Synchronization

This page documents the explicit synchronization primitives exported by `easyasc.a2` and `easyasc.a5`:

- `CvMutex`
- `VcMutex`
- `cube_ready`, `vec_ready`, `wait_cube`, `wait_vec`
- `allcube_ready`, `allvec_ready`, `allcube_wait`, `allvec_wait`
- `setflag`, `waitflag`
- `SEvent`
- `DEvent`

There are three different families here:

- `CvMutex` / `VcMutex`: cross-side ownership handoff between cube and vec
- raw cross-core/all-core flag ops: lower-level cube/vec and collective synchronization
- raw pipe flags: local pipe-to-pipe synchronization keyed by `(src, dst, event_id)`
- `SEvent` / `DEvent`: local pipe-to-pipe ordering inside one execution entity

Use that distinction first:

- if ownership crosses between cube and vec, use a mutex
- if you want the same token mechanism without wrapping it as a mutex object, use the raw cross-core/all-core ops
- if you want direct pipe-to-pipe flags instead of named event objects, use `setflag` / `waitflag`
- if you only need ordering between local pipes such as `MTE2 -> V` or `V -> MTE3`, use an event

For the higher-level mixed-pipeline discussion, see [../04_mixed_pipeline_and_sync.md](../04_mixed_pipeline_and_sync.md).

## 1. `CvMutex`

### `CvMutex(flag_id, depth=2, src_start_pipe=Pipe.S, dst_start_pipe=Pipe.S, src_end_pipe=Pipe.FIX, dst_end_pipe=None)`

- Purpose: represent a cube-producer / vec-consumer ownership handshake.
- Typical use:
  - cube writes or publishes a tile
  - vec waits for that tile
  - vec returns the slot when finished

### Parameters

- `flag_id`:
  - logical cross-side flag id
  - must map to a hardware-supported flag id
  - current emitters require an integer in the range `0..7`
- `depth`:
  - intended logical slot depth, commonly `2` for ping-pong buffering
  - stored on the mutex object and recorded in kernel metadata
  - current Python simulator does not decrement or enforce `depth` directly, so treat it as configuration metadata rather than a simulator-side counter
- `src_start_pipe`:
  - pipe used by `lock()`
  - default `Pipe.S`
- `dst_start_pipe`:
  - pipe used by vec-side `wait()`
  - default `Pipe.S`
- `src_end_pipe`:
  - pipe used by cube-side `ready()`
  - default `Pipe.FIX`
- `dst_end_pipe`:
  - pipe used by vec-side `free()`
  - if `None`, the constructor chooses a device-specific default:
    - `b*` devices -> `Pipe.MTE2`
    - device `950` -> `Pipe.V`
    - otherwise -> `Pipe.MTE3`

### Registration and restrictions

- If the object is created inside an active kernel, it is registered into `active_kernel.crosscore_mutex`.
- A kernel may not register two mutex objects with the same `flag_id`.
- `CvMutex` is for cross cube/vec ownership. It is not the same mechanism as `SEvent` / `DEvent`, and it is not what `auto_sync()` uses for same-side staging.

### Methods

#### `lock()`

- Emits: `wait_vec(flag_id, src_start_pipe)`
- Role: cube-side acquire
- Meaning in the simulator:
  - cube waits until every vec lane has published one return token for this `flag_id`
  - only when all vec lanes have returned the slot can cube reuse it

#### `ready()`

- Emits: `cube_ready(flag_id, src_end_pipe)`
- Role: cube-side publish
- Meaning in the simulator:
  - one call publishes one token to every vec lane
  - each vec lane can then consume that published tile independently

#### `wait()`

- Emits: `wait_cube(flag_id, dst_start_pipe)`
- Role: vec-side consume wait
- Meaning in the simulator:
  - the current vec lane waits for its own published token
  - consuming on lane `0` does not automatically consume lane `1`

#### `free()`

- Emits: `vec_ready(flag_id, dst_end_pipe)`
- Role: vec-side release
- Meaning in the simulator:
  - the current vec lane returns one token to cube
  - cube `lock()` does not pass until all vec lanes have returned their tokens

### Runtime mechanism

The current simulator models a shared cross-side token state per simulated core:

- `cube_ready(flag_id)` increments one `cube -> vec` token for every vec lane
- `wait_cube(flag_id)` consumes one `cube -> vec` token only for the current vec lane
- `vec_ready(flag_id)` increments one `vec -> cube` token only for the current vec lane
- `wait_vec(flag_id)` succeeds only when every vec lane has at least one `vec -> cube` token, then consumes one from every lane

That gives `CvMutex` this concrete lifecycle:

1. cube `lock()` waits for all vec lanes to say "the old slot is free"
2. cube fills the slot
3. cube `ready()` broadcasts "new data is available" to all vec lanes
4. each vec lane `wait()`s independently
5. each vec lane processes the slot
6. each vec lane `free()`s independently
7. once every lane has freed, cube can `lock()` again

This is why `CvMutex` behaves like an ownership handshake, not like a single boolean flag.

### Example: cube publishes, vec consumes

```python
cv = CvMutex(
    0,
    depth=2,
    src_end_pipe=Pipe.FIX,
    dst_end_pipe=Pipe.V,
)

cv.lock()                 # cube waits until both vec sub-blocks have returned the slot
xbuf[cnt] <<= l0c[cnt]    # publish data into the shared handoff buffer
cv.ready()                # cube broadcasts one ready token to each vec lane

cv.wait()                 # current vec lane waits for its own ready token
simple_micro(xbuf[cnt], outbuf[cnt], ...)
cv.free()                 # this vec lane returns its token to cube
```

With two vec sub-blocks, the token flow looks like:

- after `cv.ready()`: lane0 has `1`, lane1 has `1`
- after lane0 `cv.wait()`: lane0 has `0`, lane1 has `1`
- after lane1 `cv.wait()`: lane0 has `0`, lane1 has `0`
- after lane0 `cv.free()`: cube still cannot reacquire, because lane1 has not returned yet
- after lane1 `cv.free()`: cube `lock()` can succeed again

### Example: binding through `GMTensor`

`GMTensor.bind_cv_mutex()` is a convenience wrapper around the same object:

```python
z.bind_cv_mutex(0, src_end_pipe=Pipe.FIX, dst_end_pipe=Pipe.V)

z.lock()
z <<= ub_tile
z.ready()

z.wait()
z.free()
```

The `GMTensor` methods forward directly to the bound mutex. For the tensor-side API surface, see [tensor_buffer.md](tensor_buffer.md).

## 2. `VcMutex`

### `VcMutex(flag_id, depth=2, src_start_pipe=Pipe.S, dst_start_pipe=Pipe.S, src_end_pipe=Pipe.MTE3, dst_end_pipe=Pipe.FIX)`

- Purpose: represent a vec-producer / cube-consumer ownership handshake.
- Typical use:
  - vec prepares or repacks a tile
  - cube waits for the tile
  - cube returns the slot after consuming it

This is the inverse direction of `CvMutex`.

### Parameters

- `flag_id`:
  - logical cross-side flag id
  - current emitters require `0..7`
- `depth`:
  - intended logical slot depth, commonly aligned with your DBuff/TBuff slot count
  - current simulator does not consume it numerically
- `src_start_pipe`:
  - pipe used by vec-side `lock()`
  - default `Pipe.S`
- `dst_start_pipe`:
  - pipe used by cube-side `wait()`
  - default `Pipe.S`
- `src_end_pipe`:
  - pipe used by vec-side `ready()`
  - default `Pipe.MTE3`
- `dst_end_pipe`:
  - pipe used by cube-side `free()`
  - default `Pipe.FIX`

### Registration and restrictions

- Same kernel-registration rules as `CvMutex`
- duplicate `flag_id` inside one kernel is rejected

### Methods

#### `lock()`

- Emits: `wait_cube(flag_id, src_start_pipe)`
- Role: vec-side acquire
- Meaning in the simulator:
  - current vec lane waits for cube to return this slot

#### `ready()`

- Emits: `vec_ready(flag_id, src_end_pipe)`
- Role: vec-side publish
- Meaning in the simulator:
  - current vec lane publishes one token to cube

#### `wait()`

- Emits: `wait_vec(flag_id, dst_start_pipe)`
- Role: cube-side consume wait
- Meaning in the simulator:
  - cube waits until every vec lane has published one token
  - then cube consumes one token from every lane together

#### `free()`

- Emits: `cube_ready(flag_id, dst_end_pipe)`
- Role: cube-side release
- Meaning in the simulator:
  - cube broadcasts one return token back to every vec lane

### Runtime mechanism

`VcMutex` uses the same shared cross-side token store as `CvMutex`, but from the opposite direction:

1. each vec lane `lock()`s until cube has returned a reusable slot
2. each vec lane fills or republishes its portion
3. each vec lane `ready()`s
4. cube `wait()`s until every lane has published
5. cube consumes the full tile
6. cube `free()`s, which returns one token to every vec lane

This is why `VcMutex` is the right tool when a cube op needs all vec sub-blocks to finish their part before cube continues.

### Example: vec preprocess, cube consumes

```python
vc = VcMutex(
    1,
    depth=2,
    src_end_pipe=Pipe.MTE3,
    dst_end_pipe=Pipe.FIX,
)

vc.lock()                        # each vec lane waits for cube to return a slot
preprocess_micro(ub_in, ub_tmp)  # vec work
ub_to_l1_nd2nz(l1_tile, ub_tmp, valid_m, valid_k, tile_k, l1_rows)
vc.ready()                       # each vec lane publishes its completion token

vc.wait()                        # cube waits until every vec lane is ready
matmul(l0c, l1a_tile, l1b_tile)
vc.free()                        # cube returns the slot to every vec lane
```

## 3. Cross-Core and All-Core Synchronization

These APIs are the low-level synchronization instructions that the mutex wrappers build on top of.

Think of them in two layers:

- cross-core in this repository's naming means "cross cube/vec side within one simulated core"
- all-core means a collective synchronization across every participant of one family

That naming can be confusing at first, because `cube_ready` / `wait_cube` do not synchronize different physical cube cores. They synchronize cube and vec participants that share the same `flag_id`.

### Shared argument rules

All eight helpers have the same two arguments:

- `flag_id`:
  - logical token namespace
  - must be an `int` in the range `0..7`
  - helpers reject values outside that range before instruction emission
- `pipe`:
  - where the ready or wait is attached
  - must be a `PipeType`
  - the simulator accepts only the side-specific pipe sets listed below

Simulator-side accepted pipe sets:

- cube-side ops (`cube_ready`, `wait_vec`, `allcube_ready`, `allcube_wait`):
  - `Pipe.S`, `Pipe.MTE2`, `Pipe.MTE1`, `Pipe.M`, `Pipe.FIX`
- vec-side ops (`vec_ready`, `wait_cube`, `allvec_ready`, `allvec_wait`):
  - `Pipe.S`, `Pipe.MTE2`, `Pipe.V`, `Pipe.MTE3`

The meaning of `pipe` is:

- on `*_ready`, it identifies the producer-side pipe that publishes the token
- on `*_wait`, it identifies the consumer-side pipe or main loop that blocks for the token

If `pipe is Pipe.S`, the simulator runs the wait/ready directly on the main scheduling loop. Otherwise, it dispatches the instruction into the matching pipe queue.

### 3.1 Cross-side single-core token ops

These four helpers operate on the shared `CrossCoreSyncState` of one simulated core.

The simulator stores two token maps keyed by `(flag_id, vec_lane)`:

- `cube -> vec`
- `vec -> cube`

This is the same underlying mechanism used by `CvMutex` and `VcMutex`.

#### `cube_ready(flag_id=0, pipe=Pipe.FIX)`

- Purpose: publish one cube-to-vec token to every vec lane for `flag_id`.
- Emits: `cube_ready`
- Simulator effect:
  - increments `cube_to_vec[(flag_id, lane)]` for every vec lane
- Typical use:
  - cube finishes producing a shared tile
  - every vec lane is now allowed to consume its own view of that tile

Example:

```python
cube_ready(flag_id=0, pipe=Pipe.FIX)
```

#### `wait_cube(flag_id=0, pipe=Pipe.S)`

- Purpose: block the current vec lane until cube has published a token for that lane.
- Emits: `wait_cube`
- Simulator effect:
  - checks `cube_to_vec[(flag_id, current_lane)]`
  - if available, consumes exactly one token for the current vec lane
  - lane `0` and lane `1` wait independently
- Mental model:
  - this is a per-lane consumer wait, not a collective wait across vec lanes

Example:

```python
wait_cube(flag_id=0, pipe=Pipe.S)
```

#### `vec_ready(flag_id=0, pipe=Pipe.MTE3)`

- Purpose: publish one vec-to-cube return token from the current vec lane.
- Emits: `vec_ready`
- Simulator effect:
  - increments `vec_to_cube[(flag_id, current_lane)]` by `1`
- Typical use:
  - current vec lane has finished consuming or producing its portion
  - cube may proceed only after every lane has published its token

Example:

```python
vec_ready(flag_id=0, pipe=Pipe.MTE3)
```

#### `wait_vec(flag_id=0, pipe=Pipe.S)`

- Purpose: block cube until every vec lane has published one token for `flag_id`.
- Emits: `wait_vec`
- Simulator effect:
  - checks that `vec_to_cube[(flag_id, lane)] > 0` for every vec lane
  - if true, consumes one token from every lane together
- Mental model:
  - `wait_vec` is a lane-collective gather on one core
  - cube does not continue when only one vec lane is done

Example:

```python
wait_vec(flag_id=0, pipe=Pipe.S)
```

### Cross-side token lifecycle

For one simulated core with two vec lanes:

1. cube calls `cube_ready(3)`
2. simulator increments:
   - lane0 `cube_to_vec[(3, 0)] += 1`
   - lane1 `cube_to_vec[(3, 1)] += 1`
3. vec lane0 calls `wait_cube(3)` and consumes only its own token
4. vec lane1 calls `wait_cube(3)` and consumes only its own token
5. each vec lane eventually calls `vec_ready(3)`
6. cube calls `wait_vec(3)` and succeeds only after both lane0 and lane1 have contributed a return token

So the raw APIs are asymmetric by design:

- `cube_ready` broadcasts to all vec lanes
- `wait_cube` consumes per vec lane
- `vec_ready` publishes per vec lane
- `wait_vec` gathers from all vec lanes

That asymmetry is exactly what makes `CvMutex` and `VcMutex` work.

### Example: manual cube -> vec handoff without `CvMutex`

```python
cube_ready(flag_id=2, pipe=Pipe.FIX)
wait_cube(flag_id=2, pipe=Pipe.S)

# vec-side work happens here

vec_ready(flag_id=2, pipe=Pipe.V)
wait_vec(flag_id=2, pipe=Pipe.S)
```

This is lower-level than `CvMutex`:

- you manage the handshake yourself
- no `lock()/ready()/wait()/free()` naming help is provided
- no ownership intent is encoded in an object

Use the raw ops when you need that direct control. Use `CvMutex` / `VcMutex` when the pattern is an ownership handoff.

### 3.2 All-core collective ops

These four helpers operate on the simulator's shared `AllCoreSyncState`.

They do not use one global boolean flag. Instead, they use per-participant ready and wait counters, which makes them phase-aware collective barriers.

Participants are:

- `allcube_*`: every simulated cube core, keyed by `core_idx`
- `allvec_*`: every simulated vec participant, keyed by a global vec index

For vec, the simulator computes:

- `global_vec_idx = core_id * 2 + sub_block_idx`

So `allvec_*` is a collective across all vec lanes of all simulated cores, not just the two lanes inside one core.

#### `allcube_ready(flag_id=0, pipe=Pipe.FIX)`

- Purpose: declare that the current cube core has reached collective phase `k` for `flag_id`.
- Emits: `allcube_ready`
- Simulator effect:
  - increments `allcube_ready[(flag_id, core_idx)]`

#### `allcube_wait(flag_id=0, pipe=Pipe.S)`

- Purpose: block the current cube core until every cube core has reached the same collective phase.
- Emits: `allcube_wait`
- Simulator effect:
  - reads the current local wait count `phase = allcube_wait[(flag_id, core_idx)]`
  - succeeds only when every core's ready count is greater than `phase`
  - then increments this core's wait count to move it to the next phase

This means `allcube_wait` behaves like a reusable barrier, not a one-shot latch.

#### `allvec_ready(flag_id=0, pipe=Pipe.MTE3)`

- Purpose: declare that the current global vec participant has reached collective phase `k`.
- Emits: `allvec_ready`
- Simulator effect:
  - increments `allvec_ready[(flag_id, global_vec_idx)]`

#### `allvec_wait(flag_id=0, pipe=Pipe.S)`

- Purpose: block the current global vec participant until every vec participant has reached the same collective phase.
- Emits: `allvec_wait`
- Simulator effect:
  - uses the same phase-counter logic as `allcube_wait`, but over all global vec participants

### Why all-core waits are phase-based

Suppose there are four cube cores and all of them execute:

```python
allcube_ready(flag_id=1)
allcube_wait(flag_id=1)
allcube_ready(flag_id=1)
allcube_wait(flag_id=1)
```

The simulator does not confuse the first barrier with the second one.

For core `i`, the first `allcube_wait` checks whether every core has `ready_count > 0`.
After that wait succeeds, core `i` records `wait_count = 1`.
The second `allcube_wait` then checks whether every core has `ready_count > 1`.

That is why the barrier can be reused in loops without requiring a new `flag_id` every iteration.

### Example: reusable all-cube barrier

```python
for stage in range(num_stage):
    # local cube work
    allcube_ready(flag_id=1, pipe=Pipe.FIX)
    allcube_wait(flag_id=1, pipe=Pipe.S)
```

Meaning:

- each core publishes "I finished this stage"
- no core starts the next stage until every core has published the same stage

### Example: reusable all-vec barrier

```python
allvec_ready(flag_id=4, pipe=Pipe.MTE3)
allvec_wait(flag_id=4, pipe=Pipe.S)
```

Meaning:

- every global vec participant must report ready once
- only then may any participant pass the wait for that phase

### Simulator execution notes

- all-core ops trigger a parallel execution mode in the simulator, because collective waits would deadlock under a strictly serial per-core run order
- if a required peer never publishes its ready token, the simulator raises a deadlock error for `allcube_wait` or `allvec_wait`
- `Pipe.S` waits are handled on the main loop; other accepted pipes are queued on the corresponding pipe implementation

### Relationship to mutexes and events

- raw cross-side ops and `CvMutex` / `VcMutex` use the same cross-side token store
- all-core ops are a separate collective mechanism and are not wrapped by the mutex classes
- `SEvent` / `DEvent` are local per-entity pipe-ordering primitives and do not participate in these global token stores

## 4. Flag Helpers

`setflag` and `waitflag` are the lowest-level explicit local synchronization helpers exposed in the DSL.

Unlike `cube_ready` / `wait_vec`:

- they do not synchronize cube against vec
- they do not use the cross-side token stores
- they synchronize one local source pipe against one local destination pipe inside the same execution entity

In generated code, these lower directly to:

- `SetFlag<src, dst>(event_id)`
- `WaitFlag<src, dst>(event_id)`

So they are the raw flag form that both cube and vec sides can use when you want explicit pipe pairing rather than an `SEvent` / `DEvent` object.

### `setflag(src, dst, event_id)`

- Purpose: publish one local pipe flag from `src` to `dst`.
- Parameters:
  - `src`: source `PipeType`
  - `dst`: destination `PipeType`
  - `event_id`: `int` or `Var`
- Validation rules:
  - `src` must be a `PipeType`
  - `dst` must be a `PipeType`
  - `src` cannot be `Pipe.S`
  - `src` cannot be `Pipe.ALL`
  - `dst` cannot be `Pipe.ALL`
  - `event_id` must be in the range `0..7`
- Instruction emission:
  - emits `Instruction("setflag", src=..., dst=..., event_id=...)`
- Simulator effect:
  - when the instruction executes, the simulator stores one boolean token under the key:

```python
("flag", str(src), str(dst), event_id)
```

  - the token becomes `True`

### `waitflag(src, dst, event_id)`

- Purpose: wait for and consume one local pipe flag from `src` to `dst`.
- Parameters:
  - same meanings and validation rules as `setflag`
- Instruction emission:
  - emits `Instruction("waitflag", src=..., dst=..., event_id=...)`
- Simulator effect:
  - waits until the same key:

```python
("flag", str(src), str(dst), event_id)
```

  becomes `True`
  - once the wait succeeds, the token is consumed back to `False`

### Token model

The simulator treats pipe flags as one-token latches scoped to one execution entity:

- one cube core instance has its own local flag store
- one vec sub-block instance has its own local flag store

That means:

- cube-side `setflag` only talks to cube-side `waitflag`
- vec-side `setflag` only talks to vec-side `waitflag`
- these helpers are not a substitute for cross-side ownership

The key idea is:

- `src` says which producer pipe will eventually publish the flag
- `dst` says which consumer pipe or main loop is waiting for it
- `event_id` distinguishes multiple independent flag streams between the same source/destination pair

### Source and destination restrictions

Why `src` cannot be `Pipe.S`:

- `Pipe.S` is the main scheduling loop, not a real producer pipe queue
- the simulator and codegen only support issuing `setflag` from a concrete producer pipe

Why `Pipe.ALL` is rejected:

- `Pipe.ALL` is a barrier concept, not a valid flag endpoint
- there is no meaningful single flag token that comes from or targets "all pipes"

Why `dst` may be `Pipe.S`:

- waiting on `Pipe.S` means the main loop itself blocks until the source pipe publishes the token
- this is useful when later scheduling decisions must not run ahead of a producer pipe

### Two execution modes

`waitflag` behaves differently depending on whether `dst` is `Pipe.S`.

#### Case 1: `dst != Pipe.S`

- the instruction is dispatched into the destination pipe queue
- that pipe's execution loop checks the token before running the wait
- once the token exists, the wait consumes it and the pipe continues

This is the natural "pipe A signals pipe B" path.

#### Case 2: `dst == Pipe.S`

- the wait runs on the main loop instead of inside a pipe queue
- while blocked, the main loop repeatedly steps one pending pipe instruction trying to make progress
- if no instruction can make progress and the token never appears, the simulator raises a deadlock error

This is what lets a kernel write:

```python
setflag(Pipe.V, Pipe.S, 1)
waitflag(Pipe.V, Pipe.S, 1)
```

and still have the `Pipe.V` producer run before the main loop wait consumes the token.

### Example: vec pipe notifies the main loop

```python
setflag(Pipe.V, Pipe.S, 1)
waitflag(Pipe.V, Pipe.S, 1)
```

Meaning:

- the `V` pipe will eventually publish event `1` for the main loop
- the main loop will not continue until that `V -> S` token appears
- once consumed, the token is cleared, so a second `waitflag(Pipe.V, Pipe.S, 1)` would need a new `setflag`

### Example: cube pipe notifies the main loop

```python
setflag(Pipe.M, Pipe.S, 3)
waitflag(Pipe.M, Pipe.S, 3)
```

This is the cube-side counterpart covered by the simulator tests.

### Example: pipe-to-pipe handoff

```python
setflag(Pipe.MTE2, Pipe.V, 0)
waitflag(Pipe.MTE2, Pipe.V, 0)
```

Meaning:

- `MTE2` publishes one token
- `V` waits for exactly that token
- after the wait consumes it, the same `event_id` channel is empty again

### Difference from `SEvent`

`setflag` / `waitflag` and `SEvent` solve a similar class of problem, but at different abstraction levels.

`setflag` / `waitflag`:

- keyed directly by `src`, `dst`, and `event_id`
- no named object is created
- better when you want to see or control the exact pipe pair explicitly

`SEvent` / `DEvent`:

- create reusable named objects
- can be passed around and documented as part of a buffering protocol
- are usually easier to read for structured ready/valid logic

Practical rule:

- one-off or highly explicit pipe flags -> `setflag` / `waitflag`
- reusable synchronization protocol -> `SEvent` / `DEvent`

## 5. `SEvent`

### `SEvent(src_pipe, dst_pipe, preset=False, name="")`

- Purpose: create a single local event between two pipes.
- Typical use:
  - order a producer pipe and a consumer pipe on the same side
  - manually model one ready token between two pipeline stages

Unlike `CvMutex` / `VcMutex`, an event is not a cube/vec ownership object. It is a local pipe-to-pipe synchronization object keyed by:

- `src_pipe`
- `dst_pipe`
- `name`

### Parameters

- `src_pipe`:
  - producer pipe
  - must be a `PipeType`
- `dst_pipe`:
  - consumer pipe
  - must be a `PipeType`
- `preset`:
  - whether the event starts signaled
  - useful when the first consumer iteration should pass immediately
- `name`:
  - optional explicit event name
  - if empty, the runtime auto-generates `_tmp_sevent_*`

### Constructor behavior

- validates `src_pipe`, `dst_pipe`, `preset`, and `name`
- allocates a unique name if needed
- emits `create_sevent`
- if `preset=True`, current simulator seeds the event as initially available

### Methods

#### `set()`

- Emits: `event_set`
- Meaning:
  - producer signals the event once

#### `wait()`

- Emits: `event_wait`
- Meaning:
  - consumer waits until the event is signaled
  - current simulator then consumes the signal immediately

#### `setall()`

- Emits: `event_setall`
- Backend meaning:
  - on `SEvent`, this is the same as `set()`
- Current simulator:
  - treated the same as `event_set`

#### `release()`

- Emits: `event_release`
- Backend meaning:
  - `SEvent.release()` drains the outstanding signal by internally doing `wait()`
- Current simulator:
  - directly clears the local token to `False`

### Runtime mechanism

The current simulator stores one local boolean token per event key, per execution entity (one cube core instance or one vec sub-block instance):

```python
("event", str(src_pipe), str(dst_pipe), name)
```

Behavior:

- `create_sevent(..., preset=False)` -> token starts as `False`
- `create_sevent(..., preset=True)` -> token starts as `True`
- `set()` / `setall()` -> token becomes `True`
- `wait()` -> blocks until token is `True`, then consumes it to `False`
- `release()` -> forces token to `False`

So the simulator models `SEvent` as a one-token latch.

### Example: manual `MTE2 -> V` handoff

```python
ready = SEvent(Pipe.MTE2, Pipe.V, name="ub_ready")

gm_to_ub_pad(ub_tile, x[m:m + blk_m, k:k + blk_k], ...)
ready.set()           # issued on the producer side

ready.wait()          # the V pipe blocks until the MTE2-side set arrives
add(ub_out, ub_tile, 1.0)
```

Why this works even though the code is written sequentially:

- `gm_to_ub_pad(...)` and `ready.set()` lower onto the producer-side pipe sequence
- `ready.wait()` lowers onto the consumer-side pipe sequence
- the event prevents the consumer pipe from running ahead of the producer pipe

### Example: one-buffer ready/valid pair

```python
valid = SEvent(Pipe.MTE2, Pipe.V, preset=False, name="ub_valid")
ready = SEvent(Pipe.V, Pipe.MTE2, preset=True, name="ub_ready")

for tile in range(tile_num):
    ready.wait()                             # MTE2 may reuse the buffer immediately on tile 0
    gm_to_ub_pad(ubuf, x[..., tile], ...)
    valid.set()                             # producer publishes fresh data

    valid.wait()                            # V waits for fresh data
    add(ubout, ubuf, 1.0)
    ready.set()                             # consumer returns the one shared buffer
```

Why `preset=True` is on `ready`:

- before the first iteration, the single shared buffer is already reusable
- later iterations must wait for the previous consumer to return it

## 6. `DEvent`

### `DEvent(src_pipe, dst_pipe, preset=False, name="")`

- Purpose: create a double local event with alternating internal event ids.
- Typical use:
  - double-buffer or ping-pong pipe synchronization
  - loops where the producer and consumer alternate across two logical phases

The public Python API matches `SEvent`, but the backend object is different.

### Parameters

- same meanings as `SEvent`

### Constructor behavior

- validates arguments
- allocates a unique name if needed
- emits `create_devent`
- if `preset=True`, current simulator seeds the event as initially available

### Backend mechanism

In the generated backend helper class:

- `DEvent` allocates two event ids
- `set()` alternates between `id1` and `id2`
- `wait()` alternates between `id1` and `id2`
- `setall()` performs two `set()` calls, so both internal ids become available
- `release()` drains any outstanding `set()` calls by issuing matching `wait()` calls until the internal counts are balanced

This alternating behavior is what makes `DEvent` a natural match for double-buffered staging.

### Current simulator behavior

The current simulator intentionally uses a simpler model:

- it stores one boolean token per event key, just like `SEvent`
- `set()` and `setall()` both set that token to `True`
- `wait()` consumes it back to `False`
- `release()` also clears it to `False`

So today:

- the backend distinguishes `SEvent` vs `DEvent` at runtime
- trace seeding also distinguishes them when `preset=True`
- the simulator does not fully model the alternating two-id behavior

In traces, preset `DEvent` seeds `2` tokens, while preset `SEvent` seeds `1`. That matches the intended backend notion of a double event even though the runtime token store is simplified.

### Example: DBuff-style ready/valid pair

```python
valid = DEvent(Pipe.MTE2, Pipe.V, preset=False, name="dbuf_valid")
ready = DEvent(Pipe.V, Pipe.MTE2, preset=True, name="dbuf_ready")

for cnt in range(2):
    ready.wait()                              # wait for slot cnt to become reusable
    gm_to_ub_pad(ubuf[cnt], x[..., cnt], ...)
    valid.set()                              # publish slot cnt

    valid.wait()                             # consume slot cnt on the V side
    add(ubout[cnt], ubuf[cnt], 1.0)
    ready.set()                              # return slot cnt
```

The intended backend mental model is:

- slot `0` uses internal event `id1`
- slot `1` uses internal event `id2`
- the next loop iteration wraps around and reuses `id1`

That is the generated backend behavior. The current simulator only approximates it as a single token stream, so do not rely on simulator-only observations to distinguish the two internal event ids.

## 7. Relationship to `auto_sync()`

`auto_sync()` does not use `CvMutex` or `VcMutex`.

Instead, the autosync pass inserts local events:

- `SEvent` for single-buffer paths
- `DEvent` for multi-buffer paths

It usually creates two event streams per buffer family:

- `*_valid_*`
- `*_ready_*`

That is why lowered IR and traces often contain names such as:

- `_tmp_sevent_valid_...`
- `_tmp_sevent_ready_...`
- `_tmp_devent_valid_...`
- `_tmp_devent_ready_...`

Practical rule:

- same-side pipe staging -> prefer `auto_sync()` or explicit events
- cross cube/vec ownership -> use `CvMutex` or `VcMutex`

## 8. Choosing the Right Primitive

Use `CvMutex` when:

- cube produces
- vec consumes
- each vec lane must independently acknowledge slot release

Use `VcMutex` when:

- vec produces
- cube consumes
- cube must wait for all vec lanes before continuing

Use `SEvent` when:

- you need one local ready token between two pipes
- a single-phase handshake is enough

Use `DEvent` when:

- the same local synchronization edge naturally alternates between two phases
- you are reasoning in ping-pong or DBuff/TBuff terms

Use raw cross-side ops when:

- you want direct control over `cube_ready` / `wait_cube` / `vec_ready` / `wait_vec`
- the pattern does not benefit from packaging itself as a mutex object

Use all-core ops when:

- every cube core or every global vec participant must rendezvous before continuing
- you need a reusable collective barrier keyed by one `flag_id`

Use `setflag` / `waitflag` when:

- you want an explicit local flag keyed by `src`, `dst`, and `event_id`
- you do not need a named `SEvent` / `DEvent` object
- you need main-loop waiting with `dst=Pipe.S`

## 9. Common Pitfalls

- Do not replace cross-side ownership with `SEvent` / `DEvent`. Events are local pipe-ordering tools, not cube/vec ownership tools.
- Do not read `cube_ready` / `wait_cube` as "cube waits for cube". They are side-named APIs, not same-side APIs: `cube_ready` publishes from cube, `wait_cube` waits on vec.
- Do not read `allcube_*` as wrappers around `cube_ready` / `wait_vec`. They use a separate collective counter model.
- Do not confuse `setflag` / `waitflag` with cross-side sync. They use a local flag store, not the cross-side token store.
- Do not use `Pipe.S` as the `setflag` source. The API rejects it because `S` is the scheduler loop, not a producer pipe.
- Do not use `Pipe.ALL` with `setflag` / `waitflag`. `Pipe.ALL` is only meaningful for barrier-style operations.
- Do not read `depth` as a simulator-enforced token count. In current Python runtime behavior it is descriptive metadata, not the active counter.
- Do not assume `DEvent` simulator behavior is a perfect model of the generated backend's two-id alternation. It is intentionally simpler.
- When `flag_id` collisions happen, the kernel build fails early because duplicate cross-side mutex ids are rejected.

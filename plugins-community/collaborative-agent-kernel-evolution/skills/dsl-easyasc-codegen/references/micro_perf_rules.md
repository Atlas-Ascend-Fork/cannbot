# Micro-level perf rules (a5 VF kernels)

Generalized optimization methodology for a5 reg/micro kernels. Apply **after** correctness
passes, when tuning a `@vf`. These rules are about removing pipeline bubbles and instruction
count — not tiling. They assume you are already inside a `@vf` / `__VEC_SCOPE__`.

---

## 1. PipeBarrier elimination (usually the biggest single lever)

A `PipeBarrier` is only needed across a **true hazard on different pipes**. Codegen and the
in-order issue of a single pipe already order many dependencies, so explicit barriers between
them are dead weight that drains the pipeline. These typically need **no** explicit barrier:

| Situation | Why no barrier |
|---|---|
| V→V on the same buffer, read-after-write | same pipe issues in order, RAW preserved |
| V→V on independent buffers | no hazard |
| Two consecutive `@vf` in one scope, UB write→read | the scope serializes the UB write/read |
| Ops within a single sort/gather dispatch | ordered by the dispatch itself |

Cross-pipe hazards (MTE2↔V, V↔MTE3, V↔Cube) generally **do** need a barrier and must stay.

**Method**: start by removing every same-pipe (V→V) barrier, then re-run smoke and the
bit-exact check; add back only the ones whose removal breaks correctness. Do this before
reaching for algorithmic changes — bubble removal is cheap and often decisive.

---

## 2. Instruction / dispatch cost awareness

- **HW sort has a fixed dispatch floor.** The merge/sort dispatch costs roughly the same
  regardless of data size, so on small problems it can dominate. Weigh it against a non-sort
  route (§4).
- **Gather is comparatively expensive.** Count gathers per core and treat each as a real cost;
  eliminating gathers (e.g. by a bit-pattern reinterpret instead of a table lookup) is a direct win.
- **Bit-pattern reinterpret / shift is nearly free** compared to a gather or a value cast.
  Prefer it for exponent/sign reshuffles.
- **Derive counts algebraically** instead of computing each one — when a relation between
  counts exists, one reduction plus arithmetic replaces several reduction+cast+barrier chains.
- **Minimize incidental writes** — e.g. for unaligned-neighbor windows only the boundary
  sentinels are ever read; don't initialize interior pad slots.

---

## 3. Reading the profiler

Profile a single core (see `a5_simulator.md` for the cannsim / `msprof op simulator`
invocations), then read the per-instruction CSV and the per-pipe breakdown. Look at, qualitatively:
- **Overall wall proxy** (total tick / busy cycles) — your headline number across iterations.
- **Per-pipe split**: load (MTE2), store (MTE3), sort/gather dispatch, and vector compute.
  Identify the *dominant* pipe — that is what an optimization must target to matter.
- **Per-instruction counts** for the ops you tried to remove (gathers, shifts, reductions) —
  confirm a refactor actually eliminated them rather than just moving them.
- **Fixed head overhead** (load+store of a small input) is not optimizable on a single small
  op; amortize it by batching more work per launch.

---

## 4. Algorithm-selection decision tree

For data-dependent ops the *algorithm* usually dominates more than micro-tuning. Reason about
the route qualitatively before micro-optimizing:

1. **If the output is small and HW sort can be avoided**, a binary-search or merge route often
   beats sort because it has no sort-dispatch floor.
2. **Tune barriers before switching algorithms** — a route that looks slower can win after its
   redundant barriers are removed. Compare routes only after both are barrier-tuned.
3. **Go multi-core last.** Get single-core correctness and a clean single-core profile first,
   then shard by an independent dimension (e.g. batch, or row-tile — one unit of work per vec
   core). Multi-core multiplies throughput but won't fix a bad per-core algorithm.

---

## 5. Multi-core sharding & tiling (construction side)

When a single core is the bottleneck and an independent dimension exists, shard across cores.
The recurring methodology:

- **Block-dim formula**: `used_cores = min(CeilDiv(total_work, per_core_work), core_num)`. Pick
  `per_core_work` so each core does a meaningful chunk; don't blindly use all cores for tiny work.
- **Tail-core remainder**: when the dimension isn't divisible, the last core takes the leftover:
  `tail = total - (used_cores - 1) * norm_per_core`. In-kernel, branch on
  `GetVecIdx() == used_cores - 1` (and skip cores `>= used_cores`).
- **Fairer balancing** (optional): give the first `total_work % used_cores` cores one extra
  round, so no single tail core stalls the launch.
- **Tiling fields**: the tiling struct should carry the static bounds (UB size, core count) plus
  the per-core/per-tile counts the kernel reads; a tiling key selects the code path when there
  are multiple strategies.
- **Workspace per core**: when cores write GM scratch, give each its own slice
  (`ws_base + idx * per_core_ws`); size workspace by core count × max intermediate.

## 6. Building correct synchronization (the complement to §1)

§1 is about *removing* redundant barriers. This is about *adding* the right ones for a
throughput pipeline. The recurring discipline:

- **Allocate one `setflag`/`waitflag` event per producer→consumer direction**, not one per pipe.
  A `MTE2→V→MTE3` pipeline needs distinct events for `MTE2→V`, `V→MTE3` (and `MTE3→MTE2` if
  reusing buffers) so the stages overlap instead of serializing.
- **Reuse events cyclically across loop iterations** with ping-pong indexing (`event[i % 2]`) so
  a fixed small event pool drives an unbounded loop.
- **Two deadlock-avoidance rules**: (1) the producing `setflag` must precede the consuming
  `waitflag`; (2) after a format-changing op (cast / layout change), insert a vector barrier
  before the same tensor is re-read with a different dtype.
- **Vector→scalar hand-off**: when a scalar is read back from a vector result (e.g. a reduced
  value), barrier + a `V→S` event before the scalar read — otherwise the read races the compute
  and returns stale data.

## 7. Cube↔Vec fusion (a5)

For fused cube+vec ops, AIC and AIV coordinate through **GM/workspace + a cross-core handshake**,
not shared registers:

- AIC writes its matmul tile to workspace, signals (`cube_ready` / `allcube_ready`), AIV waits
  (`wait_cube` / `allcube_wait`), reads the tile, applies the vec post-op, writes out.
- Use a 1-or-2-deep handshake so AIV consumes a tile before AIC overwrites it (ping-pong the
  workspace for overlap). `CvMutex` / `VcMutex` guard the shared region.
- Get single-core (or single-side) correctness first; add the cross-core handshake last.

---

## 8. Optimization workflow (apply in order)

1. Get bit-exact correctness on the **largest** representative shape (see the UB-overflow rule
   in `error_recipes.md` — passing on a small shape does not guarantee large shapes are safe).
2. Cut redundant PipeBarriers (§1); re-verify bit-exact after each cut.
3. Remove gathers / derive counts / reinterpret instead of cast (§2).
4. Profile (§3); identify the dominant pipe.
5. If dominated by a fixed dispatch floor, reconsider the algorithm (§4).
6. If a stage stalls the pipeline, build the per-direction event pipeline (§6).
7. If dominated by head overhead and an independent dimension exists, shard multi-core (§5);
   for fused cube+vec, add the cross-core handshake (§7).
8. Keep a short change log (what changed, did wall time / barrier count drop) so the next
   similar kernel can reuse the path rather than rediscovering it.

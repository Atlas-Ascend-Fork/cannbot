# SIMT Warp Operations Reference

> **Applies to**: All SIMT models (A, B, C) — these patterns are model-agnostic.
> **Back to**: [`../SKILL.md`](../SKILL.md)

---

**1.6 Warp Reduction Pattern**

When the baseline specifies a warp reduction (topk, argmax, histogram), emit the butterfly `asc_shfl_down` pattern. This reduces 32 lanes to lane 0 in 5 steps.

```cpp
#include "simt_api/device_warp_functions.h"

// Inside __simt_vf__ function:
// After each thread computes local_max / local_max_idx...

// Butterfly warp reduction — 5 steps
for (uint32_t offset = 16; offset >= 1; offset >>= 1) {
    float other_val = asc_shfl_down(local_max, offset);
    uint32_t other_idx = (uint32_t)asc_shfl_down((float)local_max_idx, offset);
    if (other_val > local_max ||
        (other_val == local_max && other_idx < local_max_idx)) {
        local_max = other_val;
        local_max_idx = other_idx;
    }
}
// After this: lane 0 of each warp holds the warp-wide max + index
```

Rules:
- `asc_shfl_down(var, offset)` works on `float` and `uint32_t` (verified on A950)
- For non-float types (e.g., index), cast to float for the shuffle, cast back after
- The butterfly offsets are always 16, 8, 4, 2, 1 (for warp size 32)
- After the butterfly, only lane 0 (`threadIdx.x % 32 == 0`) holds the correct argmax result (the butterfly narrows to lane 0)
- **Note**: The native `asc_reduce_add()` alternative (§1.14) broadcasts to ALL lanes, unlike the butterfly. Use butterfly only when you need both value AND index (argmax)

---

**1.14 `asc_reduce_add()` — Simpler Alternative to Butterfly**

When only the warp-wide sum is needed (no index tracking), use `asc_reduce_add()` instead of the 5-step `asc_shfl_down` butterfly.

Source: SDK example `memory_fence.asc`.

```cpp
// Simple warp sum — single call replaces 5-step butterfly
float warp_sum = asc_reduce_add(val);  // result broadcasts to ALL 32 lanes (not just lane 0)

// Also available:
float warp_max = asc_reduce_max(val);
float warp_min = asc_reduce_min(val);
```

The reduced value is available in **every lane**, not just lane 0. The leader-only atomic pattern (`if (lane == 0) atomic(...)`) is correct because we want ONE atomic per warp, not because only lane 0 has the result.

Use the butterfly pattern (`asc_shfl_down`) when you need BOTH value AND index (e.g., argmax: need to track which lane had the max).

---

**1.20 Warp Reduction — Native REDUX (Ascend950PR verified)**

`Simt::WarpReduceAddSync<T>(val)` / `asc_reduce_add(val)` lowers to a single `SIMT_REDUX` instruction (16 cycles). This is 5.3x faster than the 5-step `asc_shfl_down` butterfly (5 x 17 = 85 cycles).

- **Result broadcasts to ALL 32 lanes** (verified T1-sim) — not just lane 0
- Supported types: `{int32, uint32, half, float}` (header-declared)
- The leader-only atomic pattern is needed because we want 1 atomic/warp, NOT because only lane 0 has the value
- `int32` reduction is bit-exact (associative); `float` reduction is NOT bit-exact (non-associative, measured abs_diff 4088 @1e8)
- Warp collective MUST be called unconditionally — calling inside `if (tid < n)` divergent branch is undefined behavior

Reference: `ascend950pr_isa_probes/simt.reduce.warp-sum.md`

---

**1.21 Shuffle Edge-Lane Behavior (Ascend950PR verified)**

`WarpShflUpSync(v, delta, width)` / `WarpShflDownSync(v, delta, width)` — edge lanes that would read out-of-range **keep their OWN value** (not zero).

- `ShflUp(v, 1, 32)`: lane 0 keeps its own value; lanes 1-31 get lane-1's value
- `ShflDown(v, 1, 32)`: lane 31 keeps its own value; lanes 0-30 get lane+1's value
- Host reference must mirror this edge behavior or verification will fail
- `SIMT_SHFL` dependent cadence: 17 cycles per call; no memory traffic

Reference: `ascend950pr_isa_probes/simt.shuffle.md`

---

**1.22 Vote/Ballot Semantics (Ascend950PR verified)**

| Function | Returns | Example (13/32 lanes true) |
|---|---|---|
| `WarpBallotSync(pred)` / `asc_ballot(pred)` | `uint32_t` mask, bit i = lane i | `0x1fff` |
| `WarpAllSync(pred)` / `asc_all(pred)` | 1 iff ALL 32 lanes non-zero | `0` |
| `WarpAnySync(pred)` / `asc_any(pred)` | 1 iff ANY lane non-zero | `1` |
| `WarpActiveMask()` / `asc_activemask()` | Mask of active lanes | `0xFFFFFFFF` (full warp) |

- No mask argument (unlike CUDA `__*_sync(mask, pred)`) — whole-warp implicit
- Result broadcasts to ALL lanes (every lane reads the same value)
- Must be called from convergent (non-divergent) control flow

Reference: `ascend950pr_isa_probes/simt.vote.md`

---

> **ISA verification data**: [`ascend950pr_isa_probes/simt.reduce.warp-sum.md`](ascend950pr_isa_probes/simt.reduce.warp-sum.md), [`ascend950pr_isa_probes/simt.shuffle.md`](ascend950pr_isa_probes/simt.shuffle.md), [`ascend950pr_isa_probes/simt.vote.md`](ascend950pr_isa_probes/simt.vote.md)

```
ID:        0393-the-state-region-ub-budget-is-the-whole-local-state-matrix-unless-a-core-reads-only-its-own-segment
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice). Upstream gives three UB
           sizing formulas and one qualitative reduction rule with no formula. Nothing was compiled and
           no UB was reserved.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/tiling-scheme/window-memory-layout.md:180-193
           — "## 状态区相关 UB 大小 / ```c++ / // 写单个状态 slot（SetRemoteStatus 使用） / stateWriteBuf
           = STATE_SLOT_INT32 * sizeof(int32_t)  = 32B / // 读全量本地状态区（WaitRemoteStatus 使用） /
           stateReadBuf   = localExpertNum * rankDim * STATE_SLOT_INT32 * sizeof(int32_t) /
           // 重置全量本地状态区（ClearLocalStatus 使用） / stateResetBuf  = localExpertNum * rankDim *
           STATE_SLOT_INT32 * sizeof(int32_t) / ``` / 多核后等待阶段只读自己负责的状态段时，
           `stateReadBuf` 大小可相应缩减为“本核负责段大小”。"
SOURCE:    same file:82-83 — the same product as the region size: "totalStateElems = localExpertNum *
           rankDim * STATE_SLOT_INT32 / totalStateBytes = localExpertNum * rankDim * STATE_SLOT_BYTES"
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/api-rules/mte-address-access.md:365
           — "6. **读取本地状态区必须走 GM 可见路径**：不能在 `SyncAll` 后直接 `GetValue()` 读取共享状态，
           必须先搬回 UB 再读取。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an MC² dispatch kernel that polls the local state region correctly without staging the whole
           matrix into UB and without a per-core segmentation — for instance by staging one slot per poll
           — which would make the full-matrix read buffer an artefact of one implementation rather than
           a requirement of the read rule.
```

# 0393 · The state-region UB budget is the whole local state matrix, unless a core reads only its own segment

## 1 · Claim
Upstream asserts three UB sizing formulas for the dispatch state protocol. Writing a single remote status
slot needs `STATE_SLOT_INT32 * sizeof(int32_t)` = 32 bytes. Reading the **full** local state region needs
`localExpertNum * rankDim * STATE_SLOT_INT32 * sizeof(int32_t)`. Resetting the full local state region
needs the same. Upstream asserts one reduction: when a multi-core wait phase reads only the state segment
its own core is responsible for, the read buffer may be reduced 相应 — correspondingly — to "the size of
this core's segment". Upstream asserts, in a sibling file, that reading the local state region must go
through a GM-visible path, staged into UB, and never through a direct `GetValue()` after `SyncAll()`. Not
established here: nothing was compiled and no UB was reserved.

The read and reset buffers are the same expression as `totalStateBytes`, the region's own size — so the
staging buffer is a full mirror of the region in UB.

## 2 · The wrong branch this removes
The UB cost of a synchronisation protocol is not where anyone looks for a UB cost, and this one scales with
the communication domain rather than with the tile.

**The number is not small and it is not tile-shaped.** `localExpertNum × rankDim × 32` bytes: at 8 local
experts and 16 ranks that is 4 KB; at 32 and 64 it is 64 KB. On a 248 KB UB (0209) with a DCache
reservation of at least 32 KB already owed (0237, 0377), 64 KB of state mirror is a quarter of the budget
consumed by bookkeeping before a single token is staged. An agent that sizes its tiling against
`ubSize − DCACHE` and forgets the state buffer over-commits, and the failure surfaces at the *largest*
communication domain — the configuration reached last, in production, after every smaller one passed.

**And it scales with the wrong quantity.** Every other UB consumer in this book's material scales with the
tile: bigger tensor, smaller tile, same UB. This one scales with `rankDim`. So the tiling search cannot
buy its way out by shrinking the tile — the state buffer is fixed by the topology, and past some rank count
there is no tile size that fits. Nothing in upstream's tiling material connects the two, and an agent
debugging "why does my tile have to be so small at 64 ranks" has no reason to look at the state protocol.

**The reduction is stated and not specified.** "只读自己负责的状态段时，`stateReadBuf` 大小可相应缩减为
'本核负责段大小'" names the optimisation and gives no partition. Which core is responsible for which
(localExpert, srcRank) pairs is a scheduling decision the document does not make, and the segment size
therefore has no formula — 相应缩减 is an instruction to divide by something unnamed. Two agents
implementing it will partition differently, and the partition determines both the buffer size and *which
core waits on which flag*, so a mismatch between the partition assumed by the writer of the wait loop and
the partition assumed by the tiling routine is a wait that never completes.

**The reset buffer is the quiet one.** `stateResetBuf` is the same full-matrix size and it exists because
`ClearLocalStatus` writes zeros back over the whole region between iterations. Upstream lists it as a UB
requirement and says nothing about whether the read buffer and the reset buffer can be the same allocation
— they have identical size and disjoint lifetimes within an iteration, so sharing is the obvious economy
and it is the kind of economy that turns into a correctness bug when the lifetimes overlap after all (a
reset that begins before the last read completes). Upstream neither permits nor forbids it.

**Why the mirror exists at all is the rule from the other file.** The state region lives in GM and the
direct read is forbidden (0391 §2, 0277), so *every* poll of a flag is a GM→UB copy. An implementation that
copies one slot per poll would need 32 bytes, not the whole matrix; upstream's `WaitRemoteStatus` copies
the lot. That is a plausible design — one bulk copy per wait iteration rather than `localExpertNum ×
rankDim` small ones — and it is a *choice*, presented as a sizing requirement. The OVERTURN is written
against exactly that: a kernel that polls slot-wise would need 32 bytes and would falsify the budget as a
requirement while leaving it true as a description of one implementation.

## 3 · Ground / Source
The three formulas and the reduction, `window-memory-layout.md:180-193`, in full:

> ## 状态区相关 UB 大小
>
> ```c++
> // 写单个状态 slot（SetRemoteStatus 使用）
> stateWriteBuf  = STATE_SLOT_INT32 * sizeof(int32_t)  = 32B
>
> // 读全量本地状态区（WaitRemoteStatus 使用）
> stateReadBuf   = localExpertNum * rankDim * STATE_SLOT_INT32 * sizeof(int32_t)
>
> // 重置全量本地状态区（ClearLocalStatus 使用）
> stateResetBuf  = localExpertNum * rankDim * STATE_SLOT_INT32 * sizeof(int32_t)
> ```
>
> 多核后等待阶段只读自己负责的状态段时，`stateReadBuf` 大小可相应缩减为“本核负责段大小”。

Three named users — `SetRemoteStatus`, `WaitRemoteStatus`, `ClearLocalStatus` — which
`mte-address-access.md:331-333` places in a fourth layer: "这一层把状态写入、状态等待、状态复位这些动作与
地址获取解耦" (this layer decouples status write, status wait and status reset from address acquisition).
So the three buffers are the three actions of that layer, one buffer each.

The identity with the region size, `:82-83`:

> ```c++
> totalStateElems    = localExpertNum * rankDim * STATE_SLOT_INT32
> totalStateBytes    = localExpertNum * rankDim * STATE_SLOT_BYTES
> ```

`stateReadBuf` is `totalStateElems * sizeof(int32_t)`, which is `totalStateBytes` — the same number written
two ways in one file. That the document derives the UB buffer from the element count and the region from
the byte count, rather than stating one in terms of the other, is the sort of near-duplication that drifts;
it has not drifted here and is recorded because a later revision of either line would silently break the
identity.

The read rule, `mte-address-access.md:365`, quoted in SOURCE — the reason a UB mirror exists at all.

What upstream does not supply: the per-core partition that would give the reduction a size; whether the
three buffers may share an allocation; whether `stateWriteBuf` is per-target-rank (a core writing to *n*
peers may need *n* write buffers, or may reuse one serially, and the document says neither); and any
statement connecting these buffers to the operator's tile budget, which is where they would have to be
subtracted.

`STATE_SLOT_INT32` and `rankDim` come from the dispatch state block (0391); `rankDim` is undefined in the
file and stands against the data region's `epWorldSize` (0390 §3, `C-950rem-011`) — so the state buffer's
size depends on a symbol whose identity with its neighbour is itself unresolved.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board with at least 2 cards. The budget is a host-side allocation fact and a
device-side scaling fact, and they separate.

Arm A — the reserved bytes, host-side. For an MC² dispatch operator, instrument the tiling routine to
report every UB reservation by purpose, and run at (localExpertNum, rankDim) of (2,2), (8,16) and the
largest reachable configuration. Record the state-related bytes against the formula. This needs one card
and no partner: the allocation is computed on the host.

Arm B — the budget collision. For each configuration in Arm A, record the tile size the tiling routine
selects, and repeat with the state buffers artificially zeroed. The difference is the tile the state
protocol costs. §2 claims this is invisible in current tiling documentation; the number is what would make
it visible.

Arm C — the reduction, implemented two ways. Implement the per-core segment reduction under two plausible
partitions — by `localExpert` and by `srcRank` — and record the buffer size and whether the wait completes
under each. If both complete, the partition is free and the reduction is a pure saving; if one hangs, the
partition is coupled to which core writes which flag and upstream's one-line reduction is hiding a
protocol decision.

Arm D — the slot-wise alternative, which is the OVERTURN. Implement `WaitRemoteStatus` copying **one slot**
per poll into a 32-byte buffer and confirm correctness over 500 iterations at the largest configuration.
Compare wait latency against the bulk-copy version. If it is correct, the full-matrix budget is one
implementation's choice; the latency comparison then says what that choice buys, which is the trade nobody
has priced.

Arm E — buffer sharing. Build a variant in which the read and reset buffers are one allocation and run the
full collective 500 times at the largest configuration. Upstream neither permits nor forbids it; a failure
would locate the lifetime overlap §2 suspects, and a clean run at 500 iterations is reported as
`not provoked` rather than as permission.

Device selection: Arm A needs one card; the rest are multi-card. The operator names every card in the
group, the harness prints them back with `compiler/version.info` and each resolved SoC string, occupancy is
checked on all of them before the run (shared machine, ≤4 dies), and no card is substituted between arms.
Arms C, D and E can hang on a state wait: a declared watchdog timeout and card release are mandatory.

## 5 · Checker — acceptance declared before the run
`state_ub_bytes` (Arm A) — reserved state-related UB, per configuration. Pass iff it equals
`localExpertNum * rankDim * 32` plus 32 for the write buffer plus the reset buffer, i.e. iff the three
formulas are what the implementation reserves. A smaller value means the implementation already applies a
reduction the document presents as optional.

`tile_cost_of_state` (Arm B) — the tile-size difference with and without the state reservation, per
configuration. Reported per configuration and never averaged: the whole claim is that it grows with
`rankDim`, and one number across three configurations would erase the growth.

`reduction_partition_outcome` (Arm C) — per partition, the buffer size and three-valued completion:
completes, hangs, completes with wrong data. Reported as a table.

`slotwise_correct` and `slotwise_latency_ratio` (Arm D) — a boolean and a ratio, reported together. The
boolean is the OVERTURN test; the ratio is the price of the bulk copy and is meaningless without the
boolean beside it.

`shared_buffer_survives` (Arm E) — reported as `clean over N iterations` or the failing iteration, never as
"safe". A clean run does not establish that overlapping lifetimes cannot occur; it establishes that they
did not, at this configuration, in this many iterations.

The positive fixture, declared before the run: Arm A must include a configuration in which the state buffer
is **large enough to force a smaller tile** — otherwise the reservation is absorbed by slack and
`tile_cost_of_state` is zero for reasons unrelated to the claim. If no reachable configuration forces it,
that itself is the finding and must be reported rather than presented as "the cost is negligible". And Arm
D's slot-wise variant must be shown to *detect* a missing flag: run it once against a partner that never
sets ready, and confirm it times out rather than proceeding. A wait loop that never blocks is trivially
"correct" and would pass Arm D while establishing nothing — the known blind species, and the one this arm
is most exposed to.

Process exit codes are not the verdict for any arm: a watchdog kill is an expected outcome in Arms C, D
and E.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No tiling routine was instrumented,
no UB reserved, no wait loop run, no card contacted. The quoted passages are re-verified file reads of the
upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that any implementation reserves these buffers,
that the reservation costs tile size, or that the reduction is safe — Arms A through E are all open, and
upstream supplies **formulas and no measurement**.

**It does not establish the per-core segment size.** Upstream's reduction says 相应缩减 and names no
partition; which core is responsible for which (localExpert, srcRank) pairs is a scheduling decision no
source in scope makes, so the reduced buffer has no formula and this entry does not invent one.

It does not establish that the full-matrix read buffer is *required*. §2 argues it is one implementation's
choice — a bulk copy per wait iteration rather than slot-wise polling — and Arm D is written as the
OVERTURN precisely because the slot-wise alternative would need 32 bytes. Reading this entry as "MC² needs
64 KB of UB for state" would overstate it.

It does not establish whether the three buffers may share an allocation, whether `stateWriteBuf` is
per-target-rank, or how any of them interacts with the operator's tile budget — the last being the
consequence §2 cares about and the one no document in scope computes.

It does not establish `rankDim`'s identity. The buffer size depends on it, the data region is sized by
`epWorldSize`, and whether those are one quantity is `C-950rem-011` and is open (0390 §3). A state buffer
sized by the wrong one of the two is wrong by their ratio.

It says nothing about the combine side, whose state region has its own arrangement and slot structure
(0392) and for which this file gives **no** UB sizing at all — an asymmetry worth noting and not claimed.

It says nothing about the mechanism behind the GM-visible-path rule that makes the mirror necessary; 0391
§7 and 0277 §7 record the same gap.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board was
contacted.

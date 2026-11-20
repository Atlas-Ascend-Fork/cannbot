```
ID:        0391-the-dispatch-state-slot-is-thirty-two-bytes-of-which-two-words-carry-meaning
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice). Upstream gives the slot
           format and the arithmetic and no measurement; it states the padding's purpose as alignment
           and names no mechanism that requires it. Nothing was compiled and no flag was polled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/tiling-scheme/window-memory-layout.md:58-72
           — "### 布局规则 / ``` / 排布维度：localExpert → sourceRank → stateSlot / ``` / 每个 stateSlot
           = 32B（8 × int32_t）。 / ### Slot 格式 / ``` / slot[0] = flag         (0=未就绪, 1=就绪) /
           slot[1] = tokenCount   (该 srcRank → localExpert 的实际发送 token 数) / slot[2..7] = padding
           (仅用于 32B 对齐) / ```"
SOURCE:    same file:74-84 — "### 相关常量 / ```c++ / STATE_SLOT_INT32   = 8                   //
           每 slot 8 个 int32_t / STATE_SLOT_BYTES   = 32                  // = 8 * 4 /
           STATE_READY_OFFSET = 0                   // flag 在 slot 中的下标 / STATE_TOKEN_OFFSET = 1
           // tokenCount 在 slot 中的下标 / totalStateElems    = localExpertNum * rankDim *
           STATE_SLOT_INT32 / totalStateBytes    = localExpertNum * rankDim * STATE_SLOT_BYTES / ```"
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/api-rules/mte-address-access.md:365
           — "6. **读取本地状态区必须走 GM 可见路径**：不能在 `SyncAll` 后直接 `GetValue()` 读取共享状态，
           必须先搬回 UB 再读取。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a dispatch state slot on a 950 board whose ready flag is not at word 0, or whose token count is
           not at word 1, or whose stride is not 32 bytes — observable by writing distinctive values from
           a partner rank and dumping one slot. Separately: a 32-byte slot whose flag and count are read
           correctly with a 8-byte stride would show the padding is not load-bearing for addressing.
```

# 0391 · The dispatch state slot is thirty-two bytes, of which two words carry meaning

## 1 · Claim
Upstream asserts the dispatch state region's layout: the arrangement dimensions are localExpert →
sourceRank → stateSlot, and each state slot is 32 bytes, eight `int32_t` values. Upstream asserts the slot
format: word 0 is a ready flag with 0 meaning not-ready and 1 meaning ready; word 1 is the actual number
of tokens sent for that (srcRank → localExpert) pair; words 2 through 7 are padding, 仅用于 32B 对齐 —
solely for 32-byte alignment. Upstream asserts four named constants — `STATE_SLOT_INT32` = 8,
`STATE_SLOT_BYTES` = 32, `STATE_READY_OFFSET` = 0, `STATE_TOKEN_OFFSET` = 1 — and two totals,
`totalStateElems` and `totalStateBytes`, each the product of `localExpertNum`, `rankDim` and the per-slot
size. Upstream asserts, in a sibling file, that reading the local state region must go through a
GM-visible path — staged back into UB — and never through a direct `GetValue()` after `SyncAll()`. Not
established here: nothing was compiled and no flag was polled.

## 2 · The wrong branch this removes
A 32-byte slot holding 8 bytes of information looks like waste, and the three natural economies are all
wrong.

**Packing the slots.** Two `int32` values need 8 bytes; an agent that sizes the state region at
`localExpertNum * rankDim * 8` saves 75% of it and produces a region whose slot *k* sits where the partner
rank's slot *k/4* is. The writer and the reader disagree about the stride, and the reader polls a word
that is another pair's flag. The failure is a wait that never completes, or one that completes on the wrong
pair's readiness and proceeds to read tokens that have not arrived — a hang or corruption, both
attributable to anything.

**Treating the padding as free space.** Six unused words per slot is an inviting place to put a sequence
number, a checksum, or a second counter. Upstream states the padding's purpose as alignment, and the
alignment is not decorative: the flag is what a partner rank writes to signal readiness, so the slot is the
unit of a cross-rank write. A 32-byte-aligned, 32-byte-sized slot is exactly one aligned store, which is
what makes the flag write indivisible from the reader's point of view. Repurpose the padding and the write
either grows or is no longer a single aligned unit — and upstream does not say what the atomicity contract
is, so an agent cannot reason about whether it broke it. That is the reason the padding is claimed here as
part of the layout rather than as slack.

**Reading the flag directly.** The sibling file's item 6 forbids `GetValue()` after `SyncAll()` and
requires staging through UB. An agent that has a `SyncAll()` in hand has a barrier and will reason that the
barrier makes the value visible — the premise is right and the conclusion is wrong. This is the same shape
0277 §2 records for the same rule; here it applies to the specific word being polled, and the consequence
is that a wait loop reads a stale flag forever or reads a stale 0 and proceeds early. Upstream gives no
symptom, and the two failure directions are opposite.

**The dimension order is the fourth trap and it is easy to miss.** The state region is arranged
localExpert → sourceRank, and the *data* region is arranged sourceRank → localExpert (0390). The two are
transposed. So an agent that computes one index expression and reuses it for both regions addresses the
wrong slot whenever `localExpertNum ≠ rankDim`, and addresses the right one whenever they happen to be
equal — which is a plausible test configuration. The address formulas encode the difference correctly
(`(localExpert * rankDim + srcRank)` for state, `srcRank * sourceRankRegionBytes + localExpert *
expertRegionBytes` for data), and nothing in the file flags that the orders differ.

**And `tokenCount` is not a flag.** Word 1 carries a count, which means the reader learns *how many* tokens
arrived only after the flag says ready. An implementation that infers the count from a fixed `BS` rather
than reading word 1 works whenever every (srcRank, localExpert) pair sends a full batch and fails for the
ragged case that MoE dispatch exists to handle.

## 3 · Ground / Source
The layout and slot format, `window-memory-layout.md:56-72`:

> ## Dispatch 状态区布局
>
> ### 布局规则
>
> ```
> 排布维度：localExpert → sourceRank → stateSlot
> ```
>
> 每个 stateSlot = 32B（8 × int32_t）。
>
> ### Slot 格式
>
> ```
> slot[0] = flag         (0=未就绪, 1=就绪)
> slot[1] = tokenCount   (该 srcRank → localExpert 的实际发送 token 数)
> slot[2..7] = padding   (仅用于 32B 对齐)
> ```

The constants, `:74-84`, quoted in SOURCE. Note that `STATE_SLOT_INT32` and `STATE_SLOT_BYTES` are the same
quantity in two units, with the second annotated `// = 8 * 4` — so the file derives one from the other
rather than stating two independent literals, which is the better of the two habits and is worth recording
as such.

The two address expressions the constants feed, `:88-100`:

> ```c++
> GM_ADDR dstStateAddr =
>     GetBaseWindStateAddrByRankId(ctx, dstRank, curRankId)
>     + ((uint64_t)localExpert * rankDim + (uint64_t)srcRank) * STATE_SLOT_BYTES
> ```
>
> 等待阶段读取本地状态区：
>
> ```c++
> GM_ADDR localStateBase = GetStatusDataSpaceGm(ctx)
> // slot[localExpert][srcRank] 地址：
> localStateBase + (localExpert * rankDim + srcRank) * STATE_SLOT_BYTES
> ```

Two accessors for the same region depending on direction — the rank-parameterised one for writing to a
peer, `GetStatusDataSpaceGm` for reading locally — which is 0389's composition claim applied to the state
side. The index expression is identical in both, so the local and remote views agree on the layout.

The read rule, `mte-address-access.md:365`:

> 6. **读取本地状态区必须走 GM 可见路径**：不能在 `SyncAll` 后直接 `GetValue()` 读取共享状态，必须先搬回
>    UB 再读取。

必须 twice. No mechanism is given — whether the prohibition is about cache coherence, about a scalar unit
not seeing MTE-written GM, or about compiler caching of the load — and the three would need different
mitigations if the staged path were unavailable.

What upstream does not supply: any atomicity statement for the flag write; any statement of whether the
flag and the count are written together or separately (if separately, a reader that sees flag = 1 may read
a stale count, which is the classic publication race and nothing addresses it); any ordering rule between
the payload write and the flag write; and any statement of what resets the flags between iterations,
beyond naming a `ClearLocalStatus` user of the reset buffer at `:190`.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board with at least 2 cards.

Arm A — the slot, dumped. With a partner rank writing flag = 1 and tokenCount = 13 for a known
(localExpert, srcRank), dump 64 bytes from the computed slot address and record where the 1 and the 13
land, and what occupies words 2-7. Two slots' worth is dumped deliberately, so the stride is visible in the
same read.

Arm B — the stride and the dimension order. With `localExpertNum ≠ rankDim` (say 3 and 4), have the partner
write a distinct `tokenCount` for every (localExpert, srcRank) pair — value `100*localExpert + srcRank` —
and dump the whole state region. Reconstruct the mapping from the dump. This confirms both the 32-byte
stride and the localExpert-major order, and it is the arm that would catch a transposed index. Choosing
unequal dimensions is the point: with 4 and 4 the transposition is invisible.

Arm C — the read rule, tested in both directions. After a `SyncAll()`, read a flag two ways — direct
`GetValue()` and staged through UB — and compare, repeating 200 times at several rank counts. Upstream says
the direct read is invalid; a non-deterministic mismatch is the predicted signature, so a single comparison
would miss it. Report the mismatch count, not a boolean.

Arm D — the publication race §3 raises and no source addresses. Have the partner write tokenCount and flag
in that order, and have the reader, on seeing flag = 1, immediately read tokenCount. Repeat 500 times.
Record any run where the count is stale. If the two words can be observed out of order, every wait loop
written from this layout needs a fence the document does not mention.

Arm E — the padding's role. Build one variant with `STATE_SLOT_BYTES` = 8 (packed, flag and count only) and
one at 32, both writer and reader consistent, and compare correctness and the write's observed atomicity.
If the packed variant is correct, the padding is pure alignment overhead and can be stated as such; if it
is not, the 32-byte slot is load-bearing and the reason should be recorded, because upstream gives only
"for alignment".

Device selection is explicit and multi-card: the operator names every card in the group, the harness prints
them back with `compiler/version.info` and each resolved SoC string, occupancy is checked on all of them
before the run (shared machine, ≤4 dies), and no card is substituted between arms. Arms C, D and E can hang
on a state wait: a watchdog timeout and card release are declared before the run.

## 5 · Checker — acceptance declared before the run
`flag_word_index` and `count_word_index` (Arm A) — the observed word indices of the 1 and the 13. Pass iff
0 and 1. Two separate variables: a layout with the flag at 0 and the count elsewhere is a different defect
from a wholly different layout.

`slot_stride_bytes` (Arm A, B) — the observed slot-to-slot distance. Pass iff 32.

`dimension_order` (Arm B) — two-valued: localExpert-major or sourceRank-major. Pass iff localExpert-major.
Reported with the unequal dimensions used, so a later reader can see the arm could have distinguished them.

`direct_read_mismatches` (Arm C) — mismatch count out of 200, per rank count. Reported as a table.
**A clean set does not establish that the direct read is safe** and is reported as `not provoked`: upstream's
claim is about visibility semantics and a passing observation cannot refute an invalid-but-usually-working
access.

`stale_count_runs` (Arm D) — runs out of 500 in which flag = 1 was observed with a stale count. Reported.
Any non-zero value is a finding that upstream's layout document does not anticipate.

`packed_variant_correct` (Arm E) — true iff the 8-byte-slot variant is correct over the same protocol.
Reported, not gated.

The positive fixture, declared before the run: Arm A's written values must be **13 and 1 in that order**,
and the arm must also dump a slot the partner did **not** write, which must hold the pre-run poison. If the
unwritten slot also holds 1 and 13, the dump is not addressing what it thinks it is — or the whole region
was written — and every index in the arm is void. And Arm C's staged read must be shown to return the
correct value at least once; if neither read path ever returns the written flag, the comparison is between
two broken reads and its agreement means nothing. Without both, the checker reads only "the expected values
appeared somewhere", which is the known blind species and is especially easy in a state region full of
small integers.

Process exit codes are not the verdict for any arm: a hang is a predicted outcome in Arms C, D and E.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no flag
written or polled, no state region dumped, and no card was contacted. The quoted passages are re-verified
file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the slot size, the field positions, the dimension
order, or that the direct read is unsafe — Arms A through E are all open, and upstream supplies **the
format and no measurement**.

**It establishes no atomicity or ordering property.** Whether a 32-byte slot write is indivisible, whether
the flag and count can be observed out of order, and whether the payload write is ordered before the flag
write are all unstated by every source in scope. §2's argument that the padding makes the flag write a
single aligned store is reasoning about why the layout might be as it is, not a statement about the
hardware, and Arms D and E are where it would be tested.

It does not establish the mechanism behind the GM-visible-path rule. Upstream forbids `GetValue()` after
`SyncAll()` and names no reason; cache coherence, scalar-versus-MTE visibility and compiler load caching
would each explain it and would need different mitigations if UB staging were unavailable. 0277 §7 records
the same gap for the same rule.

It does not establish what resets the flags between iterations. `:190` names a `ClearLocalStatus` user of a
reset buffer sized to the whole local state matrix (0393); the reset's timing, its ordering against the next
iteration's writes, and whether a partner can write a flag before the local reset completes are unaddressed.

It says nothing about the combine state region, which the same file gives a different slot structure and a
different arrangement (0392), nor about `rankDim`'s relationship to the data region's `epWorldSize`
(0390 §3, `C-950rem-011`).

It says nothing about the address the slot is computed from — that is 0389's composition claim — nor about
the 1 MB state-region base, which is 0277's.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board was
contacted.

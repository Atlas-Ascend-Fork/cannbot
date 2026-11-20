```
ID:        0389-the-window-layout-formulas-start-from-an-accessor-that-has-already-applied-the-one-megabyte-skip
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice), which states the two halves
           of the address computation in two of its own files and never states how they compose.
           Nothing was compiled and no window was read. This entry supplies the remaining terms of the address
           computation 950:0277 §7 leaves open; the COMPOSITION is an inference, not established.
BOARD:     family-claimed(unverified)
           # upstream scopes the A5 half by compile macro (`__NPU_ARCH__ == 3510`) rather than by board
           # token, and no board was contacted.
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/tiling-scheme/window-memory-layout.md:36-42
           — "GM_ADDR dstDataAddr = / GetBaseWindAddrByRankId(ctx, dstRank, curRankId) / + (uint64_t)
           srcRank    * sourceRankRegionBytes / + (uint64_t)localExpert * expertRegionBytes / +
           (uint64_t)dstSlot    * commTokenBytes"
SOURCE:    same file:88-92 — "GM_ADDR dstStateAddr = / GetBaseWindStateAddrByRankId(ctx, dstRank,
           curRankId) / + ((uint64_t)localExpert * rankDim + (uint64_t)srcRank) * STATE_SLOT_BYTES"
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/api-rules/mte-address-access.md:283
           — "sample 的 `GetStatusDataSpaceGm`、`GetBaseWindAddrByRankId`、`GetBaseWindStateAddrByRankId`
           属于这一层。这里对应的是“数据区基址”和“状态区基址”分开封装，而不是在主流程里反复手写平台分支。"
           and `:271-273` — that layer "只回答“本卡 / 远端的数据区基址和状态区基址分别在哪里”，不掺入
           expert、slot、token 等业务偏移"
SOURCE:    same file:240 — "- 数据区基址：`windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE`" and `:355` —
           "1. **A5 数据区偏移 1MB**：A5 平台数据区基址 = `windowsIn[rankId] + 1MB`，不加偏移将读写到
           状态区。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a dump showing that `GetBaseWindAddrByRankId` returns `windowsIn[rankId]` unshifted on A5 —
           the layout formulas would then be missing the 1 MB term and every kernel written to them
           would be reading and writing the state region. Observable as the difference between the
           accessor's return value and `windowsIn[rankId]`.
```

# 0389 · The window layout formulas start from an accessor that has already applied the one-megabyte skip

## 1 · Claim
Upstream asserts, in its window-layout document, four address formulas — dispatch data, dispatch state,
combine data, combine state — each of which begins from an accessor call and adds business offsets:
`GetBaseWindAddrByRankId(ctx, dstRank, curRankId)` for the two data regions, and
`GetBaseWindStateAddrByRankId(ctx, dstRank, curRankId)` for the two state regions. Upstream asserts, in a
different file of the same skill, that those two accessors belong to a "window base-address layer" whose
sole job is to answer where each rank's data-region and state-region bases are, without mixing in expert,
slot or token offsets. Upstream asserts, in that same file, that on A5 the data-region base **is**
`windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE` and that a kernel omitting the offset reads and writes the
state region. Not established here: nothing was compiled and no window was read.

The inference, stated separately from those three readings: the 1 MB skip is applied *inside* the data
accessor, so the layout formulas already start past it and must not add it again. Upstream states each
half and never states the composition.

This entry addresses the hole `950:0277` §7 discloses — that it establishes one term of an address
computation and not the computation. **The remaining terms are supplied**: the four layout formulas and
their constants, carried by 0390-0393. **The composition is not established.** That the 1 MB skip lives
inside the data accessor is the inference above, drawn from layer 2's stated contract, and it is settled by
one printf (§4 Arm A, `Q-950rem-11`) that has not been run. So the hole is narrowed and not closed, and §7
says the same. It does not restate 0277's constant, which remains that entry's claim.

## 2 · The wrong branch this removes
Two documents, two correct halves, and the join is where the kernel is written.

An agent that has read 0277's rule holds a memorable, emphatic fact: *on A5 you must add 1 MB*. Upstream
states it three times, once as a numbered pitfall with 必须 and a stated consequence. An agent that then
opens the layout document finds `GetBaseWindAddrByRankId(...) + srcRank * ... + localExpert * ... +
dstSlot * ...` and has to decide whether the 1 MB is in there. Nothing in the formula says. Nothing in the
accessor's name says. And the rule it just learned says to add it.

**Adding it twice lands one megabyte into the data region.** That is not a fault: the window is a single
allocation and 1 MB past the data base is still valid, mapped memory belonging to the same rank. The
kernel writes its payload there and reads it back from there consistently — so a **single-rank
self-consistency test passes**. It fails only when a partner rank writes at the correct offset and this
rank reads 1 MB past it, which is a multi-card failure that presents as garbage payload or a hang while
waiting on state that was written where nobody is looking.

**Not adding it, if the accessor does not apply it, is 0277's failure**: payload written over the
synchronisation state region, which upstream describes as producing a hang or a partner rank proceeding on
a flag it never set.

So the two errors are symmetric, both silent at build time, both survivable in single-card testing, and
the documentation supports either reading. That is why this entry's OVERTURN is an *observation of the
accessor's return value* rather than a behavioural test: the one number settles which of the two branches
an implementer is on.

**The layering statement is the strongest evidence and it is in the other file.** `mte-address-access.md`
describes a four-layer decomposition and puts the accessors in layer 2, whose stated job is to answer where
the bases are "without mixing in expert, slot or token offsets" — and then puts the layout formulas in
layer 3, "先拿基址，再叠加布局偏移". A layer whose job is to return the *data-region base* on a platform
where the data-region base is defined as `windowsIn[rankId] + 1MB` must apply the offset, or it is not
returning what it says it returns. That is an argument from the stated contract, and it is the reason §1's
inference reads as it does. It is not a reading of the accessor's implementation, which is in a sample this
harvest does not have.

**A second, quieter join.** The state formulas start from `GetBaseWindStateAddrByRankId`, a *different*
accessor. On A5 the state base is `windowsIn[rankId]` itself — unshifted. So the two accessors return
addresses 1 MB apart on A5 and, on A3, come from two entirely different struct fields (`localWindowsIn`
and `localWindowsExp`, `mte-address-access.md:213`). The layer exists precisely to hide that difference,
and an agent that "simplifies" by using one accessor and adding a constant has re-introduced the platform
branch the layer was built to remove — and has hardcoded the A5 layout into a kernel that will be built
for A3.

## 3 · Ground / Source
The four formulas, `window-memory-layout.md`. Dispatch data, `:36-44`:

> ```c++
> GM_ADDR dstDataAddr =
>     GetBaseWindAddrByRankId(ctx, dstRank, curRankId)
>     + (uint64_t)srcRank    * sourceRankRegionBytes
>     + (uint64_t)localExpert * expertRegionBytes
>     + (uint64_t)dstSlot    * commTokenBytes
> ```
>
> 其中 `dstSlot = curExpertCnt`，即该 token 在目标 expert 已接收 token 中的顺序序号。

Dispatch state, `:88-100`:

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

Combine data, `:126-131`, and combine state, `:171-176`, follow the same shape from the same two
accessors. So there are **three** base accessors in play — the two rank-parameterised ones and
`GetStatusDataSpaceGm(ctx)` for the local state region — and `mte-address-access.md:213` notes that on A3
`localWindowsExp` 兼做 `GetStatusDataSpaceGm`, i.e. the local-state accessor and the remote-state field are
the same storage there.

The layering, `mte-address-access.md:265-283`:

> ### 2. window 基址获取层
>
> 这一层只回答“本卡 / 远端的数据区基址和状态区基址分别在哪里”，不掺入 expert、slot、token 等业务偏移。
> …
> sample 的 `GetStatusDataSpaceGm`、`GetBaseWindAddrByRankId`、`GetBaseWindStateAddrByRankId` 属于这一层。
> 这里对应的是“数据区基址”和“状态区基址”分开封装，而不是在主流程里反复手写平台分支。
>
> ### 3. 业务地址拼装层
>
> 这一层在拿到基址后，再结合 layout 公式拼出 dispatch / combine 真正要访问的 slot 地址。

and the principle at `:257`: "`winContext` 只提供每张卡 window 的基址；真正的数据区布局、状态区布局、slot
偏移，仍要由 layout 公式决定" — followed at `:365` item 7 by "先拿 window 基址，再套 layout 公式：
`winContext` 不会直接给你某个 slot 的最终地址，它只提供 window 基址；真正的 slot 地址还要结合
`window-memory-layout.md` 里的布局公式计算."

That item 7 is the pointer 0277 §3 follows to reach this file, and this entry is the other end of it.

The A5 base definitions, `:236-241`, quoted at 0277 §3 and cited here in SOURCE. Note the exact wording:
数据区基址 is *defined as* `windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE`. It is a definition of what the term
"data-region base" means on A5, not an instruction to add something to an accessor's output — and layer 2's
job is to return the data-region base.

What upstream never states, in either file: whether `GetBaseWindAddrByRankId` applies the offset. The
sample implementations are named and not shown; `mte-address-access.md:277` calls them "本地工程里通常会
提供一层 compat helper" and `:279` warns "这些 helper 本质上是工程代码对 `winContext` 的一层适配，不代表
HCCL 会直接提供同名 kernel API" — so the accessors are project code, not a vendor API, and their behaviour
is a property of a sample this harvest does not have.

The struct-instability warnings at `:20` and `:22` (recorded at 0277 §3) apply here too: the sample's
`HcclA5OpResParam` is a 精简定义 unsuitable for parsing a real HCCL context, and what survives is that the
field layout is determined once the platform is fixed.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board with at least 2 cards. The central question is answered by reading one
pointer.

Arm A — the accessor's return value, compared against the raw field. On A5, print
`GetBaseWindAddrByRankId(ctx, rankId, rankId)`, `GetBaseWindStateAddrByRankId(ctx, rankId, rankId)` and
the raw `windowsIn[rankId]` from the context. Record the two differences. The claim predicts
data − raw = 1048576 and state − raw = 0. This is the whole entry in one printf and it needs no partner
rank.

Arm B — the composition, end to end. With a partner rank writing a known payload at a known
(srcRank, localExpert, dstSlot), compute `dstDataAddr` by the layout formula and dump the bytes there.
They must be the payload. Then compute it again with an extra 1 MB added and dump: those bytes must **not**
be the payload. The pair is what distinguishes "the formula works" from "the dump happens to find payload
somewhere", and the second half is the double-offset error made visible.

Arm C — the double-offset failure shape. Build the dispatch kernel with the extra 1 MB and run the full
collective. Record whether it produces wrong output, hangs, or completes with correct output at some rank
counts. §2 predicts single-rank self-consistency and multi-rank failure; confirming the *self-consistency*
is what explains why the error survives testing, and it is the most useful sentence for a reviewer.

Arm D — the state accessors. Confirm `GetBaseWindStateAddrByRankId(ctx, rank, rank)` and
`GetStatusDataSpaceGm(ctx)` return the same address for the local rank on A5, and record whether they
differ on A3. Upstream implies the first and states the A3 aliasing at `:213`; neither is observed.

Arm E — the four formulas, each exercised once. For dispatch data, dispatch state, combine data and combine
state, write a known value through the formula and read it back through an independently computed address
(host-side arithmetic from the raw base). Four independent checks; a formula that is wrong in one of the
four is invisible to a test that exercises only the dispatch path.

Device selection is explicit and stricter because this is multi-card: the operator names every card in the
group, the harness prints them back with `compiler/version.info` and each resolved SoC string, occupancy is
checked on all of them before the run (shared machine, ≤4 dies), and no card is substituted between arms.
Arm C's double-offset build must run with a declared watchdog timeout and release the cards on timeout — a
hang is a predicted outcome and an un-timed arm would hold the group. Capture protocol for any timing:
≥10 iterations, first 5 discarded, mean of the last 5, **max across ranks** (a mean would hide the
straggler that sets the latency).

## 5 · Checker — acceptance declared before the run
`data_accessor_offset_bytes` (Arm A) — `GetBaseWindAddrByRankId(...) − windowsIn[rankId]`. Pass iff
1048576. A value of 0 is the OVERTURN: the accessor does not apply the skip, the layout formulas are
missing the term, and every kernel written to them addresses the state region. Any other value corrects
0277's constant in place and is logged there.

`state_accessor_offset_bytes` (Arm A) — the same difference for the state accessor. Pass iff 0. Reported
separately and never merged with the data offset: the entire claim is that the two accessors differ, and
one combined "the accessors look right" verdict would erase it.

`formula_locates_payload` (Arm B) — true iff the layout-formula address holds the partner's payload **and**
the plus-1 MB address does not. Both clauses required. Without the second, "the payload was found" is
consistent with a dump that searches rather than addresses.

`double_offset_signature` (Arm C) — three-valued: wrong output, hang, or correct output; plus a separate
boolean for whether the single-rank case was self-consistent. Reported, not gated.

`local_state_accessors_agree` (Arm D) — true iff the two local-state accessors return one address on A5.
Reported.

`per_formula_correct` (Arm E) — four booleans, one per formula, never aggregated. Three correct and one
wrong is the realistic defect and no pass rate would surface which.

The positive fixture, declared before the run: Arm B's partner must write a **second** known payload at a
**different** known slot, and the formula's address must move by exactly the predicted number of bytes. If
it does not move, the dump is locating something other than the payload — a zero boundary, a struct field,
a coincidence — and every address in the arm is void. This is the same fixture 0277 §5 declares for its own
Arm A, and it is required again here because this entry's addresses are computed differently. A second
fixture for Arm A: `windowsIn[rankId]` must be shown to be a plausible device address (non-null, aligned,
inside the reported `winSize` range); if the raw field is being read at the wrong struct offset — which
`:20` warns is likely with the sample's 精简定义 — both differences are arithmetic on garbage. Without
both, the checker reads only "two pointers differed by a megabyte", which is the known blind species.

Process exit codes are not the verdict for any arm: Arm C expects a hang or wrong output from a process
that may exit zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no accessor
called, no window dumped, no payload written or located, and no card was contacted. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest. No SDK header was read for any
of the three accessors — upstream states they are project sample code rather than a vendor API, so no
header would carry them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that `GetBaseWindAddrByRankId` applies the 1 MB
skip — **that is an inference from layer 2's stated contract**, not a reading of any implementation, and
Arm A is what would settle it in one observation. It does not establish that adding the offset twice
produces the failure §2 describes, nor that a single-rank test would pass.

It does not establish 0277's constant. The 1 MB figure, the state-before-data layout, and the consequence
of omitting the offset are `950:0277`'s claims, resting on the same upstream skill; this entry composes with
them and adds no evidence for them. `Q-950arch-24` records the measurement owed there.

**It does not establish any of the layout formulas' terms.** `sourceRankRegionBytes`,
`expertRegionBytes`, `commTokenBytes`, `STATE_SLOT_BYTES` and the combine-side quantities are separate
claims carried by 0390, 0391, 0392 and 0393; this entry claims only the composition — that the formulas
start from an accessor, not from a raw field.

It does not establish the accessors' behaviour on A3, where the two bases come from different struct fields
and remote addresses are reached through a pointer chain (`remoteRes[rankId].nextDevicePtr`,
`mte-address-access.md:213`). Only the A5 composition is claimed, and even that is scoped by compile macro
rather than by board.

It does not establish that the accessors exist under those names in any real project. Upstream calls them
sample/compat helpers and warns explicitly at `:279` that HCCL provides no same-named kernel API. So the
names are a convention of one sample, and a consuming team's tree may spell them differently or place the
offset elsewhere — which is precisely why Arm A compares a return value against a raw field rather than
trusting a name.

BOARD is `family-claimed(unverified)`: upstream scopes the A5 half by `__NPU_ARCH__ == 3510` and names no
board token this book recognises; no board was contacted.

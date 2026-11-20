```
ID:        0390-a-dispatch-comm-token-is-a-32-byte-aligned-payload-followed-by-a-twelve-byte-triple
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice). Upstream gives the byte
           arithmetic and no measurement; the file uses two different names for the rank-count symbol
           in adjacent formulas. Nothing was compiled and no token was written.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/tiling-scheme/window-memory-layout.md:17-32
           — "排布维度：sourceRank → localExpert → tokenSlot" … "每个 tokenSlot 存放一个完整通信 token =
           payload（32B 对齐）+ triple（3 × int32）。" … "```c++ / payloadBytes = AlignUp(H *
           sizeof(dtype), 32)   // 32B 对齐 / tripleBytes = 3 * sizeof(int32_t)               // = 12B,
           [srcRank, srcTokenIdx, srcTopKIdx] / commTokenBytes = payloadBytes + tripleBytes /
           expertRegionBytes = BS * commTokenBytes               // 单个 (srcRank, localExpert) 区域 /
           sourceRankRegionBytes = localExpertNum * expertRegionBytes / rankDataBytes = epWorldSize *
           sourceRankRegionBytes / ```"
SOURCE:    same file:46-52 — "### Triple 写入位置 / ```c++ / // payload 写完后，triple 紧随其后 /
           uint32_t tripleOffset = payloadBytes / sizeof(dtype);  // dtype 单位偏移 / // triple[0] =
           srcRankId, triple[1] = srcTokenIdx, triple[2] = srcTopKIdx / ```"
SOURCE:    same file:31 vs :83 — `rankDataBytes = epWorldSize * sourceRankRegionBytes` in the data-region
           block, against `totalStateBytes = localExpertNum * rankDim * STATE_SLOT_BYTES` in the
           state-region block: two symbols, `epWorldSize` and `rankDim`, for what the address formulas
           at `:38-42` and `:89-92` treat as one rank dimension. Neither is defined in the file.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a dispatch token layout on a 950 board in which the triple does not immediately follow the
           aligned payload — for example padding between them, or the triple placed before the payload —
           observable by writing a distinctive triple and locating it in a dump of one token slot.
```

# 0390 · A dispatch comm token is a 32-byte-aligned payload followed by a twelve-byte triple

## 1 · Claim
Upstream asserts the dispatch data region's layout: the arrangement dimensions are sourceRank →
localExpert → tokenSlot, and each token slot holds one complete communication token consisting of a
payload aligned up to 32 bytes and a triple of three `int32` values. Upstream asserts the byte arithmetic:
`payloadBytes = AlignUp(H * sizeof(dtype), 32)`; `tripleBytes = 3 * sizeof(int32_t)` = 12 B carrying
`[srcRank, srcTokenIdx, srcTopKIdx]`; `commTokenBytes = payloadBytes + tripleBytes`;
`expertRegionBytes = BS * commTokenBytes` for one (srcRank, localExpert) region;
`sourceRankRegionBytes = localExpertNum * expertRegionBytes`; and `rankDataBytes = epWorldSize *
sourceRankRegionBytes`. Upstream asserts the triple is written immediately after the payload, at a
dtype-unit offset of `payloadBytes / sizeof(dtype)`, and names the three fields in order. Not established
here: nothing was compiled and no token was written.

## 2 · The wrong branch this removes
Without the layout an agent writing a dispatch kernel invents one, and three of its natural choices are
wrong in ways nothing reports.

**Packing without the alignment.** `H * sizeof(dtype)` is the obvious payload size and it is right only
when it happens to be a multiple of 32. For `H` = 7168 at bf16 it is 14336, already aligned; for `H` = 100
at fp32 it is 400, and `AlignUp(400, 32)` = 416. An agent that packs tightly produces a token stride 16
bytes short of the receiver's, so every token after the first is displaced by an accumulating offset —
token *n* is wrong by 16*n* bytes. The first token is correct, which is exactly the case a single-token
test exercises. This is the classic stride mismatch and it is silent because both sides are writing and
reading valid memory.

**Putting the triple first.** A header-then-payload layout is the more common convention in message
formats, and it is the one an agent will reach for if the order is not stated. Upstream states it — 紧随其后,
immediately following — but the reason it matters is that the payload's *alignment* is what fixes the
triple's position: if the triple went first, the payload would start at offset 12 and the 32-byte alignment
would be broken for every DMA that moves it. So the order is not stylistic; it is what makes the aligned
payload reachable by an aligned copy. Upstream does not say that, and an agent that reorders "for
readability" breaks the alignment guarantee without touching the alignment code.

**Reading `tripleOffset` as a byte offset.** The line is
`uint32_t tripleOffset = payloadBytes / sizeof(dtype);` with the comment dtype 单位偏移 — a dtype-unit
offset. So it is an *element* index into a `dtype`-typed pointer, not a byte offset. An agent that
computes `basePtr + tripleOffset` on a `__gm__ uint8_t*` lands at `payloadBytes / sizeof(dtype)` bytes
instead of `payloadBytes` — for bf16, half the intended distance, inside the payload. The variable's name
carries no unit and its type is `uint32_t`, so nothing but the comment distinguishes the two readings.

There is a second-order hazard in the same line worth naming: the triple is three `int32` values, and the
payload is `dtype`. Writing an `int32` triple through a `dtype`-typed pointer at a dtype-unit offset
requires a reinterpretation, and if `dtype` is bf16 the triple's 12 bytes span six bf16 elements. The
arithmetic is consistent; the pointer types are not, and upstream shows neither the cast nor the write.

**And the size formula's symbol does not match the address formula's.** `rankDataBytes` uses
`epWorldSize`; the state-region block eight lines later uses `rankDim` for what the two address formulas
treat as the same rank dimension. Neither symbol is defined in this file. If they are the same quantity
under two names, the file has a naming defect; if they differ — an expert-parallel world size versus a
communication-domain size — then the data region is sized by one and the state region by another, and a
kernel that uses one for both mis-sizes a region. Upstream does not say which, and the two blocks are
adjacent.

## 3 · Ground / Source
The layout rule and the constants, `window-memory-layout.md:13-32`:

> ## Dispatch 数据区布局
>
> ### 布局规则
>
> ```
> 排布维度：sourceRank → localExpert → tokenSlot
> ```
>
> 每个 tokenSlot 存放一个完整通信 token = payload（32B 对齐）+ triple（3 × int32）。
>
> ### 基础常量
>
> ```c++
> payloadBytes         = AlignUp(H * sizeof(dtype), 32)   // 32B 对齐
> tripleBytes          = 3 * sizeof(int32_t)               // = 12B，[srcRank, srcTokenIdx, srcTopKIdx]
> commTokenBytes       = payloadBytes + tripleBytes
> expertRegionBytes    = BS * commTokenBytes               // 单个 (srcRank, localExpert) 区域
> sourceRankRegionBytes = localExpertNum * expertRegionBytes
> rankDataBytes        = epWorldSize * sourceRankRegionBytes
> ```

The nesting is consistent with the address formula at `:38-42` (0389 §3): `srcRank *
sourceRankRegionBytes + localExpert * expertRegionBytes + dstSlot * commTokenBytes` walks the same three
dimensions in the same order. That internal agreement is worth recording — it is the file agreeing with
itself, which is not corroboration, but a disagreement there would have been a defect and there is none.

Note that `commTokenBytes` is **not** itself aligned: an aligned payload plus 12 bytes is a multiple of 32
plus 12, so successive token slots start at offsets 12, 24, 4, 16, 28, … modulo 32. Only the *first*
token's payload is 32-byte aligned; every subsequent one is misaligned by a rotating amount. Upstream
aligns `payloadBytes` and does not align `commTokenBytes`, and says nothing about the consequence. That
matters directly against 0257, which records that `LoadAlign`/`StoreAlign` require 32-byte-aligned
addresses — a copy of token *n*'s payload starts at an address that is aligned only when
`12n ≡ 0 (mod 32)`, i.e. every eighth token. This is derived here from upstream's own arithmetic and is
stated by no source; §4 Arm C is what would establish whether it bites.

The triple's position, `:46-52`:

> ### Triple 写入位置
>
> ```c++
> // payload 写完后，triple 紧随其后
> uint32_t tripleOffset = payloadBytes / sizeof(dtype);  // dtype 单位偏移
> // triple[0] = srcRankId, triple[1] = srcTokenIdx, triple[2] = srcTopKIdx
> ```

Three named fields in order. `srcTopKIdx` connects to the combine side, where `:133` states
`srcSlotIdx = srcTopKIdx` for a MoE slot — so the triple is the return path's addressing information, which
is why it travels with the payload rather than in the state region.

The undefined symbols. `H`, `dtype`, `BS`, `localExpertNum`, `epWorldSize` and `rankDim` are all used and
none is defined in this file. `:5-9` states what a reader is assumed to know before opening the page —
the dispatch/combine phase decomposition, the token/`expandIdx`/`epRecvCounts`/`epSendCounts` relationship,
and whether the window+state protocol is in use — and symbol definitions are not on that list. So the
formulas are dimensionally checkable and not evaluable from this document.

Recorded as `C-950rem-011` (the `epWorldSize` / `rankDim` pair). All quoted material is
`upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board with at least 2 cards. The layout is a byte-level claim, so the
procedure dumps bytes.

Arm A — one token, read. With a partner rank dispatching a single token whose payload is a recognisable
ramp and whose triple is `[7, 11, 13]`, dump `commTokenBytes` from the computed slot address (0389's
composition) and locate: where the payload starts, where it ends, where the triple starts, and what lies
between. The offsets are the claim. Run at two `H` values — one whose raw size is already 32-aligned and
one whose is not — because the alignment term is invisible in the first.

Arm B — the stride, over many tokens. Dispatch `BS` tokens with per-token distinguishable payloads and
locate each. The measured slot-to-slot stride is `commTokenBytes`; compare against the formula. A stride
short by exactly `AlignUp(H*sizeof(dtype),32) − H*sizeof(dtype)` would mean the implementation packs
tightly and the document describes an intention rather than the code.

Arm C — the rotating misalignment §3 derives. For tokens 0 through 8, record each payload's start address
modulo 32, and record whether the kernel's payload copy uses an alignment-requiring API. Under §3 only
every eighth token is 32-byte aligned. If the copy path is `LoadAlign`/`StoreAlign` (0257) this must
produce a fault or wrong data on the other seven; if it does not, either the copy path tolerates
misalignment or `commTokenBytes` is aligned somewhere the document does not show. Both outcomes are
findings and neither is stated anywhere.

Arm D — the triple's unit. Write the triple through the documented `tripleOffset` on a `dtype`-typed
pointer and, separately, at a byte offset of `payloadBytes`, and dump both. Confirm which lands
immediately after the payload. This settles §2's third branch in one comparison and needs only one rank.

Arm E — the two rank symbols. Print `epWorldSize` and `rankDim` from the context in a run with a
non-trivial expert-parallel configuration, and compare. If they are equal in every reachable configuration
the naming is a defect only; if they can differ, the data and state regions are sized by different
quantities and every kernel using one for both is wrong in one of the two regions.

Device selection is explicit and multi-card: the operator names every card in the group, the harness prints
them back with `compiler/version.info` and each resolved SoC string, occupancy is checked on all of them
before the run (shared machine, ≤4 dies), and no card is substituted between arms. A watchdog timeout and
card release are declared before any arm that can hang on a state wait.

## 5 · Checker — acceptance declared before the run
`payload_bytes_observed` (Arm A) — the measured distance from payload start to triple start, at both `H`
values. Pass iff it equals `AlignUp(H * sizeof(dtype), 32)` in both cases. Equality at the already-aligned
`H` alone establishes nothing about the alignment term and is reported as such.

`token_stride_observed` (Arm B) — the measured slot-to-slot distance. Pass iff `commTokenBytes`. Reported
separately from `payload_bytes_observed`: a correct payload size with a wrong stride is a different defect
from the reverse, and one combined "layout matches" verdict would carry neither.

`payload_alignment_by_index` (Arm C) — each token's payload start modulo 32, for tokens 0-8, plus whether
the copy path faults or corrupts. Reported as a series, never as "mostly aligned".

`triple_offset_unit` (Arm D) — two-valued: dtype-unit or byte. Reported; upstream's comment says the
first and the variable name says nothing.

`rank_symbols_equal` (Arm E) — true iff `epWorldSize == rankDim` in the tested configuration, with the
configuration recorded. Reported, never generalised from one configuration to "they are the same".

The positive fixture, declared before the run: Arm A's payload must be a **ramp**, not a constant, so that
its start and end are both locatable and a shifted read is distinguishable from a correct one. A constant
payload makes "the payload is here" true at many offsets. And the triple must be `[7, 11, 13]` —
distinctive small primes that cannot be confused with a length, a rank index, a slot count or an alignment
constant. If the dump cannot locate those three values in the token, it is not reading the token region and
every offset in the arm is void. Without both, the checker reads only "bytes were found", which is the
known blind species and is especially easy here because a token region is full of plausible integers.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no token
dispatched, no window dumped, no offset located, and no card was contacted. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the 32-byte alignment, the 12-byte triple, the
token stride, or the triple's position — Arms A through E are all open, and upstream supplies **arithmetic
and no measurement**.

It does not establish any symbol's value or meaning. `H`, `dtype`, `BS`, `localExpertNum`, `epWorldSize`
and `rankDim` are used and undefined in this file, so the formulas are dimensionally checkable and not
evaluable from it. Whether `epWorldSize` and `rankDim` denote one quantity is `C-950rem-011` and is open.

**The rotating-misalignment consequence in §3 is derived here and stated by no source.** That
`commTokenBytes` is a multiple of 32 plus 12, and therefore that only every eighth token's payload is
32-byte aligned, follows from upstream's own two constants; whether it matters depends on the copy path's
alignment requirements (0257) and on whether a real implementation pads the token slot. Arm C is what
would establish it, and until then it is arithmetic about a document.

It does not establish where the token slot's address comes from — that is 0389's composition claim, which
this entry uses and does not re-derive — nor the 1 MB state-region offset, which is 0277's.

It says nothing about the dispatch **state** region (0391), the combine regions (0392), or the state-region
UB budget (0393); each is a separate block of the same file with its own constants.

It says nothing about how a real implementation writes the token: no source in scope shows the copy, the
pointer casts between `dtype` and `int32`, or whether payload and triple are written by one DMA or two.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises, its A5 scoping
lives in a sibling file and is by compile macro, and no board was contacted.

```
ID:        0332-gather-source-offsets-stop-at-65535-bytes-for-8-bit-and-131071-for-16-bit-and-the-in-code-comment-is-stale
LABEL:     boundary
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/templates/usage_guide.md:216-217 —
           "Gather source offset 硬门槛：8 位不超过 65535B，16 位不超过 131071B。表项、offset 单位和
           dtype 字节数必须一起校验；旧实现注释中的 `dChunk<=256` 已过期，当前整块输入 Gather 门槛
           是 128。"
SOURCE:    same file:210-214 — "- `dChunk <= 128` 且容量/offset 满足时，用一张全量偏移表做一次大
           Gather； - 其它场景逐行 Gather 到 `[G,dChunk]`，但不退回 GM 单元素读； - 尾 dChunk 先填
           padding，再用 2D DMA 覆盖有效部分。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board that issues a Gather with an 8-bit source offset above
           65535 B, or a 16-bit one above 131071 B, and returns correct data — the limits would then
           not be hard, and every buffer-sizing decision derived from them would be over-constrained.
```

# 0332 · Gather source offsets stop at 65535 bytes for 8-bit and 131071 for 16-bit, and the in-code comment is stale

## 1 · Claim
Upstream asserts two hard limits on the source offset a Gather may address: 65535 bytes with an
8-bit offset representation and 131071 bytes with a 16-bit one. Upstream asserts a validation
obligation that goes with them — the table entries, the offset's unit, and the dtype's byte width
must be checked *together*, because the limit is in bytes while a table is written in whatever unit
the author chose. Upstream asserts that an existing in-code comment giving `dChunk <= 256` is out of
date and that the current threshold for gathering a whole input block in one call is 128. Upstream
asserts the surrounding routing: at `dChunk ≤ 128`, with capacity and offset satisfied, one full
offset table drives one large Gather; otherwise the assembly proceeds row by row into `[G, dChunk]`
and must **not** fall back to single-element GM reads; and the tail `dChunk` is pre-filled with
padding before a 2D DMA covers the valid part. Not established here.

## 2 · The wrong branch this removes
The stale comment is the entry's centre and the failure it causes is specific. An implementer
reading `dChunk <= 256` in the code sizes the block to 256, the offsets then exceed the
representable range for the chosen width, and the Gather reads from the wrong place. The comment is
*inside the code*, which is where an implementer trusts most; the correction is in a prose guide the
implementer may not open.

The second wrong branch is validating the wrong quantity. The limit is a byte count. A table of
element offsets multiplied by an element width can be perfectly legal at fp16 and overflow at fp32
with the same table and the same `dChunk`. Upstream states the three-way check
(`表项、offset 单位和 dtype 字节数必须一起校验`) precisely because checking `dChunk` alone passes at
one dtype and fails at another — a shape-and-dtype interaction that a single-dtype test suite will
not see.

The third is the fallback direction. When the block Gather is unavailable, the tempting retreat is
single-element GM reads — simple, always correct, and catastrophic on a latency-bound path
(`950:0161` records this family's neighbour measuring an order of magnitude for exactly that
substitution, 1565 µs → 89 µs). Upstream forbids it and names the intermediate: row-wise Gather into
`[G, dChunk]`.

## 3 · Ground / Source
The limits and the stale comment, `templates/usage_guide.md:216-217`:

```
Gather source offset 硬门槛：8 位不超过 65535B，16 位不超过 131071B。表项、offset 单位和 dtype
字节数必须一起校验；旧实现注释中的 `dChunk<=256` 已过期，当前整块输入 Gather 门槛是 128。
```

The routing it sits inside, `:207-214`:

```
### 8.1 输入 2D Compact DMA + Gather

原布局中同一 TopK 行沿 D 的步长为 inner。一次搬入 D 个 block，每个 block 含 G 个连续元素，
Compact 模式在 UB 中形成 `[dChunk,G]`。随后：

- `dChunk <= 128` 且容量/offset 满足时，用一张全量偏移表做一次大 Gather；
- 其它场景逐行 Gather 到 `[G,dChunk]`，但不退回 GM 单元素读；
- 尾 dChunk 先填 padding，再用 2D DMA 覆盖有效部分。
```

On the numbers. `65535 = 2¹⁶ − 1` and `131071 = 2¹⁷ − 1`. So the "8-bit" and "16-bit" labels do not
name the offset field's width in the obvious way — an 8-bit field could not express 65535 at all.
The consistent reading is that they name the *element width* (8-bit and 16-bit dtypes) and that the
byte limit doubles with it, which would make the underlying quantity a 16-bit **element** count:
`65535` elements of 1 byte, `65535` elements of 2 bytes ≈ `131070`, off by one from the stated
`131071`. That off-by-one is not resolvable from the text, and the alternative reading — two
different address-field widths, 16-bit and 17-bit — is equally consistent with the numbers and less
consistent with the phrase `8 位 / 16 位`. **This entry does not choose.** Both readings are
recorded, they differ by one byte at the boundary, and §4 Arm 1 is a bisection that settles it
without interpretation. Recorded in `harvest/standing/950-bp.md`.

That ambiguity is the reason the entry's slug carries the byte figures rather than the widths: the
byte figures are what upstream states, and the widths are what upstream's labels claim to mean.

`dChunk` is the D-direction chunk size the fallback tiler searches jointly with `G` inside a 240 KiB
UB budget (`:167-169`, and `950:0140` from the sibling shelf for the budget). `G` is capped at 128
by the same passage — the same number as the current `dChunk` threshold, which is a coincidence
worth *not* collapsing: they are different quantities with the same cap, and an implementer who ties
them together will not be able to search them jointly, which is what the tiler does.

Nothing here is measured. There is no timing, no failing case, and no statement of what happens when
a limit is exceeded — silently wrong data, a fault, or a clamp is not distinguished.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the boundary, bisected. Issue a Gather whose maximum source offset is swept across each
candidate limit at 1-byte granularity: `65534, 65535, 65536` for the 8-bit-element case and
`131069, 131070, 131071, 131072` for the 16-bit one. Compare every result elementwise against a CPU
reference. The largest offset that returns correct data is the limit, and it settles §3's ambiguity
without anyone having to decide what `8 位` means. Record also *how* the failure presents — wrong
data, fault, or clamp — since upstream does not say and the answer determines whether a runtime
guard is needed or a compile-time one suffices.

Arm 2 — the three-way validation, tested where it bites. Hold the offset *table* fixed and vary only
the dtype byte width (int8 → fp16 → int32) so that the same table addresses 1×, 2× and 4× the bytes.
Upstream's obligation predicts the legal `dChunk` falls as the dtype widens. A test suite that
sweeps `dChunk` at one dtype would find one limit and generalise it wrongly; this arm is the shape
of the test that would not.

Arm 3 — the stale comment, as a live regression. Build the block-Gather path at `dChunk = 128` and
at `dChunk = 256`, at each dtype. Upstream's correction predicts 256 fails somewhere; if it passes
at every dtype, the comment is not stale and the guide is wrong, and the entry is corrected in
place.

Arm 4 — the forbidden fallback, priced rather than assumed. Build the row-wise Gather assembly and a
single-element GM read version of the same case, and time both. Upstream forbids the second without
quantifying it; this is the number that would make the prohibition portable.

Variance floor first for Arm 4: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median, with `0327`'s same-path sibling check applied before the table is read. Arms 1–3 are exact
comparisons and need no floor. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that exceeding the limit fails loudly (Arm 1 records the failure mode
explicitly, because a silent wrong read is the dangerous case and a fault is the safe one); that the
offset unit in the shipped table is bytes — it is echoed from the kernel alongside the dtype width,
which is the whole point of the three-way check.

## 5 · Checker — acceptance declared before the run
Verdict `limit8` and `limit16` = the largest source offsets in Arm 1 that return correct data.
Declared before the run, with both candidate readings named so neither can be adopted afterwards:
`(65535, 131071)` supports upstream's literals; `(65535, 131070)` supports the "16-bit element
count" reading and makes the guide's `131071` off by one; anything else overturns both.

Verdict `fail_mode` ∈ {wrong-data, fault, clamp} from Arm 1, reported unconditionally.
Verdict `dtype_scaling` = true iff Arm 2's legal `dChunk` halves as the dtype width doubles.
Verdict `dchunk256_fails` = true iff Arm 3's 256 build fails at any dtype.
Verdict `scalar_penalty` = Arm 4's ratio, reported with its floor.

The exit code is not the verdict. Three guards.

First, every Gather result is compared elementwise against a CPU reference, never checked for
plausibility. A Gather reading past its limit returns *data*, and data that is the right shape and
the right dtype passes every check except a comparison.

Second — the input that makes this checker go red — Arm 1 is preceded by a control at an offset far
*below* every candidate limit, which **must** return correct data. If the control fails, the harness
is not issuing a working Gather at all, every boundary reading is void, and the "limit" it would
report is an artefact of a broken setup. That planted positive is required because a bisection whose
lower arm is broken always finds a limit, and always the wrong one.

Third, `limit8` and `limit16` are reported as observed byte counts with the dtype and the offset
unit echoed beside them. A limit reported without those three is the exact form of the statement
this entry says cannot be validated.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 65535, 131071, 128 and 256
are upstream's stated figures; no Gather was issued, no offset was swept, and the ambiguity in §3
between "16-bit element count" and "two address-field widths" is unresolved because only a run can
resolve it.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not resolve what `8 位` and `16 位` label —
element width or offset-field width — and the two readings differ at the boundary by one byte;
adopting either here would be picking the more plausible author, which Art. 7 forbids. It does not
establish what happens when a limit is exceeded: upstream states the limits and never the failure
mode, so a consuming skill cannot know whether a guard must be runtime or may be compile-time. It
does not establish that `dChunk ≤ 256` was ever correct, only that upstream now says otherwise; the
comment upstream calls stale is in code not reproduced in this guide, and this book has not located
it. The relationship between the `dChunk` cap of 128 and the `G` cap of 128 is not established —
they are separate quantities that happen to share a value. The forbidden single-element fallback is
prohibited without a number. `dChunk`, `G` and the 240 KiB budget come from the sibling shelf
(`950:0140`) and are one origin with this document. BOARD is `family-claimed(unverified)`: the
document targets Ascend 950 / DAV_3510 and names no board. Nothing transfers to the other book
(RULES.md Art. 1).

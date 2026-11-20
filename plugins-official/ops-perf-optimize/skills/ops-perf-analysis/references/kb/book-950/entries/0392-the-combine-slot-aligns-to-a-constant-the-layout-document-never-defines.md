```
ID:        0392-the-combine-slot-aligns-to-a-constant-the-layout-document-never-defines
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice). The combine block uses an
           undefined symbol where the dispatch block eight lines earlier uses a literal, and states a
           per-slot size as implementation-defined immediately before hardcoding it. Nothing was
           compiled and no combine slot was written.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/tiling-scheme/window-memory-layout.md:114-122
           — "### 基础常量 / ```c++ / slotCountPerToken    = K + sharedExpertNum / payloadBytes =
           H_expand * sizeof(ExpandXType) / slotBytes            = AlignUp(payloadBytes, winAlignBytes)
           / tokenRegionBytes     = slotCountPerToken * slotBytes / rankCombineBytes     = BS *
           tokenRegionBytes / ```" — `winAlignBytes` appears here and nowhere else in the file.
SOURCE:    same file:26 — the dispatch counterpart, which uses a literal: "payloadBytes =
           AlignUp(H * sizeof(dtype), 32)   // 32B 对齐"
SOURCE:    same file:145-152 — "每个状态槽大小由实现决定，最小为 32B。 / ### 基础常量 / ```c++ /
           stateStrideBytes      = 32    // 单个状态槽 / tokenStateRegionBytes = slotCountPerToken *
           stateStrideBytes / ```" — stated as implementation-defined with a 32 B floor, then fixed at 32
           two lines later.
SOURCE:    same file:106-112,133,156-167 — the combine layout: "排布维度：srcTokenIdx → slotIdx
           (K + sharedExpertNum slots per token) / 前 K 个 slot：MoE expert 结果（按 topK 顺序） /
           后 sharedExpertNum 个 slot：共享专家结果"; "其中 `srcSlotIdx = srcTopKIdx`（MoE slot）或
           `K + sharedExpertSlotIdx`（共享专家 slot）"; "slot[0] = readyFlag   (0=未就绪, 1=就绪) /
           slot[1..7] = padding"; "targetReadyCount(token) = K + sharedExpertNum   // 无 mask 时 /
           // 有 xActiveMask 或 zero expert 时需相应减少"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a definition of `winAlignBytes` anywhere in upstream or in a real MC² implementation — the
           symbol would then be defined and the defect would be a cross-reference omission rather than an
           undefined term. Separately: a combine slot stride observed to differ from 32 bytes on the state
           side, which would confirm the "implementation-defined" reading against the hardcoded constant.
```

# 0392 · The combine slot aligns to a constant the layout document never defines

## 1 · Claim
Upstream asserts the combine data region's layout: the arrangement dimensions are srcTokenIdx → slotIdx,
with `K + sharedExpertNum` slots per token, the first `K` holding MoE expert results in topK order and the
remaining `sharedExpertNum` holding shared-expert results. Upstream asserts the byte arithmetic:
`slotCountPerToken = K + sharedExpertNum`; `payloadBytes = H_expand * sizeof(ExpandXType)`;
`slotBytes = AlignUp(payloadBytes, winAlignBytes)`; `tokenRegionBytes = slotCountPerToken * slotBytes`;
`rankCombineBytes = BS * tokenRegionBytes`. Upstream asserts the combine state region uses the same
arrangement, that each state slot's size is 由实现决定 — determined by the implementation — with a minimum
of 32 bytes, and then asserts `stateStrideBytes = 32`. Upstream asserts the slot format (word 0 a ready
flag, words 1-7 padding) and the wait condition `targetReadyCount(token) = K + sharedExpertNum` in the
unmasked case, reduced when `xActiveMask` or a zero expert is present. Not established here: nothing was
compiled and no combine slot was written.

`winAlignBytes` appears once in the file and is defined nowhere in it.

## 2 · The wrong branch this removes
The alignment constant is the single number that decides whether two ranks agree about where a slot
begins, and the document leaves it as a name.

**Every guess is defensible and they disagree.** An agent implementing `AlignUp(payloadBytes,
winAlignBytes)` must supply a value. 32 is the obvious one — it is what the dispatch block eight lines
earlier uses as a literal for the same operation, and 0257 records 32 as the `LoadAlign`/`StoreAlign`
address requirement. 512 is defensible as a window or DMA granularity. 128 or 256 appear elsewhere in this
book's material as cache-line candidates (`Q-950arch-13`). The choices are not equivalent: for
`H_expand` = 100 at fp32, `payloadBytes` = 400 and `slotBytes` is 416, 512, or 448 depending. **A writer and
a reader that pick differently disagree about every slot after the first**, by an amount that accumulates
with `slotIdx` and then again with `srcTokenIdx`. Nothing faults; the combine result is assembled from the
wrong offsets.

That is worse than an ordinary stride bug because combine is the *return* path: the data being misplaced
is the expert output on its way back to the token's originating rank, so the corruption appears in the
final tensor with no intermediate check between the misplaced write and the model's output.

**The symmetry with dispatch is what makes the omission likely to be missed.** The dispatch block writes
`AlignUp(H * sizeof(dtype), 32)` with an inline `// 32B 对齐` comment. A reader arriving at the combine
block has just seen the pattern with a literal and will read `winAlignBytes` as "the same thing, named".
It may well be 32 — and it may not, since the combine payload is `H_expand`-sized rather than `H`-sized and
a document that wanted the same constant could have written 32 again. The one place the reader would
resolve it is a definition, and there is none.

**The state-slot sentence has the opposite defect and the same cause.** "每个状态槽大小由实现决定，最小为
32B" declares the size implementation-defined with a floor, and two lines later
`stateStrideBytes = 32` fixes it. An agent that reads the prose implements a configurable stride and must
find the value somewhere; an agent that reads the code hardcodes 32 and has silently made an
implementation choice the prose says is open. Both are following the document. This is the rule-stated-then-
violated-in-adjacent-executable-code species this book has recorded twice already — `C-950arch-007` (a 32 KB
DCache minimum stated nine lines before a snippet reserving 128 KB) and `C-950rem-009` (a validation
function named one way and called another) — and the repair is the same: one generator for the rule and the
constant, not a correction to the instance.

**The wait condition carries the third gap.** `targetReadyCount(token) = K + sharedExpertNum   // 无 mask
时` with "有 xActiveMask 或 zero expert 时需相应减少" — reduce accordingly — and no formula. A wait loop
whose target count is too high hangs forever; too low and it proceeds on an incomplete token and produces a
partial sum. Both are silent at build time and the first is the one that holds a multi-card group. Upstream
names the two conditions that change the count and supplies neither adjustment.

**And the combine data region has no triple.** The dispatch token carries `[srcRank, srcTokenIdx,
srcTopKIdx]` alongside its payload (0390) so the receiver knows where the token came from. The combine slot
carries payload only; the addressing information is instead *implicit* in the slot index, via
`srcSlotIdx = srcTopKIdx` for a MoE slot or `K + sharedExpertSlotIdx` for a shared-expert slot. So the
return path's correctness depends entirely on the writer computing the same `srcSlotIdx` the reader will
assume — with no self-describing field to check it against, which is exactly the check the dispatch
direction has.

## 3 · Ground / Source
The combine data block, `window-memory-layout.md:104-133`:

> ## Combine 数据区布局
>
> ### 布局规则
>
> ```
> 排布维度：srcTokenIdx → slotIdx (K + sharedExpertNum slots per token)
> 前 K 个 slot：MoE expert 结果（按 topK 顺序）
> 后 sharedExpertNum 个 slot：共享专家结果
> ```
>
> ### 基础常量
>
> ```c++
> slotCountPerToken    = K + sharedExpertNum
> payloadBytes         = H_expand * sizeof(ExpandXType)
> slotBytes            = AlignUp(payloadBytes, winAlignBytes)
> tokenRegionBytes     = slotCountPerToken * slotBytes
> rankCombineBytes     = BS * tokenRegionBytes
> ```
>
> ### 地址公式
>
> ```c++
> GM_ADDR dataAddr =
>     GetBaseWindAddrByRankId(ctx, dstRank, curRankId)
>     + (uint64_t)srcTokenIdx * tokenRegionBytes
>     + (uint64_t)srcSlotIdx  * slotBytes
> ```
>
> 其中 `srcSlotIdx = srcTopKIdx`（MoE slot）或 `K + sharedExpertSlotIdx`（共享专家 slot）。

The combine state block, `:137-167`:

> ### 布局规则
>
> ```
> 排布维度：srcTokenIdx → slotIdx (同数据区)
> ```
>
> 每个状态槽大小由实现决定，最小为 32B。
>
> ### 基础常量
>
> ```c++
> stateStrideBytes      = 32    // 单个状态槽
> tokenStateRegionBytes = slotCountPerToken * stateStrideBytes
> ```
>
> ### Slot 格式
>
> ```
> slot[0] = readyFlag   (0=未就绪, 1=就绪)
> slot[1..7] = padding
> ```
>
> 等待条件：
>
> ```c++
> // 每个 token 等待自己需要的所有 slot 就绪
> targetReadyCount(token) = K + sharedExpertNum   // 无 mask 时
> // 有 xActiveMask 或 zero expert 时需相应减少
> ```

Note that `slot[1..7]` implies eight words — consistent with 32 bytes and with the dispatch slot's
`STATE_SLOT_INT32 = 8` (0391) — but the combine block names no `STATE_SLOT_INT32` equivalent, so the eight
is inferred from the index range rather than stated. And unlike the dispatch state slot, the combine one
has **no token count**: word 1 is padding where dispatch carries `tokenCount`. That asymmetry is real and
unremarked — the return direction evidently needs no count because the slot count is known from `K`.

The undefined symbols in this block: `winAlignBytes`, `K`, `sharedExpertNum`, `H_expand`, `ExpandXType`,
`BS`, `sharedExpertSlotIdx`, `xActiveMask`. `BS` is shared with the dispatch block and is undefined there
too (0390 §3). `winAlignBytes` is the one that carries a byte quantity and therefore the one whose absence
changes an address.

`:195-199`'s 下一跳 section points onward to `multi-core-formulas.md`, `../api-rules/mte-address-access.md`
and `double-buffer-protocol.md` — three files, of which this harvest read the second. Whether
`winAlignBytes` is defined in either of the other two is unchecked and is Arm A.

Recorded as `C-950rem-012` (the undefined `winAlignBytes`) and `C-950rem-013` (the implementation-defined
state-slot size fixed at 32 two lines later). All quoted material is `upstream/skills-dev-main` — one
origin (RULES.md Art. 3).

## 4 · Procedure
Arm A is a documentation search and needs no device; the rest need at least 2 cards.

Arm A — find the definition. Search the whole upstream tree for `winAlignBytes`, and read
`multi-core-formulas.md` and `double-buffer-protocol.md` — the two 下一跳 files this harvest did not open.
If a definition exists, this entry's central defect is a missing cross-reference rather than an undefined
term, which is the OVERTURN's first clause and a much smaller finding.

Arm B — the observed alignment. With a partner rank writing distinguishable payloads into slots 0, 1 and 2
of one token, dump the combine data region and measure the slot-to-slot stride. Compare against
`AlignUp(payloadBytes, X)` for X in {32, 64, 128, 256, 512}. The X that matches is the real value, and it is
recoverable in one dump. Run at an `H_expand` whose raw payload size is **not** a multiple of any candidate,
so the candidates are distinguishable — with an already-aligned payload every X gives the same answer and
the arm measures nothing.

Arm C — the token stride. Measure the token-to-token distance and compare against `slotCountPerToken *
slotBytes`. This is a separate measurement from Arm B because an implementation could align the token
region as well as the slot, and the formula does not.

Arm D — the state stride and the missing count. Dump the combine state region and measure the slot stride;
confirm word 0 carries the ready flag and words 1-7 are untouched. Then check whether any implementation
writes a count anywhere in the slot — if it does, the padding is not padding and the dispatch/combine
asymmetry §3 records is not real.

Arm E — the wait count under masking. Run one token with `xActiveMask` excluding some experts and record
what `targetReadyCount` must be for the wait to complete. Upstream says 需相应减少 and gives no formula;
the observed value against the mask is the formula. Predicted failure if the unmasked count is used: a
hang, so a watchdog is mandatory.

Device selection is explicit and multi-card: the operator names every card in the group, the harness prints
them back with `compiler/version.info` and each resolved SoC string, occupancy is checked on all of them
before the run (shared machine, ≤4 dies), and no card is substituted between arms. Arm E's predicted
outcome is a hang: a declared watchdog timeout and card release are mandatory, and an un-timed arm is not
permitted on a shared machine.

## 5 · Checker — acceptance declared before the run
`winalign_defined` (Arm A) — true iff a definition is found anywhere upstream. Reported. A true result
reframes the entry; a false result is the finding as written.

`observed_slot_align_bytes` (Arm B) — the X for which `AlignUp(payloadBytes, X)` equals the measured
stride. Reported as a value, not a pass/fail: there is no documented value to pass against, which is the
entry's point. If **no** X in the candidate set matches, the slot is not aligned by `AlignUp` at all and
the formula is wrong in form as well as in constant.

`token_stride_matches_formula` (Arm C) — true iff the measured token stride equals `slotCountPerToken ×
observed slotBytes`. Reported separately from Arm B: a correct slot stride with an unexpected token stride
means the token region carries its own alignment the formula omits.

`state_stride_bytes` (Arm D) — the measured combine state slot stride. Pass iff 32, which would confirm the
hardcoded constant against the implementation-defined prose. Any other value confirms the prose and refutes
the constant, and either way one of the two adjacent statements is wrong.

`masked_target_count` (Arm E) — the count required for completion, against the mask used. Reported as a
(mask, count) pair so a formula can be fitted rather than asserted.

The positive fixture, declared before the run: Arm B must be run at an `H_expand × sizeof(ExpandXType)`
that is **not** a multiple of 32, 64, 128, 256 or 512 — otherwise several candidate X values produce the
same stride and the arm cannot discriminate. This is the fixture, not a detail: an arm run at an
already-aligned payload returns a number that is consistent with every hypothesis, which is the known blind
species — an instrument that cannot distinguish the cases it was built to distinguish. And the dump must
locate payloads by **per-slot distinctive content** (slot *i* filled with the constant `0xA0 + i`), so a
located boundary cannot be confused with a zero region. Without both, the checker reads only "a stride was
measured", which would be an artefact of the chosen shape.

Process exit codes are not the verdict for any arm: Arm E expects a hang.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no combine
slot written, no region dumped, no stride measured, and no card was contacted. The quoted passages are
re-verified file reads of the upstream tree performed during this harvest, as is the observation that
`winAlignBytes` occurs exactly once in the file.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the combine slot's alignment, the token stride,
the state slot's real size, or the masked wait count — Arms A through E are all open.

**It does not establish that `winAlignBytes` is undefined upstream**, only that it is undefined *in this
file* and occurs there once. The file's own 下一跳 section names two further documents this harvest did not
open, and Arm A is the search that would settle it. Treating "undefined here" as "undefined anywhere" would
be the scope error this book exists to refuse.

It does not establish which of the two adjacent state-slot statements holds. "由实现决定，最小为 32B" and
`stateStrideBytes = 32` are one origin contradicting itself two lines apart; Art. 7 forbids resolving that
by preferring the executable line, and Arm D is what would.

It does not establish the masked wait formula. Upstream names two conditions (`xActiveMask`, zero expert)
that reduce the count and supplies no adjustment for either; Arm E would fit one from observation, which is
not the same as recovering upstream's intent.

It does not establish any symbol's value or meaning: `K`, `sharedExpertNum`, `H_expand`, `ExpandXType`,
`BS`, `sharedExpertSlotIdx` and `xActiveMask` are all used and undefined in this file, so the formulas are
dimensionally checkable and not evaluable from it.

It says nothing about the dispatch regions (0390, 0391), about the base address the formulas start from
(0389), or about the 1 MB state offset (0277).

**The asymmetry noted in §3 — that the combine slot carries no source triple and no token count — is an
observation about the document, not about any implementation.** Whether a real combine kernel writes
identifying information somewhere is Arm D's second half and is unrun.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board was
contacted.

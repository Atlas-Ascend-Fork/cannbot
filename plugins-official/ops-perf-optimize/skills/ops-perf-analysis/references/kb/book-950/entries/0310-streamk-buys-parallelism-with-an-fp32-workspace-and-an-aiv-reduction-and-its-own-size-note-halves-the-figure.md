```
ID:        0310-streamk-buys-parallelism-with-an-fp32-workspace-and-an-aiv-reduction-and-its-own-size-note-halves-the-figure
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/streamk_design.md:127-129 —
           "GetWorkSpace() = aicNum * BLOCK_BASE_M * BLOCK_BASE_N * sizeof(FP32)   // 部分和累加空间
                           + RPC_WORKSIZE * MB_SIZE                                // 跨核通信"
SOURCE:    same file:275 — "2. **Workspace 容量开销**：约 `aicNum × 128KB = 3MB+`（FP32），需确认
           HBM 预算。" ; :90-91 — "constexpr uint16_t BLOCK_BASE_M = 256;  // L0/workspace 对齐粒度
           / constexpr uint16_t BLOCK_BASE_N = 256;" ; :276 — "**精度影响**：SK 路径的部分和在
           workspace 用 FP32 保存，AIV 归约完成后再 cast 回 FP16/BF16，**精度等价或优于**纯 FP16
           归约（减少了中间 round）。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a StreamK build on a named 950 board whose actual workspace request, read back from the
           runtime, is `aicNum × 131072` bytes plus the RPC term — the formula at `:127` would then
           be wrong and the `128KB` note right. Independently: a measured SK result that is *less*
           accurate than a pure-FP16 reduction on the same shape kills the precision claim.
```

# 0310 · StreamK buys parallelism with an FP32 workspace and an AIV reduction, and its own size note halves the figure

## 1 · Claim
Upstream asserts that StreamK's K-splitting requires a GM workspace that the other matmul strategies
do not: each AIC core writes an FP32 partial sum of one `BLOCK_BASE_M × BLOCK_BASE_N` tile, and AIV
cores afterwards read the `kCnt` partial sums of one MN tile, add them, cast to FP16/BF16 and write
C. Upstream asserts the size formula
`GetWorkSpace() = aicNum × BLOCK_BASE_M × BLOCK_BASE_N × sizeof(FP32) + RPC_WORKSIZE × MB_SIZE`,
with `BLOCK_BASE_M = BLOCK_BASE_N = 256` declared as constants in the same file. Upstream asserts a
precision consequence: keeping partials in FP32 and casting once at the end is `精度等价或优于` a
pure FP16 reduction. Upstream asserts a size estimate in its constraints section —
`约 aicNum × 128KB = 3MB+` — which does not follow from its own formula: `256 × 256 × 4 = 262144`
bytes, that is 256 KiB per core, twice the stated 128 KB. Not established here.

The `3MB+` total is unattributable in either reading, because `aicNum` is never given a value in the
file: at 256 KiB/core it is 3 MB only if `aicNum = 12`, and this book's own record of installed 950
SKUs (`950:0217`) lists cube-core counts of 4, 8, 28, 32 and 36, none of them 12.

## 2 · The wrong branch this removes
An agent budgeting HBM for a StreamK kernel takes the `128KB` note because it is the sentence
written in the "注意事项" section, where budgets are supposed to live, and provisions half of what
the formula asks for. The failure is not a compile error — the workspace is requested at launch —
so it surfaces as an allocation failure at run time on a loaded device, or not at all on an idle
one, which is the worst of both.

The second wrong branch is treating StreamK's workspace as free because "it is only workspace".
Upstream places it against HBM explicitly (`需确认 HBM 预算`), and the requirement scales with
`aicNum` — so the same kernel that fits on a 4-cube-core SKU asks for nine times as much on a
36-core one. A budget checked on the small part and shipped is a budget that was never checked.

The third, and the one that changes a design decision: the workspace is the reason StreamK is
mutually exclusive with A/B-Full-Load (`0311`) and is *not* stacked with scale coalescing
(`0313`). An agent that reads the mutual exclusions as arbitrary policy will try to combine them;
they are consequences of the K-split having moved the accumulation off-chip.

## 3 · Ground / Source
The formula, `streamk_design.md:126-129`:

```
GetWorkSpace() = aicNum * BLOCK_BASE_M * BLOCK_BASE_N * sizeof(FP32)   // 部分和累加空间
               + RPC_WORKSIZE * MB_SIZE                                // 跨核通信
```

The constants it is built from, `:90-91`:

```cpp
constexpr uint16_t BLOCK_BASE_M = 256;                        // L0/workspace 对齐粒度
constexpr uint16_t BLOCK_BASE_N = 256;
```

The note that disagrees with it, `:275`:

```
2. **Workspace 容量开销**：约 `aicNum × 128KB = 3MB+`（FP32），需确认 HBM 预算。
```

Re-derived: `256 × 256 × 4 = 262144 B = 256 KiB`. The note says 128 KB. The defensible statement is
narrow and is the one this entry makes: **the note contradicts the formula stated 148 lines above
it in the same file, by a factor of two.** The `3MB+` figure is not evaluated here because `aicNum`
is unbound — claiming "the budget is understated 2×" would require knowing which of the two the
implementation uses, and reading cannot tell. Recorded as `C-950bp-004`.

`RPC_WORKSIZE` and `MB_SIZE` are named and never defined anywhere in the family. `950:0111` records
the same two symbols undefined in the analysis shelf's matmul budget formulas — the same repo, so
one origin, and this is the second place the same undefined pair carries an additive term in a
capacity request. Owed in `harvest/standing/950-bp.md`.

The per-core write offset, `:134-136`, which is what makes the per-core sizing correct:

```cpp
offsetWorkspace = (((tileIdx % usedCoreNum) / skKTileNum) * skKTileNum
                  + Get<MNK_K>(singleCoreCoord))
                  * BLOCK_BASE_M * BLOCK_BASE_N;
```

Upstream discloses the corresponding defect, `:288-297`: computing this offset from the global
`tileIdx` instead of the last round's MN index produces `精度校验失败，输出的 C 矩阵某些 tile 全 0
或重复叠加`. That is a wrong-answer mode, not a capacity mode, and it belongs to the same field.

The precision claim, `:276`:

```
3. **精度影响**：SK 路径的部分和在 workspace 用 FP32 保存，AIV 归约完成后再 cast 回 FP16/BF16，
   **精度等价或优于**纯 FP16 归约（减少了中间 round）。
```

Measured/inferred split at sentence level: **nothing here is measured**. The formula is source, the
`128KB` note is prose, the precision claim is an argument from rounding counts with no error figure
attached, and the `3MB+` is arithmetic on an unstated `aicNum`.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — what is actually requested. Build a StreamK kernel at an admitted shape (`0309`) and read
the workspace size the runtime is asked for, from the host tiling context, echoed to stdout together
with the queried `aicNum` and the resolved SoC string. Compare against both candidates:
`aicNum × 262144 + RPC` and `aicNum × 131072 + RPC`. This is a `[no-card]`-adjacent arm in spirit —
it needs a build but not a timed run — and it settles the numeric half outright.

Arm 2 — the terms nobody defines. Sweep `aicNum` (by restricting visible cores) and fit the observed
request against `a × aicNum + b`. `a` recovers the per-core term; `b` recovers
`RPC_WORKSIZE × MB_SIZE`, which no document gives. Two points suffice; four are taken.

Arm 3 — the precision claim, which is the half a size check cannot reach. On one SK-admitted shape,
build three variants: SK with FP32 workspace (shipped), SK with an FP16 workspace, and the SWAT
baseline that never leaves L0C. Compare all three elementwise against an FP64 CPU reference and
report max absolute error and max relative error for each. Upstream's claim predicts
FP32-SK ≤ SWAT ≤ FP16-SK in error. The FP16-workspace arm is the one that can bite, and it is
retained whatever it shows.

Arm 4 — the disclosed offset defect, reproduced deliberately. Build with
`offsetWorkspace = tileIdx * BLOCK_BASE_M * BLOCK_BASE_N` and confirm the described symptom (zeroed
or doubly-accumulated tiles). This arm exists to give Arm 3's correctness check something it must
catch; see §5.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after; discard the case
if the die moved. Refuses to assume: that a free die stays free; that a die may be substituted; that
`aicNum` is a literal — it is queried (`950:0207`) and echoed beside every workspace figure, because
the whole formula is linear in it; that the request the host makes is the allocation the runtime
performs (both are recorded, and a difference is a finding).

## 5 · Checker — acceptance declared before the run
Verdict `ws_per_core` = `(request − b) / aicNum` from Arms 1–2, in bytes. Declared before the run
with both outcomes named: `ws_per_core == 262144` means the formula governs and the `128KB` note is
wrong; `ws_per_core == 131072` means the note governs and the formula is wrong. Any third value
means both documents are wrong and the entry is corrected in place. There is no outcome under which
the current text is fully right, which is what makes this contradiction worth a slot.

Verdict `rpc_term` = `b`, reported unconditionally — it is the first value anyone has for
`RPC_WORKSIZE × MB_SIZE`.

Verdict `err_ordering` = true iff Arm 3's max relative errors satisfy
`FP32-SK ≤ SWAT` and `FP32-SK < FP16-SK`. `false` on the second half overturns the precision claim's
comparative form.

The exit code is not the verdict. Three guards. First, Arm 3's correctness comparison is against an
FP64 reference, not against SWAT — comparing two NPU builds to each other cannot detect an error
they share. Second — the input that makes this checker go red — Arm 4's deliberately broken offset
**must** be reported as a precision failure by the same comparison Arm 3 uses. If Arm 4 passes,
Arm 3's correctness arm is not reading the output tiles it claims to, and every green from it is
void. That is a planted positive the checker has to find, and it is available for free because
upstream published the defect. Third, `ws_per_core` is reported with the queried `aicNum` beside it;
a workspace figure without its core count is the exact shape of the `3MB+` statement this entry
declines to evaluate.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `256 × 256 × 4 = 262144` is
arithmetic performed here on paper against upstream's own constants; no build has requested a
workspace, no runtime has reported one, and no error figure exists for any of the three precision
variants.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry establishes that two statements in one upstream file
disagree by a factor of two; it does **not** establish which is implemented, and it deliberately
does not claim the budget is understated, because that would require knowing which the code uses.
The `3MB+` total is not evaluated: `aicNum` is unbound in the source and no installed 950 SKU this
book records has 12 cube cores (`950:0217`). `RPC_WORKSIZE` and `MB_SIZE` are undefined in both
upstream shelves and are treated here as an unknown additive constant, not as zero. The precision
claim is an argument about rounding counts with no error figure anywhere in the file, so nothing
here establishes that FP32 partials are more accurate — only that upstream says so and why. Nothing
establishes StreamK's *benefit*; upstream gives no timing for it at any shape. BOARD is
`family-claimed(unverified)`: no file in this family names a chip (`0347`). Nothing transfers to the
other book (RULES.md Art. 1).

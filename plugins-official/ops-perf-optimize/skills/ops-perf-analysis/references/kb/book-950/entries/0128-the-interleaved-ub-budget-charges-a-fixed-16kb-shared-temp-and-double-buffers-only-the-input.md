```
ID:        0128-the-interleaved-ub-budget-charges-a-fixed-16kb-shared-temp-and-double-buffers-only-the-input
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:452-503 —
           "常量取自 host tiling：`tmp`(共享 Reduce 临时区)=16KB，`DB`(double buffer)=2，
           `dtypeSize`=4(fp32)/2(fp16,bf16)。acc/red/tmp/part 恒为 fp32；inQ/outQ 用 D_T 精度。" ·
           "chunkA0 = (ubSize - fixedIndep) / perA0，clamp 到 [1, A0]" ·
           "chunkR0 = (ubSize - fixedBytes) / (2 × innerRowElems × dtypeSize)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured interleaved case on a named 950 board where a chunk sized at the budget's
           limit overflows UB, or where the 16 KB shared temp is demonstrably not allocated — the
           budget's fixed term would then be wrong and every interleaved chunk size with it.
```

# 0128 · The interleaved UB budget charges a fixed 16 KB shared temp and double-buffers only the input

## 1 · Claim
Upstream asserts a UB budget for the two interleaved templates that is structurally different from
the five templates'. Its constants, taken from the host tiling: a shared Reduce temporary region
fixed at 16 KB (`kCacheBufBytes`), a double-buffer factor of 2, and `dtypeSize` 4 for fp32 and 2
for fp16/bf16 — with the accumulator, the step-1 intermediate, the temp and the partial sum always
FP32 regardless of operand dtype, while the input and output queues use the operand precision.
For tail-R, upstream asserts `fixedIndep = 16384 + CeilAlign(outLanes, 8) × 4 × 2` and a
per-`chunkA0` cost `perA0 = 2×sliceStride×dtypeSize + sliceStride×4 + R0×A1×4 + R0×4 + 4`, giving
`chunkA0 = (ubSize − fixedIndep) / perA0` clamped to `[1, A0]`, with leftover UB spent on raising
`rowsPerLoad` to enlarge the burst, clamped to `[1, min(8, rows axis length)]`. For tail-A,
`fixedBytes = innerRowElems×4 + 16384 + R1×A1×4 + CeilAlign(outLanes,8)×4×2` and
`chunkR0 = (ubSize − fixedBytes) / (2 × innerRowElems × dtypeSize)` clamped to `[1, min(R0, 8)]`,
with `usedCoreNum = min(slabCnt, coreNum)` and `workspace = 0`. Not established here.

## 2 · The wrong branch this removes
An agent that reuses the five-template budget for an interleaved case gets the wrong answer in
three independent ways. First, the shared temp: 16 KB fixed versus the five templates' computed
`tmp_buf_size` with a 4096 B floor (0129) — a 4× difference on a term that is subtracted before the
division, and at small chunk counts that changes the chunk. Second, the double-buffer factor
applies to the input queue only (`2×sliceStride×dtypeSize` for `inQ`), not to every buffer, whereas
the five-template budgets fold `×2` into both input and output; an agent that copies that habit
over-charges the output side and under-sizes the chunk. Third, the dtype rule is mixed: `acc`,
`red`, `tmp` and `part` are FP32 always, `inQ`/`outQ` follow the operand — so an fp16 case does not
halve its budget, it halves only part of it. An agent that scales the whole budget by `dtypeSize`
will be wrong by a factor that depends on the shape.

The `rowsPerLoad` leftover rule removes a fourth wrong branch: treating surplus UB as headroom.
Upstream spends it on burst size, which is the quantity the whole template exists to enlarge (0126)
— surplus UB that is not converted into burst is surplus that buys nothing.

## 3 · Ground / Source
`reduction/fallback/tiling-flow.md:452-503`, §12 in full:

```
> 常量取自 host tiling：`tmp`(共享 Reduce 临时区)=16KB，`DB`(double buffer)=2，`dtypeSize`=4(fp32)/2(fp16,bf16)。acc/red/tmp/part 恒为 fp32；inQ/outQ 用 D_T 精度。

### 12.1 tail-R（fast）—— 求内块分块 chunkA0（`TryComputeFastTiling`）

记内块 [A0,R0,A1,R1]（轴 S..N-1，S=axisNum-4）:
  sliceStride = R0 × A1 × R1           // 一个 A0 面的元素数
  outLanes    = A0 × A1                // 输出通道数
  innerElems  = A0 × R0 × A1 × R1      // 内块总元素（连续性校验 axisStride[S-1]==innerElems）

固定开销（与 chunkA0 无关）:
  fixedIndep = 16384 + CeilAlign(outLanes, 8) × 4 × 2   // tmp(16K) + part + outQ(fp32)

与 chunkA0 成比例的每单位字节:
  perA0 = 2×sliceStride×dtypeSize   (inQ, DB=2, D_T)
        + sliceStride×4             (acc, fp32)
        + R0×A1×4                   (step1 中间 red, fp32)
        + R0×4                      (step2 plane，保守预留)
        + 4                         (dstA4，保守预留)

chunkA0 = (ubSize - fixedIndep) / perA0，clamp 到 [1, A0]

★ 命中门控（全满足才用，否则回退五模板）:
    innerElems×dtypeSize % 32 == 0      // 连续 DataCopy 32B 对齐
    R1×dtypeSize ≤ 16                   // ★ burst 病态判据
    rowsSize ≥ 8                        // ★ rows 太小则两步规约+屏障反超增益
    chunkA0 == A0                       // 内块整块放得下（无需分块）
    groupCnt = ∏(外层A轴) ≤ coreNum
   余量提 rowsPerLoad（增大 burst）: rowsPerLoad += 剩余UB / (2×chunkElems×dtypeSize)，clamp [1, min(8, rows轴长)]

### 12.2 tail-A（fast-RARA）—— 求内块分块 chunkR0（`TryComputeFastRARATiling`）

记内块 [R0,A0,R1,A1]（轴 S..N-1，S=axisNum-4）:
  innerRowElems = A0 × R1 × A1        // 固定 R0 的一行（连续性校验 axisStride[S]==innerRowElems）
  outLanes      = A0 × A1

固定开销:
  fixedBytes = innerRowElems×4         (acc, fp32)
             + 16384                   (tmp)
             + R1×A1×4                 (plane)
             + CeilAlign(outLanes,8)×4×2   (part + outQ, part fp32 / outQ D_T)

chunkR0 = (ubSize - fixedBytes) / (2 × innerRowElems × dtypeSize)   // DB=2，clamp 到 [1, min(R0, 8)]

★ 命中门控: innerRowElems×dtypeSize % 32 == 0  (32B 对齐)
            slabCnt = ∏(外层A轴) ; slabCnt×2 ≥ coreNum ; innerRowElems ≥ 512
   usedCoreNum = min(slabCnt, coreNum)  ; workspace = 0
```

The explicit comparison against the five-template budgets, `:505-513`:

```
| 项 | 五模板 | 交错模板 |
|----|--------|---------|
| 分块对象 | R（FullLoad/Recompute） | 内块 A0（tail-R）/ 内块 R0（tail-A） |
| 载入方向 | 转置聚 R | 内存物理连续，大 burst（连续 `DataCopy`，非 `DataCopyPad`） |
| dtype | 任意 | fp32/fp16/bf16（载入即升 fp32，int32 不走 fast） |
| 共享临时区 | tmp_buf_size ≥ 4096 | 固定 16KB（`kCacheBufBytes`） |
| 跨核合并 | 二分累加 / Group workspace | tail-R workspace 两段式（coresPerGroup==1 免）；tail-A 无 |
```

Two of the five `perA0` terms are annotated `保守预留` (conservative reservation) by upstream
itself — `R0×4` for the step-2 plane and a bare `4` for `dstA4`. Upstream is disclosing that its own
budget over-charges by an unquantified amount, which is honest and also means the computed
`chunkA0` is a lower bound rather than the true capacity limit. Under 0104's rule, `16384`, the
`CeilAlign(…, 8)` granularity, the `min(8, …)` clamps on `rowsPerLoad` and `chunkR0`, and both
conservative reserves are hardcoded literals — software 经验值, searchable — while `ubSize` is a
chip specification field and is not.

Note the interaction with the gate: `chunkA0 == A0` is a hit condition (0125), and `chunkA0` is
computed by this budget. So the budget does not merely size the chunk — it decides whether the
template is used at all, and case #17 fell back precisely because the budget returned
`chunkA0 = 14 < A0 = 32` (0127). Any error in this formula therefore shows up as a routing error,
not as a sizing error.

The field names these values populate are in `reduction/fallback/tiling-fields.md:65-76`:
`fastInnerStart`, `fastGroupCnt`, `fastCoresPerGroup`, `fastRowsAxisIdx`, `fastRowsPerLoad`
(`一次载入的 rows 行数（增大 burst，≤8）`), `fastInnerChunkA0` (`命中要求 == szA0`), `raraSlabCnt`,
`raraChunkR0` (`≤ min(R0,8)`), and `workspace_size` = `tail-R = groupCnt×coresPerGroup×outLanes×4;
**tail-A = 0**`. Two symbols in that table are used without definition anywhere in the family:
`szA0` (which context makes the inner block's A0 extent, i.e. the same thing as `A0` in §12.1) and
`outLanes` in the `workspace_size` row (defined in §12.1 but not in the field table).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Budget-tightness test on both templates. For tail-R take case #18's shape; for tail-A take #11's.
Read `ubSize` at runtime and print it. Evaluate the budget by hand and compare against the host
echo of `fastInnerChunkA0` / `raraChunkR0` — a disagreement here is a finding before any kernel
runs. Then build three points per template: at the computed chunk, at chunk+1, and at the chunk the
budget would give with the two `保守预留` terms removed (tail-R only). One compiler pin, md5 per
binary, host echo of every interleaved field, fp64 reference check within a tolerance declared in
advance, `aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped,
per case, reported against 0126 arm 0's variance floor.

Second arm — the 16 KB temp. Build one tail-R case with the fixed term set to 4096 (the five
templates' floor) instead of 16384 and record whether it runs correctly. If it does, the 16 KB is
not required at this shape and the surplus is quantified as `(16384 − 4096) / ubSize`.

Third arm — `rowsPerLoad`. Sweep it over `[1, min(8, rows)]` at #18's shape and record `aiv_time`
and the measured burst at each, so the leftover-UB rule is shown to buy burst and the burst is
shown to buy time — two links that are asserted separately and measured together.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` is
192 KB or 248 KB (0131 — it is queried and printed); that a chunk that builds is the chunk that ran
(echo required); that removing a conservative reserve is safe — arm 1's third point is expected to
be the one that fails, and it is retained whether it fails or not.

## 5 · Checker — acceptance declared before the run
Verdict variable `chunk_tight(template)`: true iff the at-budget point runs correctly and the
chunk+1 point fails. Declared acceptance: the budgets are correct as written iff `chunk_tight` holds
for both templates. The OVERTURN fires iff an at-budget point fails — the formula under-charges, and
because `chunkA0 == A0` is a routing gate, an under-charging formula also mis-routes. A second
verdict `reserve_surplus` = (largest working chunk) / (formula chunk), reported as a number; a value
above 1.0 quantifies the two disclosed conservative reserves and is expected, not a defect.

The exit code is not the verdict. The blind mode is clamping: `chunkA0` is clamped to `[1, A0]` and
`chunkR0` to `[1, min(R0,8)]` by the formula itself, so a chunk+1 request may be silently clamped
back and run correctly, which would score `chunk_tight = false` for a boundary never crossed. The
host echo of the actual chunk is therefore compared against the request at every point, any
mismatch marks the point `clamped`, and the checker goes red rather than issuing a verdict when a
point is clamped. Second guard: the printed `ubSize` must be identical between the hand evaluation
and the run, since the whole budget is a function of it.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the 16 KB shared temp, the `min(8, …)` clamps, or
either conservative reserve — all are literals with no derivation. It does not establish `ubSize`
for any board, and both budgets are functions of it (0131). It does not establish that the budget's
`chunkA0` matches what the shipped host tiling computes; upstream gives the formula and names the
function, and this book has compared neither. It does not resolve `szA0`, used in the field table
without definition. It does not cover the five-template budgets (0123) or BlockSplitR's workspace
(0124), which are different formulas with different reserves. `arch35` names a family, not a board,
so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would
happen. Nothing here is established for any 910-family board.

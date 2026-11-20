```
ID:        0148-the-gather-simd-thresholds-are-four-underived-byte-counts-and-the-real-cost-gate-lives-outside-this-skill
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/gather/fallback/tiling-flow.md:144-151,142 —
           "| int8 | 1 (or improved) | 218 | / | int16 | 2 (or improved) | 360 | / | int32 |
           4 (or improved) | 620 | / | int64 | 8 | 2048 |" · "以上只判断内部模板能否生成 UB tiling。
           调用前还必须通过 API 上游能力与 workspace 成本门控；`needTrans=true` 不表示内部 Transpose
           全局最优。完整门控参考最佳实践库的 `reference/gather/templates/gather_elements_v2_route.template`。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep of `innerSize × dtypeSize` across each of the four thresholds on a named
           950 board showing the SIMD and SIMT templates cross over at a materially different byte
           count — the table would then be miscalibrated for this board, and every gather routed by
           it inherits the error.
```

# 0148 · The gather SIMD thresholds are four underived byte counts, and the real cost gate lives outside this skill

## 1 · Claim
Upstream asserts a four-row threshold table deciding when a gather is wide enough for the SIMD
vectorised templates rather than the SIMT scalar ones, expressed as a minimum
`innerSize × dtypeSize`: 218 for int8, 360 for int16, 620 for int32, 2048 for int64. Upstream gives no
derivation, no measurement, no case identity and no board for any of the four. Upstream separately
asserts that the UB feasibility test it does give for the internal-transpose path decides only
whether a UB tiling can be generated, that an upstream API capability gate and a workspace cost gate
must both pass before the call, that `needTrans = true` does not mean the internal transpose is
globally optimal, and that the complete gate set lives in a different skill —
`reference/gather/templates/gather_elements_v2_route.template` in the performance-best-practices
library. Not established here.

## 2 · The wrong branch this removes
Three thresholds are non-round numbers — 218, 360, 620 — which is the signature of calibration rather
than of a hardware boundary, and the fourth (2048) is a power of two, which reads like one. An agent
meeting the table has no way to tell them apart, and the two kinds behave differently under the
provenance rule (0104): a calibrated number is a software 经验值 that a search may cross, while a
capability boundary is not. Under that rule all four trace to literals in a markdown table with no
chip-configuration chain, so all four are searchable — and the honest consequence is that a tuner
should enumerate around them rather than obey them.

The ratios are worth reading because they do not follow a single rule. 218 → 360 is ×1.65,
360 → 620 is ×1.72, and 620 → 2048 is ×3.30. So the first three scale sublinearly with element width
while the fourth jumps. An agent that interpolates a missing dtype — bf16, fp16, fp32, all absent from
this table despite being the dtypes the transpose path supports (`当前 dtype 仅
fp16/bf16/fp32/int32`, `:336`) — will pick the wrong side of the pattern. The table is indexed by
integer dtypes only, and the family's own supported-dtype list is floating-point-heavy. That gap is
the wrong branch this entry most needs to remove: there is no threshold row for fp16, fp32 or bf16,
and an agent will substitute the same-width integer row without any statement that width is the only
thing that matters.

The out-of-skill gate is a different kind of trap. `needTrans = true` is computable from this document
alone, and an agent that stops there has a plan that satisfies the only test it can see while failing
two it cannot. Upstream says so plainly and names the file; that file is in a sibling skill, which
means this reference is not self-sufficient for the path it documents most thoroughly.

## 3 · Ground / Source
The threshold table, `gather/fallback/tiling-flow.md:144-151`, in full:

```
### SIMD 阈值（按 dtype）

| dtype | improveDtypeSize | SIMD 阈值 (innerSize × dtypeSize) |
|-------|------------------|-----------------------------------|
| int8  | 1 (or improved)  | 218                               |
| int16 | 2 (or improved)  | 360                               |
| int32 | 4 (or improved)  | 620                               |
| int64 | 8                | 2048                              |
```

The gates that consume it, `:90-94` and `:106-109`:

```
├─ gatherMode == PER_SLICE && batchSize==1 && outerSize==1（2D 场景）
│   && innerSize × improveDtypeSize ≥ SIMD 阈值（按 dtype 分级）
│   && batchSize*outerSize*gatherSize ≥ coreNum/2
│     → 【SIMD 两维】gatherSize 分核，innerSize 行向量化搬运
```
```
├─ gatherMode == PER_SLICE && innerSize × improveDtypeSize ≥ SIMD 阈值
│   && UB ≥ 2 × INDICES_SIZE(8KB) && batchSize*outerSize*gatherSize ≥ coreNum/2
│     → 【SIMD 行拷贝】逐输出行 DataCopyPad innerSize 元素，index 缓存
```

Note the quantity mismatch: the table's column header is `innerSize × dtypeSize` while both gates
test `innerSize × improveDtypeSize`. After `Dtype Improve` (0147) those are equal by construction —
`innerSize_improved × improveDtypeSize = innerSize × dtypeSize` — so the two forms agree in bytes,
but only if the gate uses the *improved* `innerSize`. The decision tree's input list at `:63` carries
both `innerSize` and `improveDtypeSize` without saying which `innerSize` the gate means. Read one way
the gate is a byte count; read the other it is off by the improvement factor, up to 8×. Registered as
C-950tiling-022.

The out-of-skill gate, `:142`:

```
> 以上只判断内部模板能否生成 UB tiling。调用前还必须通过 API 上游能力与 workspace 成本门控；`needTrans=true` 不表示内部 Transpose 全局最优。完整门控参考最佳实践库的 `reference/gather/templates/gather_elements_v2_route.template`。
```

and restated as a routing consequence, `:167`:
`当 dim!=last 时把物理/内部 Transpose 列为候选，按上述门控选择；不要把内部 Transpose 当默认路径。`

The internal-transpose UB test the sentence qualifies, `:118-140`:

```
CACHELINE = 512  // 字节
TRANSPOSE_WS_LEN = 128  // 转置窗口长度

carryNumAlign = CACHELINE / dtypeSize
availableUb = ubSize - 2048

// Transpose buffer (固定)
transInBufferSize  = TRANSPOSE_WS_LEN * CACHELINE   // 64KB
transOutBufferSize = TRANSPOSE_WS_LEN * CACHELINE   // 64KB

// Gather buffer (转置后做末轴 gather)
gatherInBufferSize  = CeilAlign(gatherDimSize, xAlign) * dtypeSize
                    + CeilAlign(minIdxSlice, idxAlign) * sizeof(int32) * 2
gatherOutBufferSize = CeilAlign(minIdxSlice, xAlign) * dtypeSize

inBufferSize  = max(gatherInBufferSize, transInBufferSize)
outBufferSize = max(gatherOutBufferSize, transOutBufferSize)

needTrans = availableUb >= (inBufferSize + outBufferSize)
```

`128 × 512 = 65536` = 64 KiB, so the two fixed transpose buffers together demand 128 KiB before any
gather buffer is counted — which upstream states directly at `:337`
(`UB 够容纳 transpose buffer (128KB) + gather buffer`). Against a UB in the 192–248 KB range (0131,
0140) that is over half the capacity spent on a fixed pair of buffers, which is why the `needTrans`
test is usually the binding one.

Four symbols in that block are never defined in the family: `xAlign`, `idxAlign`, `minIdxSlice`, and
the `2048` subtracted from `ubSize` (a reserve with no stated purpose). Two more appear in the other
budgets: `MIN_OUT_UB` at `:211` and `MIN_INDICES_UB` at `:228`, both used in gates with no values.
`INDICES_SIZE` is given inline as 8 KB at `:107` and `:253`, and `DCache` is given inline as 128 KB at
`:237` — the only place in this domain where a data-cache size is stated, and it is stated in
parentheses inside a gather template's condition. Recorded in `harvest/standing/950-tiling.md`.

The family's own field document, which would define these symbols, does not exist:
`gather/fallback/index.md:10` links `tiling-fields.md（规划中）` and `gather/index.md:13` instructs
the reader to open it. It is the only family in this domain missing that file, and a prior survey
recorded the broken link; re-reading the directory confirms the absence. Registered as
C-950tiling-023.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Threshold ladders, one per dtype row plus the three missing float dtypes. For each of int8, int16,
int32, int64, fp16, fp32 and bf16, fix a `PER_SLICE` case with `batchSize = outerSize = 1` and
`gatherSize` large enough to satisfy `≥ coreNum/2`, and sweep `innerSize × dtypeSize` over
{0.25, 0.5, 0.8, 1.0, 1.25, 2, 4} × the tabled threshold (using the same-width integer row as the
nominal threshold for the float dtypes, and recording that substitution as an assumption). At every
point build both the SIMD row-copy template and the SIMT scalar template, one compiler pin, md5 each,
host echo of `innerSize`, `improveDtypeSize`, the byte product the gate actually evaluated, and the
selected template. Compare output elementwise against a CPU reference on both arms. Record `aiv_time`
and MTE2 operation count under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped, per case.

Improvement-ambiguity arm, which settles C-950tiling-022: run two int8 cases with the same
`innerSize × dtypeSize` in bytes but different `improveDtypeSize` (one where `innerSize` is a multiple
of 8, one where it is not) and record which side of the gate each lands on. If the gate uses the
un-improved `innerSize` the two differ by up to 8×.

`needTrans` arm: with UB queried at runtime (0141), evaluate the transpose test by hand and against
the host echo, then build the internal-transpose path at a case where `needTrans` is marginally true
and at one where it is marginally false, plus the physical-transpose and SIMT alternatives at both, so
`needTrans=true 不表示全局最优` becomes a measured statement rather than a caution.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` or
`ubSize` are literals; that the float dtypes share the integer thresholds (that substitution is
recorded as an assumption and the sweep is what tests it); that a forced template was used (host echo
required); that the out-of-skill cost gate is unavailable — if the named template file can be read,
its gates are recorded as a separate origin and reported, and if not, that absence is reported.

## 5 · Checker — acceptance declared before the run
Verdict variable `simd_cross(dtype)`: the `innerSize × dtypeSize` at which SIMD's median `aiv_time`
first falls below SIMT's by more than the variance floor. Declared before the run: each tabled
threshold is supported iff `simd_cross ∈ [0.5, 2.0] × table value`. The OVERTURN fires iff any
`simd_cross` falls outside `[0.25, 4.0] ×` its tabled value — the row is then miscalibrated for this
board by more than a factor of four in one direction. For the three float dtypes there is no tabled
value, so `simd_cross` is reported as a new measurement rather than as a check, and that is stated in
the result. Verdict `gate_uses ∈ {improved, raw}` from the improvement arm. Verdict
`needtrans_optimal`: true iff the internal transpose is fastest at every case where `needTrans` is
true; upstream predicts false, and a true result would mean the caution is unnecessary.

The exit code is not the verdict: a gather with wrong indices exits 0. The elementwise comparison runs
on every arm and the checker fails red if it did not. Second guard, the one that keeps the ladder
honest: at every rung both templates must be shown to have been built and run — two distinct md5s and
two distinct echoed template names — because a host that refuses SIMD below its own threshold would
produce a crossover read off refusals rather than off timings, which would confirm the table by
construction. Rungs with only one arm are reported as untestable, not as agreement.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 218/360/620/2048 figures
are upstream's, with no derivation, case identity, tool or board attached.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish any of the four thresholds, does not establish that
they are calibrated rather than architectural, and does not supply the three missing float dtype rows
— it records their absence. It does not resolve whether the gate evaluates improved or raw `innerSize`
(C-950tiling-022). It does not establish `xAlign`, `idxAlign`, `minIdxSlice`, `MIN_OUT_UB`,
`MIN_INDICES_UB`, the 2048 UB reserve, the 8 KB `INDICES_SIZE`, or the 128 KB `DCache` figure — all
are literals or undefined symbols in this family. It does not reproduce the out-of-skill capability and
workspace cost gates, which live in a sibling skill and are outside this domain's scope; without them
this family's routing is documented but not complete. It does not establish the missing
`tiling-fields.md` (C-950tiling-023). No chip is named anywhere in the gather family, so BOARD is
`family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT because that is where our
run would happen. Nothing here is established for any 910-family board.

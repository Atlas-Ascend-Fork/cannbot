```
ID:        0149-a-non-last-axis-per-element-gather-turns-scattered-reads-into-a-three-stage-transpose-inside-one-kernel
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/gather/fallback/tiling-flow.md:320-339,77-88,
           193-197 — "对固定的 (o, c)，x 沿 gather 轴的 GD 个元素虽然物理上不连续（stride=innerSize），
           但可以用 `DataCopyPad(srcStride=innerSize)` 跨步 DMA 加载到 UB，再用 `TransDataTo5HD` 在
           UB 内做矩阵转置使其连续" · "不在 framework 层做 3 次独立 Transpose kernel，而是在 **1 个
           kernel 内的 3 个阶段**完成（Transpose → Gather → ReTranspose），用 workspace GM 中转，
           无额外 kernel launch 开销。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured non-last-axis PER_ELEMENT gather on a named 950 board where the SIMT scalar
           fallback matches or beats the in-kernel transpose path on a case that passes every stated
           capability, UB and cost gate — the three extra data movements would then not pay for
           themselves where upstream says they do.
```

# 0149 · A non-last-axis PER_ELEMENT gather turns scattered reads into a three-stage transpose inside one kernel

## 1 · Claim
Upstream asserts a specific transformation for `torch.gather`-style indexing on a non-last axis. In
`y[o, g, c] = x[o, index[o,g,c], c]`, for a fixed `(o, c)` the `gatherDimSize` elements of x along the
gather axis are physically non-contiguous with stride `innerSize`, but can be loaded into UB by strided
DMA (`DataCopyPad(srcStride=innerSize)`), made contiguous there by `TransDataTo5HD`, and written to
workspace GM; the x rows are then read back sequentially and gathered by vector instruction into
workspace; and the result is re-transposed and written back with strided DMA. Upstream asserts that
this is done as three stages inside one kernel rather than as three independent framework-level
transpose kernels, so there is no extra launch overhead. Upstream asserts the routing position: this
path is a candidate only for `PER_ELEMENT` with `dim != last`, is gated by capability, UB and cost
tests, and is explicitly not the default — `不要把内部 Transpose 当默认路径`. On any gate failure the
order is: physical transpose ×3 plus last-axis gather, then Scalar/SIMT. Not established here.

## 2 · The wrong branch this removes
The wrong branch is the one the mechanism argument invites: `dim != last` plus enough UB looks
sufficient, and upstream says twice that it is not — `dim != last` 和 UB 足够都不是进入内部
Transpose 的充分条件` at `:6`, and `needTrans=true` 不表示内部 Transpose 全局最优` at `:142`. Three
data movements are being added to save one scattered read pattern, and whether that trades well
depends on quantities the UB test does not look at: the workspace traffic, the transpose window
efficiency, and how bad the scattered read actually was on this shape. An agent that enables the path
whenever it fits pays three movements on shapes where the scalar path was fine.

The capability gate removes a harder-to-see branch. Upstream lists concrete requirements —
`postDim > 32`, x and index `gatherDim ≥ 16`, x element count `< INT32_MAX`,
`xGatherDim × dtypeSize < 120000`, dtype limited to 2-byte and 4-byte types with
`当前 dtype 仅 fp16/bf16/fp32/int32`, and `int8 必须走物理路径或 Scalar/SIMT` — and none of these is
inferable from the mechanism. An agent reasoning from the transformation alone will route an int8 case
into a template that does not support it.

The fixed transpose window is the third. `TRANSPOSE_WS_LEN = 128` and `CACHELINE = 512` give two 64 KiB
buffers, 128 KiB of UB spent before any gather buffer is counted (0148). On a 192–248 KB UB (0131,
0140) that is more than half the capacity, fixed, regardless of shape. An agent that budgets the
transpose path as if its cost scaled with the tile will conclude it fits when it does not.

## 3 · Ground / Source
The mechanism, `gather/fallback/tiling-flow.md:320-331`, in full:

```
### 6.3 Transpose + Gather 策略详解（GatherElementsV2 Transpose 模板）

**解决的问题**：torch.gather dim!=last（如 dim=0）且数据为受支持的 2B/4B dtype 时，SIMT 逐元素随机读 GM 可能很慢。内部 Transpose 将散点读转为顺序读 + UB 内向量化 gather；是否采用仍由能力和成本门控决定。int8 不受当前内部模板支持。

**核心思路**：torch.gather `y[o, g, c] = x[o, index[o,g,c], c]` 中，对固定的 (o, c)，x 沿 gather 轴的 GD 个元素虽然物理上不连续（stride=innerSize），但可以用 `DataCopyPad(srcStride=innerSize)` 跨步 DMA 加载到 UB，再用 `TransDataTo5HD` 在 UB 内做矩阵转置使其连续，然后写到 workspace GM。之后从 workspace 顺序读 x 行，用 `Gather` 指令在 UB 内向量化 gather。最后将结果 ReTranspose 写回 y。

**与物理 Transpose 的区别**：不在 framework 层做 3 次独立 Transpose kernel，而是在 **1 个 kernel 内的 3 个阶段**完成（Transpose → Gather → ReTranspose），用 workspace GM 中转，无额外 kernel launch 开销。

**3 阶段流程**：
1. **TransposeProcess**: `DataCopyPad(srcStride=postDim)` stride DMA → `TransDataTo5HD` UB 内转置 → workspace GM
2. **GatherProcess**: 从 workspace 顺序读 x 行 → `Gather` 指令向量化 → workspace GM
3. **ReTransposeProcess**: 从 workspace 读 → `TransDataTo5HD` 转置回 → `DataCopyPad(dstStride=postDim)` 写回 y
```

The gate list, `:77-88`:

```
├─ gatherMode == PER_ELEMENT && dim != last（innerSize > 1）
│   ├─ 内部能力门控：dtype/SoC 支持，shape 可合轴连续搬运，postDim>32，
│   │                  x/idx gatherDim≥16，x元素数<INT32_MAX，xGatherDim*dtypeSize<120000
│   │   && Transpose UB 足够
│   │   && workspace 搬运成本门控通过
│   │     → 【kernel 内 Transpose + Gather】
│   │        阶段1: stride DMA + TransDataTo5HD 转置 x/index → workspace GM
│   │        阶段2: workspace 顺序读 + Gather 指令 → workspace GM
│   │        阶段3: ReTranspose + stride DMA 写回 y
│   ├─ 否则，物理 Transpose 平台可用 && 成本/实测收益门控通过
│   │     → 【物理 Transpose×3 + 末轴 Gather】
│   └─ 否则 → 【Scalar/SIMT】A/B
```

restated as an applicability list, `:333-339`:

```
**适用条件**：
- `gatherMode == PER_ELEMENT`（torch.gather/GatherElementsV2）
- `dim != last`（innerSize > 1，否则直接走 SIMD 末轴 Gather）
- dtype/SoC、shape 合轴、postDim/gatherDim、元素数门控通过；当前 dtype 仅 fp16/bf16/fp32/int32
- UB 够容纳 transpose buffer (128KB) + gather buffer
- workspace 成本代理优于物理 Transpose
- 任一条件失败后，继续评估物理 Transpose，再回退 Scalar/SIMT
```

The tiling and workspace, `:184-197`:

```
UB 分配:
  transInBufferSize  = TRANSPOSE_WS_LEN(128) × CACHELINE(512B) = 64KB
  transOutBufferSize = TRANSPOSE_WS_LEN(128) × CACHELINE(512B) = 64KB
  gatherInBufferSize = CeilAlign(GD, xAlign) × dtypeSize + idxSlice × sizeof(int32) × 2
  gatherOutBufferSize = CeilAlign(idxSlice, xAlign) × dtypeSize
  inBufferSize  = max(gatherInBufferSize, transInBufferSize)
  outBufferSize = max(gatherOutBufferSize, transOutBufferSize)
  门控: ubSize - 2048 >= inBufferSize + outBufferSize

workspace GM: 每核独立 workspace 区域, 存转置后的 x/index/y
  workspacePerBlock = carryNumAlign × (CeilAlign(GD×dtypeSize, 4) + idxGatherDim × 4)

多核: 按 idxPreDim × idxPostDim 分核 (行+列 2D 切分)
      usedCoreNum = min(idxPreDim × idxPostDim, coreNum)
```

with `carryNumAlign = CACHELINE / dtypeSize` from `:124`, so the per-core workspace scales inversely
with element width — a 2-byte dtype gets `carryNumAlign = 256` and a 4-byte dtype 128, doubling the
workspace footprint at the narrower type.

Note the `max(...)` structure of the UB test: the gather buffers and the transpose buffers *share* the
allocation rather than adding to it, so the test is `ubSize - 2048 ≥ max(gatherIn, 64KB) +
max(gatherOut, 64KB)`. Below 64 KiB of gather buffer the test is a constant 128 KiB + 2 KiB and does
not depend on the shape at all. That is why `needTrans` is usually decided by UB capacity rather than
by the case.

Two numbers in the capability gate have no stated origin and are of different kinds:
`xGatherDim × dtypeSize < 120000` is a non-round byte bound that reads as calibrated, and
`postDim > 32` / `gatherDim ≥ 16` read as alignment or vectorisation minima. Upstream distinguishes
none of them. `SoC 支持` appears as a gate term with no definition of which SoCs.

The cost gate — `workspace 成本代理优于物理 Transpose` — is named and not specified anywhere in this
family; the complete gate set is deferred to a sibling skill (0148 §3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Three-way comparison on gate-passing cases. Construct four `PER_ELEMENT`, `dim != last` cases that
pass every stated capability gate, spanning the dtype set (fp16, fp32, int32) and two shapes each —
one with `postDim` just above 32 and one with `postDim` large — with x element counts well inside
`INT32_MAX` and `xGatherDim × dtypeSize` just under and just over 120000. At each case build three
kernels with one compiler pin: in-kernel transpose, physical transpose ×3 plus last-axis gather, and
SIMT scalar. md5 each; host echo of the collapsed sizes, `needTrans`, `carryNumAlign`,
`workspacePerBlock`, `usedCoreNum` and the selected template. Compare output elementwise against a CPU
reference on all three arms. Record `aiv_time`, MTE2/MTE3 bytes, workspace bytes and — for the physical
arm — the number of kernel launches, under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations,
first 5 dropped, per case.

Capability-gate arm, a poison arm per gate. For each of `postDim > 32`, `gatherDim ≥ 16`,
`xGatherDim × dtypeSize < 120000` and the int8 exclusion, construct one case that violates exactly that
gate and passes the rest, force the in-kernel transpose path anyway where the host allows it, and record
whether the result is wrong, fails to launch, or merely slower. A gate whose violation costs nothing is
a gate worth relaxing; one whose violation produces wrong output is a correctness boundary, and the two
must not be reported as the same thing.

`needTrans` boundary arm: with UB queried at runtime, find the case where the
`ubSize - 2048 ≥ 128 KiB + …` test flips, and measure all three arms on either side, so
`needTrans=true 不表示全局最优` is measured rather than repeated.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` or
`coreNum` are literals (queried, 0141); that the launch-overhead saving is real — the physical arm's
launch count is measured, not assumed; that a forced path was taken (host echo required); that a
result at fp16 transfers to fp32, since `carryNumAlign` and hence the workspace footprint differ by 2×.

## 5 · Checker — acceptance declared before the run
Verdict variable `transpose_gain(case)` = min(physical, SIMT) median `aiv_time` / in-kernel-transpose
median `aiv_time`. Declared before the run: the path is justified iff `transpose_gain > 1 +
variance_floor` on at least three of the four gate-passing cases. The OVERTURN fires iff
`transpose_gain ≤ 1 + variance_floor` on all four — the three extra movements would then not pay
where upstream says they do. A second verdict `launch_saving` = physical arm launch count minus
in-kernel launch count, expected to be 2, reported as observed. Per-gate verdict
`gate_kind ∈ {correctness, performance, none}` from the capability arm.

The exit code is not the verdict: a gather returning wrong elements exits 0, and the transpose path has
three stages in which a value can lose its index position. The elementwise comparison is the primary
instrument and the checker fails red if it did not run on all three arms. Second guard: path identity —
the host echo must confirm the in-kernel arm actually used the transpose template (non-zero
`workspacePerBlock`, `needTrans = true`) and that the physical arm launched more than one kernel; a
silently collapsed pair of arms would make `transpose_gain ≈ 1` read as a clean overturn from an
experiment that ran one plan twice.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Upstream states no measurement
for this path either — `SIMT 逐元素随机读 GM 可能很慢` is a hedged assertion (`可能`), and the whole
gather family carries no number with a case identity.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that the in-kernel transpose is faster than either
alternative on any shape — upstream itself only says the scattered read `可能很慢` and defers the
decision to gates it does not fully specify. It does not establish any capability-gate threshold
(`postDim > 32`, `gatherDim ≥ 16`, `120000`), does not establish which SoCs `SoC 支持` admits, and does
not reproduce the workspace cost gate, which lives in a sibling skill and is outside this domain. It
does not establish `xAlign`, `idxSlice`, `minIdxSlice` or the 2048 UB reserve (0148). It does not
establish the launch-overhead saving. No chip is named anywhere in the gather family, so BOARD is
`family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT because that is where our
run would happen. Nothing here is established for any 910-family board.

```
ID:        0147-gather-collapses-to-four-sizes-and-gathermode-decides-which-templates-are-even-legal
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/gather/fallback/tiling-flow.md:14-43,60,167,
           309-318 — "合轴 | 将原始 shape + axis 合并为 `(outerSize, gatherDimSize, gatherSize,
           innerSize)` 四元组" · "SIMD 两维和 SIMD 行拷贝模板**仅适用于 PER_SLICE**——它们假设一个
           索引取整行 slice，可用 DataCopyPad 连续搬。PER_ELEMENT 中每个输出位置有独立索引，无连续
           slice 可搬，走这两个模板会导致逐元素标量读退化。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured PER_ELEMENT gather on a named 950 board where the SIMD row-copy template
           matches or beats the templates upstream restricts PER_ELEMENT to — the mode restriction
           would then be a modelling convenience rather than a performance fact.
```

# 0147 · Gather collapses to four sizes, and gatherMode decides which templates are even legal

## 1 · Claim
Upstream asserts that gather tiling collapses `(x.shape, index.shape, axis, batch_dims)` into four
sizes — `outerSize` (product of dimensions before the gather axis), `gatherDimSize` (x's length along
it), `gatherSize` (index's length along it), `innerSize` (product after it) — plus `batchSize`.
Upstream asserts that the collapse arithmetic differs by index semantics: for `PER_SLICE`,
`gatherSize = index.numel() / batchSize` and
`ySize = batchSize * outerSize * gatherSize * innerSize`; for `PER_ELEMENT`, `ySize = index.numel()`
and the output count must *not* be multiplied by `outerSize` or `innerSize`, `否则会重复计算输出元素数`.
Upstream asserts that `gatherMode` is a first-class routing input and not a detail:
`PER_ELEMENT` (torch.gather, GatherElementsV2 — index same shape as output, one element per position)
versus `PER_SLICE` (GatherV2, Embedding — one index fetches `innerSize` contiguous elements). Upstream
asserts that the SIMD two-dimensional and SIMD row-copy templates are legal only for `PER_SLICE`,
because both assume one index fetches a whole row that `DataCopyPad` can move contiguously, and that
routing a `PER_ELEMENT` case to either degenerates into per-element scalar reads. Upstream asserts a
`Dtype Improve` step: when `innerSize × dtypeSize` is a multiple of 8, 4 or 2 bytes, the element type
is promoted to that width to reduce MTE2 operation count, with
`innerSize_improved = innerSize × dtypeSize / improveDtypeSize`. Not established here.

## 2 · The wrong branch this removes
`torch.gather` and `tf.gather` have the same name and different semantics, and the tiling consequence
is total. A harness agent that treats "gather" as one operator writes the `PER_SLICE` collapse for a
`PER_ELEMENT` case and gets `ySize` too large by `outerSize × innerSize` — upstream flags exactly
that (`否则会重复计算输出元素数`) — which then propagates into every multi-core split and every UB
budget. The kernel launches, over-allocates, and either wastes cores or writes past the real output
extent.

The template legality is the sharper half. `DataCopyPad` moving `innerSize` contiguous elements per
index is the entire mechanism of the two SIMD row templates. Under `PER_ELEMENT` there is no such
run: each output position carries its own index, so the "row copy" becomes `innerSize` independent
scalar reads. That is not a slow variant of the same plan — it is a different memory access pattern
with the same tiling data, and an agent with no correctness signal will ship it. Upstream names the
degeneration rather than only forbidding the route, which is what makes the rule usable.

`Dtype Improve` removes a third wrong branch: taking `dtypeSize` from the tensor. An int8 gather whose
`innerSize` is a multiple of 8 moves 8× fewer MTE2 operations if the element type is promoted, and
every downstream budget in this family is written in `improveDtypeSize`, not `dtypeSize`. An agent
that uses the declared dtype computes tiles that are legal and eight times more numerous than
necessary.

## 3 · Ground / Source
The collapse, `gather/fallback/tiling-flow.md:12-43`:

```
| 术语 | 含义 |
|------|------|
| **合轴** | 将原始 shape + axis 合并为 `(outerSize, gatherDimSize, gatherSize, innerSize)` 四元组 |
| **outerSize** | gather 轴 **之前** 所有维度乘积（batch/outer 维） |
| **gatherDimSize** | x 沿 gather 轴的长度（被索引维度大小） |
| **gatherSize** | index 沿 gather 轴的长度（索引数量 per outer×inner） |
| **innerSize** | gather 轴 **之后** 所有维度乘积（inner 维，一个索引取的 slice 大小） |
| **Dtype Improve** | 小 dtype 的 innerSize×dtypeSize 若 32B 对齐，提升为更大 dtype 减少 MTE2 次数 |
| **gatherMode** | 算子的索引语义：`PER_ELEMENT`（torch.gather/GatherElementsV2，index 与 output 同形，每位置独立索引取 1 元素）或 `PER_SLICE`（GatherV2/Embedding，每索引取 innerSize 个连续元素）。**决定哪些模板分支可用** |
```

```
给定: x.shape, index.shape, axis(dim), batch_dims=0

batchSize  = prod(x.shape[0:batch_dims])     // 默认 1
outerSize  = prod(x.shape[batch_dims:axis])  // gather 轴之前
gatherDimSize = x.shape[axis]                // 被索引维度
innerSize  = prod(x.shape[axis+1:])          // gather 轴之后
若 gatherMode == PER_SLICE:
  gatherSize = index.numel() / batchSize
  ySize      = batchSize * outerSize * gatherSize * innerSize

若 gatherMode == PER_ELEMENT:
  idxPreDim     = prod(index.shape[0:axis])
  idxGatherDim  = index.shape[axis]
  idxPostDim    = prod(index.shape[axis+1:])
  gatherSize    = idxGatherDim  // 仅供 gather 轴长度/复用比判断
  ySize         = index.numel()
  // 不再乘 outerSize/innerSize；否则会重复计算输出元素数
```

`Dtype Improve`, `:45-54`:

```
lastAxisBytes = innerSize * dtypeSize
若 dtypeSize < 8 且 lastAxisBytes % 8 == 0 → improveDtypeSize = 8
若 dtypeSize < 4 且 lastAxisBytes % 4 == 0 → improveDtypeSize = 4
若 dtypeSize < 2 且 lastAxisBytes % 2 == 0 → improveDtypeSize = 2
否则 improveDtypeSize = dtypeSize
innerSize_improved = innerSize * dtypeSize / improveDtypeSize
```

Note that the term's own definition says `32B 对齐` while the rule tests 8, 4 and 2 bytes. The
glossary sentence and the arithmetic disagree about the alignment quantum; the arithmetic is the
operative one. Registered as C-950tiling-021.

The mode restriction, `:60`:

```
> **gatherMode 是决策树的关键输入**：`PER_ELEMENT`（torch.gather/GatherElementsV2，每位置独立索引取 1 元素）与 `PER_SLICE`（GatherV2/Embedding，每索引取 innerSize 个连续元素）的模板选择不同。SIMD 两维和 SIMD 行拷贝模板**仅适用于 PER_SLICE**——它们假设一个索引取整行 slice，可用 DataCopyPad 连续搬。PER_ELEMENT 中每个输出位置有独立索引，无连续 slice 可搬，走这两个模板会导致逐元素标量读退化。
```

The operator-to-mode map and the legality matrix, `:300-318`:

```
| 算子 | gatherMode | index 形态 | 每 index 取 | 对应框架 |
|------|-----------|-----------|------------|---------|
| **GatherElementsV2** | **PER_ELEMENT** | == x.ndim（同形） | 1 元素 | torch.gather |
| **GatherV2** | **PER_SLICE** | ≤ x.ndim | innerSize 元素 | TF tf.gather |
| Embedding | PER_SLICE | 1D/2D | innerSize 元素 | nn.Embedding |
| batch_dims>0 | PER_SLICE | 前缀匹配 | innerSize 元素 | TF tf.gather(batch_dims) |
```

```
| 模板 | PER_ELEMENT (torch.gather) | PER_SLICE (GatherV2/Embedding) | 原因 |
|------|:---:|:---:|------|
| **kernel 内 Transpose + Gather** | **✅（仅能力/UB/成本门控全通过）** | ❌ | PER_ELEMENT 专属：每位置独立索引但同一 (o,c) 的 GD 列可 stride DMA 转置 |
| **物理 Transpose + 末轴 Gather** | ✅（平台能力/成本门控通过） | ❌ | 把 gather 轴交换到末轴并复用独立高性能算子 |
| SIMD 末轴 Gather | ✅ (inner==1) | ✅ (inner==1) | 末轴 gather，x 行全载 UB + Gather 指令 |
| GA 全载 | ✅ | ✅ | GD×inner 全载 UB |
| Full-Load | ✅ | ✅ | GD×inner 全载 + 2D |
| **SIMD 两维** | **❌** | **✅** | 需一个索引取整行 slice，PER_ELEMENT 每位置独立索引无 slice |
| **SIMD 行拷贝** | **❌** | **✅** | 同上，DataCopyPad 逐行搬 innerSize 元素需索引复用 |
| SIMT 标量/两维 | ✅ | ✅ | 通用兜底，直接 GM 读写 |
```

The restriction is therefore symmetric: two templates are `PER_SLICE`-only and two are
`PER_ELEMENT`-only, which upstream states as a mode-exclusivity property rather than as a preference.

The empty-input guard, `:68`: `前置: gatherDimSize == 0 → EMPTY 模板（输出清零）`.

The address-width rule, `:285-292`, which is a correctness gate rather than a performance one:

```
若 gatherDimSize × innerSize > INT32_MAX 或 ySize > INT32_MAX:
  INDEX_SIZE_T = uint64_t
否则:
  INDEX_SIZE_T = uint32_t  // 32 位地址（更快）
```

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the mode restriction, a poison arm. Take one `PER_ELEMENT` case with `dim != last` and a
large `innerSize` (x = `[64, 512, 1024]` int32, `dim = 1`, index same shape) — a shape that would
satisfy the SIMD row-copy gate on size grounds. Build three kernels with one compiler pin: the
template upstream routes it to (per 0149), the SIMD row-copy template forced, and the SIMT scalar
fallback. md5 each; host echo of the four collapsed sizes, `gatherMode`, `improveDtypeSize` and the
selected template. Compare output elementwise against a CPU reference — a forced row-copy on a
`PER_ELEMENT` case may be *wrong* as well as slow, and which of the two it is decides how upstream's
prohibition should be read. Record `aiv_time` and MTE2 operation count under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Arm 2 — the collapse arithmetic, host only, no device. For six shapes covering both modes and
`batch_dims ∈ {0, 1}`, compute the four sizes and `ySize` by hand and compare against the host's
echoed values, and separately compute `ySize` with the `PER_SLICE` formula applied to a `PER_ELEMENT`
case to record the size of the over-count upstream warns about.

Arm 3 — `Dtype Improve`. For an int8 `PER_SLICE` case, sweep `innerSize` over values that are and are
not multiples of 8, 4 and 2, and record `improveDtypeSize`, the MTE2 operation count and `aiv_time`
at each. This measures whether the promotion delivers the stated MTE2 reduction and settles which
alignment quantum the rule actually uses (C-950tiling-021).

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` or
`ubSize` are literals (queried per 0141 — several gates use `coreNum/2`); that a forced template was
used (host echo required); that a `PER_ELEMENT` row-copy is merely slow rather than wrong — arm 1's
elementwise comparison is what decides.

## 5 · Checker — acceptance declared before the run
Verdict variable `mode_restriction_kind ∈ {correctness, performance, none}` from arm 1: `correctness`
if the forced row-copy produces wrong output; `performance` if it is correct but slower than the
routed template by more than the variance floor; `none` if it is correct and within the floor.
Declared acceptance: upstream's restriction is supported iff the verdict is `correctness` or
`performance`. The OVERTURN fires on `none`, or on the forced row-copy being *faster* — the
restriction would then be a modelling convenience. Verdict `collapse_matches` from arm 2 is a
per-shape boolean over the four sizes and `ySize`. Verdict `improve_gain(alignment)` from arm 3 is the
MTE2 operation-count ratio at each swept `innerSize`.

The exit code is not the verdict: a gather with wrong indices exits 0, and a forced-template build the
host silently overrode also exits 0. Two guards. First, the elementwise comparison is the primary
instrument in arm 1 and the checker fails red if it did not run. Second, template and mode identity:
the host echo must show the requested template and the correct `gatherMode` at every point; a
collapsed pair of arms would make `mode_restriction_kind = none` from an experiment that never forced
anything, which is precisely the blind reading this guard exists to prevent.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no shape was collapsed by a real host and no kernel was built. The entry does
not establish that the four-size collapse is sufficient, that the mode restriction is a performance
fact rather than a design choice, or that `Dtype Improve` reduces MTE2 operations. It does not resolve
the alignment-quantum disagreement in the `Dtype Improve` definition (C-950tiling-021). It does not
cover the template gates themselves (0148) or the transpose cost gating (0149). It does not establish
`INT32_MAX` address-width behaviour. No chip is named anywhere in the gather family — a prior survey
recorded this family as carrying no chip and no measured number, and re-reading confirms it — so BOARD
is `family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT because that is where
our run would happen. Nothing here is established for any 910-family board.

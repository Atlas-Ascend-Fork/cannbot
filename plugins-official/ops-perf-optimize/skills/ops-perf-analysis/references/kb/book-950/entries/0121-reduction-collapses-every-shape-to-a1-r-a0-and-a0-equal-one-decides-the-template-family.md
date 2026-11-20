```
ID:        0121-reduction-collapses-every-shape-to-a1-r-a0-and-a0-equal-one-decides-the-template-family
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:10-22,26-40,
           95,115 — "**合轴** | 将原始 shape + axes 合并为 `(A1, R, A0)` 三元组" ·
           "1. 标记每个维度为 A(保留) 或 R(归约) 2. 消除 size=1 的冗余维 3. 合并相邻同类型轴" ·
           "┌─ A0 == 1 ──→ AR 族（最内维归约，等价 2D [A1, R]）" ·
           "└─ A0 > 1 ──→ ARA 族（非尾轴归约，等价 3D [A1, R, A0]）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a reduction case on a named 950 board where the collapsed triple (A1, R, A0) is
           identical for two different original shapes but the measured best template differs —
           the collapse would then be lossy for tiling purposes.
```

# 0121 · Reduction collapses every shape to (A1, R, A0), and A0 == 1 decides the template family

## 1 · Claim
Upstream asserts that reduction tiling begins by collapsing an arbitrary `(shape, axes)` pair into
a three-element triple: mark every dimension as A (retained) or R (reduced), drop size-1
dimensions, merge adjacent same-type axes, and read off `A1` as the product of retained axes
*before* the reduction axis, `R` as the reduction axis length, and `A0` as the product of retained
axes *after* it. Upstream further asserts that the triple, not the operator name, selects the
template family: `A0 == 1` means the reduction is over the innermost dimension and the case is
equivalent to a 2-D `[A1, R]` problem (the AR family), while `A0 > 1` means a non-trailing
reduction equivalent to a 3-D `[A1, R, A0]` problem (the ARA family). Upstream also asserts the
collapse can fail: when A and R strictly alternate in memory, adjacent axes are of different types
so merging is impossible, and no axis has size 1, so the shape cannot be pressed into a single R —
the five-template precondition does not hold and a separate pre-gate applies (0125). Not
established here.

## 2 · The wrong branch this removes
The wrong branch is treating reduction tiling as per-operator knowledge. Softmax, LayerNorm,
ReduceSum and ArgMax appear to need four different plans, and an agent asked for a Softmax tiling
will look for Softmax-specific rules. Upstream's structure says the opposite: they share one
template language and differ only in the buffer count in the UB budget's denominator (0130). An
agent that misses the collapse writes an operator-specific plan for each, gets no reuse, and — the
expensive part — has no way to tell that `[batch, seq]` with axis=1 and `[N]` with axis=0 are the
same tiling problem with `A1 = batch` versus `A1 = 1`.

The `A0 == 1` test removes a second, sharper wrong branch. It is the difference between reducing
the innermost dimension (contiguous in memory, vectorisable directly) and reducing a middle
dimension (strided, so each output lane gathers across a stride). Those need different UB layouts,
different alignment rules (`a0_tile_unit = 64` for FP32, 128 for FP16 — the vector register width
in elements) and different multi-core split axes. An agent that reasons about "the reduction axis"
without asking what follows it will apply the AR budget to an ARA case and get a plan whose tile
does not correspond to any contiguous region.

## 3 · Ground / Source
The vocabulary, `reduction/fallback/tiling-flow.md:10-22`, in full:

```
| 术语 | 含义 |
|------|------|
| **合轴** | 将原始 shape + axes 合并为 `(A1, R, A0)` 三元组 |
| **A1** | 归约轴 R **之前**所有保留轴的乘积 |
| **R** | 归约轴长度 |
| **A0** | 归约轴 R **之后**所有保留轴的乘积（AR 模式下 A0=1） |
| **模板** | 确定的 UB 切分与多核策略，共五种 |
| **FullLoad** | R 方向数据一次全部载入 UB |
| **Recompute** | R 方向超出 UB 容量，分块处理并在块间合并 |
| **SmallR** | R 极小时通过转置布局优化访存（仅 AR 模式） |
| **多轴交错** | 合轴后仍为多个交替 A/R（A-R-A-R…，不可合成单个 R），如 8 轴 ARARARAR / 7 轴 ARARARA |
| **交错连续载入** | 交错布局专用模板（tail-R fast / tail-A fast-RARA），按内存物理连续顺序做大 burst 载入，把 A/R 分离从 HBM 碎读搬到 UB 内链式规约 |
| **R 轴分核 group（BlockSplitR）** | 大 R + 小 A 时**跨核切归约轴 R**：各核算一段 R 的部分和写 workspace，SyncAll 后 Phase2 合并。与"切 A"的五模板/normal 并列 |
```

The collapse procedure, `:26-38`:

```
给定: shape, axes

1. 标记每个维度为 A(保留) 或 R(归约)
2. 消除 size=1 的冗余维
3. 合并相邻同类型轴

输出: (A1, R, A0)

多轴归约（如 axes=[1,2]）时，相邻 R 轴合并为一个 R。
```

The failure case, `:40`:

> **合轴后可能仍是交错序列。** 当保留轴与归约轴在内存上交替出现（如 shape `[4,2,2,640,32,32,2,2]`
> axes=[1,3,5,7]，标记后为 `A-R-A-R-A-R-A-R`），相邻同类型轴合不掉、size=1 也去不掉，最终 **无法压成
> 单个 R**。此时不能直接进五模板（五模板假设合轴后是简单 AR/ARA，单个 R）

The family split, `:95` and `:115`:

```
┌─ A0 == 1 ──→ AR 族（最内维归约，等价 2D [A1, R]）
└─ A0 > 1 ──→ ARA 族（非尾轴归约，等价 3D [A1, R, A0]）
```

Worked collapses, from the two case files. `reduction/fallback/example/softmax/experience.md:34-38`:

```
| `[batch, seq, dim]` axis=1 | axis=1 | A1=batch, R=seq, A0=dim |
| `[batch, seq]` axis=1 | axis=1 | A1=batch, R=seq, A0=1 → AR 族 |
| `[N]` axis=0 | axis=0 | A1=1, R=N, A0=1 → AR 族 |
```

`reduction/fallback/example/euclidean_norm/experience.md:32-38`:

```
| `[64000, 32]` | [0] | R=64000, A=32 → RA（单 R） | 五模板 |
| `[4, 3200, 24]` | [1] | A=4, R=3200, A0=24 → ARA（单 R） | 五模板 |
| `[2,320,14,320]` | [1,3] | `A-R-A-R`（2 个 R，合不掉） | **交错** |
| `[4,2,20,49,32,9,15]` | [1,3,5] | `A-R-A-R-A-R-A`（7 轴 tail-A） | **交错** |
| `[4,2,2,640,32,32,2,2]` | [1,3,5,7] | `A-R-A-R-A-R-A-R`（8 轴 tail-R） | **交错** |
```

Note the first row: `[64000, 32]` with `axes=[0]` collapses to `R=64000, A=32`, which is an *RA*
layout — the reduction axis first, retained axis last — and upstream files it under 五模板 with
`A1 = 1`. The triple notation puts a leading R at `A1 = 1, R = 64000, A0 = 32`, i.e. the ARA
family with a degenerate outer axis. Upstream never says this explicitly, and the `A0 == 1` test
handles it correctly by construction. Recorded because it is the case that would trip a reader
applying the family test to the label "RA" rather than to `A0`.

Upstream also carries a hard reading instruction on the routing page,
`reduction/index.md:14`: `⚠️ 路由命中后**必须深入 fallback/ 子目录**读取 tiling-flow.md ...
tiling-fields.md ... example/<算子名>/experience.md。禁止仅读本文件的表格后停止。` It is the
only family in this domain that forbids stopping at its routing table, and it is the family with
the most content behind it.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Collapse-equivalence test, which is what makes the claim falsifiable. Construct pairs of
*different* original shapes that collapse to the *same* `(A1, R, A0)` triple — e.g. `[8, 4, 512]`
with axes=[2] and `[32, 512]` with axes=[1], both collapsing to `A1=32, R=512, A0=1`; and
`[2, 2, 1, 1024, 64]` with axes=[3] against `[4, 1024, 64]` with axes=[1], both collapsing to
`A1=4, R=1024, A0=64`. Build four pairs across FP32/FP16, one compiler pin, md5 per binary, host
echo of the collapsed triple and the chosen template. For each member of each pair, sweep all
applicable templates rather than only the chosen one, verify every build against an fp64 reference
within the declared tolerance, and record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case with no
representative sampling.

Second arm — the family test. At fixed `A1` and `R`, sweep `A0 ∈ {1, 2, 8, 64, 128, 512}` and
record which template family the host chooses and which family is actually fastest, so the
`A0 == 1` boundary is observed rather than assumed.

Refuses to assume: that a free die stays free; that a die may be substituted; that the collapsed
triple echoed by the host matches the one derived by hand (both are recorded and compared); that
the same-triple pair has the same memory layout — it does not, and that is exactly the point of
the test; that `core_num` and `ub_size` are the script defaults (both are queried, and this family
carries two incompatible values for each — 0131).

## 5 · Checker — acceptance declared before the run
Verdict variable `collapse_lossless`, one boolean per shape pair: true iff both members choose the
same template AND their best-template rankings agree AND their median `aiv_time` values are within
10 % of each other. Declared acceptance: the collapse is a sufficient tiling summary iff
`collapse_lossless` holds for all four pairs. The OVERTURN fires iff any pair has the same triple
but a different best template — the triple is then lossy, and every downstream template decision
inherits the loss. A pair with the same best template but a >10 % time gap is a partial result: the
collapse selects correctly but does not predict cost, and that is reported as its own sentence.

The exit code is not the verdict. This checker's blind mode is the host quietly re-deriving a
different triple than the one intended: two shapes that were supposed to collapse identically might
not, in which case agreement or disagreement says nothing. The host echo of `(A1, R, A0)` and
`mode` is therefore compared between pair members before any timing is read, and the checker goes
red on a mismatch instead of comparing times. It also fails red if any template in the sweep
produced a result outside the declared tolerance, rather than dropping that point.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no shape was collapsed by a real host tiling and no kernel was built. The
entry does not establish that the collapse is lossless, that `A0 == 1` is the right family
boundary, or that the merge/drop rules handle every axis order — upstream states them as steps and
gives no counter-examples beyond the interleaved case it explicitly excludes. It does not cover
what happens when the reduction axes are non-adjacent but still collapsible after dropping size-1
dimensions; upstream's rule set implies it works and gives no example. The interleaved case is out
of scope here and is entry 0125. No board is named in `tiling-flow.md` itself — the only board-ish
words in this family are `arch35` and `Ascend 950` in the case file (0131) — so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.

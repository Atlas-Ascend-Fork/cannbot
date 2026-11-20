```
ID:        0107-matmul-picks-one-of-three-mutually-exclusive-strategies-and-streamk-kills-fullload-by-semantics
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:15-23,325-340 —
           "MatMul Tiling 有三种算法策略，互斥选择" ... "**互斥关系**：StreamK ⊥ FullLoad
           （StreamK 下 K 分散到多核，驻留语义失效）" ; decision tree "Step 1 — StreamK 判定 ...
           Step 2 — FullLoad 判定 ... 不通过 → SWAT（默认回退）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured case on a named 950 board where a plan combining K-axis multi-core
           splitting with an L1-resident operand outperforms both pure StreamK and pure FullLoad
           on the same shape — the exclusion is then a property of upstream's generator, not of
           the architecture.
```

# 0107 · MatMul picks one of three mutually exclusive strategies, and StreamK kills FullLoad by semantics

## 1 · Claim
Upstream asserts that MatMul tiling chooses exactly one of three mutually exclusive strategies,
in a fixed order: StreamK first (K split across cores, each core owning a K segment, cross-core
partial sums reduced through workspace), FullLoad second (A or B resident in L1 for the whole
computation, eliminating repeated K-axis movement), and SWAT last as the unconditional default
baseline (K-axis streaming, data loaded into L1 in segments and rolled). Upstream further asserts
that StreamK and FullLoad are incompatible in principle rather than by budget — under StreamK the
K axis is already scattered across cores, so residency has no meaning (`驻留语义失效`) — and that
the decision tree tests StreamK before FullLoad, so a shape passing both gates gets StreamK.
Not established here.

## 2 · The wrong branch this removes
Without the ordering, a harness agent that reads the three strategies as a menu evaluates them by
expected benefit and picks FullLoad for a large-K shape because the FullLoad section promises a
5–15 % task-time reduction while the StreamK section promises nothing numeric at all. That
inverts upstream's own order. Worse, an agent that reads them as composable tries to enable both:
the flags `isAFullLoad`/`isBFullLoad` and the StreamK field set are independently settable in the
tiling struct, nothing in the schema forbids the combination, and the kernel will pick a template
from the flags. The result is a K-split kernel whose "resident" operand is re-loaded per core
segment — correct output, silently worse movement, and no diagnostic anywhere. Upstream states
the exclusion twice (`:23` and the `已走 StreamK | 不叠加` row at `:267`) precisely because the
struct does not enforce it.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:15-23`:

```
MatMul Tiling 有三种算法策略，互斥选择：

| 算法 | 核心思想 | 适用条件 |
|------|---------|---------|
| **SWAT**（默认基线） | K 轴流式迭代，数据沿 K 分段载入 L1，每次只驻留一小段，计算完即滚动 | 所有 Shape，为回退保障 |
| **FullLoad** | A 或 B 全量驻留 L1，消除 K 轴重复搬运 | A 或 B 全载于 L1 内，对侧循环 ≥ 2 |
| **StreamK** | K 轴切分给多核，每核负责一段 K，workspace 归约 | K ≥ 32768 且 B=1 且无 group |

**互斥关系**：StreamK ⊥ FullLoad（StreamK 下 K 分散到多核，驻留语义失效）。
```

The decision tree, `:327-340`:

```
给定变体 + Shape (M, K, N, [B/g])

Step 1 — StreamK 判定
  ├─ 通过 → StreamK
  │   强制：l1BufferNum=2, l0cDB=1
  │   batch_matmul (B≥2) 和 group_matmul 默认不启用
  └─ 不通过 → Step 2

Step 2 — FullLoad 判定
  ├─ 通过 → FullLoad
  │   A-Full 与 B-Full 互斥，选小侧
  └─ 不通过 → SWAT（默认回退）
```

The same three-way choice appears in `fallback/fallback-algorithm.md:21-24,31-35`, which is the
family's routing entry point; the two files agree on the order and on the StreamK condition text.
Both are the same repo, so this is one origin (RULES.md Art. 3) and the entry stays `harvested`.

The exclusion has a second consequence upstream records at `:299-312`: under StreamK, seven
fields are forced constants — `l1BufferNum=2`, `l0cDB=1`,
`mBaseTailSplitCnt=nBaseTailSplitCnt=1`, `mTailMain=nTailMain=0`, `usedCoreNum=aicNum` — so a
StreamK plan that reports a tuned `nBufferNum` or a `usedCoreNum` below `aicNum` is internally
inconsistent, and that is mechanically checkable without a device.

The StreamK entry condition quoted here (`K ≥ 32768 且 B=1 且无 group`) is contradicted by the
same file's own formula 262 lines later; that contradiction is entry 0108 and row
C-950tiling-002, and it extends `harvest/CONTRADICTIONS.md` C-009.

`algorithm 来源` is declared at `:9`: CANN `conv_api_tiling_*.cpp` (arch35), with constants in
`conv_api_tiling_util.h` / `conv_template_utils.h`. Those headers are not in this tree; `arch35`
is the only architecture word in the file and it names a family, not a board.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT, recorded as whichever ran); never
run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only if HBM-used and AICore-utilisation are at their idle floor in all three
samples; export `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after the run and discard the case if
the die moved.

Three-arm comparison on shapes that pass more than one gate. Choose shapes where both StreamK and
FullLoad gates evaluate true under upstream's own formulas: small M and N with very long K
(M=N=512, K=32768, FP16) and one where only the `:283` formula passes (M=N=512, K=16384, FP16 —
the file's own worked example). For each shape build four kernels from the same source with the
same compiler pin: (a) SWAT, (b) FullLoad on the smaller side, (c) StreamK, (d) the forbidden
combination — StreamK field set with `isAFullLoad=true`. Arm (d) is the point of the experiment;
it is the arm that makes the exclusion observable rather than assumed, and it is retained in the
report whether or not it bites. md5 all four binaries so that four distinct builds are shown to be
distinct. Verify every arm's output against an fp64 reference within the operator's declared
tolerance before any timing is read — arm (d) may be numerically wrong, and that is a result.
Collect `aic_time`, `aiv_time` and MTE2 bytes moved under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations per case, first 5 discarded as warm-up,
per case with no representative sampling.

Refuses to assume: that a die free before the run stayed free; that a die may be substituted for
the named one; that arm (d) is illegal — it is built and run rather than argued about; that
`aicNum` is any particular number (it is read at runtime, not from a script literal — C-007
records five incompatible values in this subtree); that a 950PR result transfers to 950DT.

## 5 · Checker — acceptance declared before the run
Verdict variables: `excl_holds` and `order_holds`, per shape. `excl_holds` is true iff arm (d) is
either numerically wrong, or fails to launch, or is no faster than the better of (b) and (c) by
more than 5 %. `order_holds` is true iff arm (c) is at least as fast as arm (b) on every shape
where both gates pass. Declared acceptance: the entry survives iff `excl_holds` is true on both
shapes. The OVERTURN fires iff arm (d) is numerically correct AND beats both (b) and (c) by more
than 5 % on either shape. `order_holds` false with `excl_holds` true is a partial result — the
exclusion stands but upstream's StreamK-first ordering does not — and is written into §6 as such
rather than being smoothed away.

The exit code is not the verdict; `msprof` exits 0 on runs that emitted no metric rows, and a
build whose forbidden flag combination was silently ignored also exits 0. Two guards make this
checker able to go red rather than merely to confirm: the host echo of the full field set
(`isAFullLoad`, `l1BufferNum`, `usedCoreNum`, `skSingleCoreK`) must match what arm (d) requested,
and MTE2 bytes moved must differ between arms (b) and (c) — if they do not, the two arms did not
actually run different plans and no timing comparison is valid. The checker fails on either
condition instead of reporting the timings it can see.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no kernel was built or run. The entry does not establish that the three
strategies are the right three, that the StreamK-first order is optimal, or that the exclusion is
architectural rather than an artifact of upstream's generator — the §4 arm (d) exists because
that distinction is currently unavailable. It does not establish any of the gate thresholds; the
StreamK condition quoted here is itself internally contradicted (0108). No board is named in this
file: `arch35` at `:9` names a family, so BOARD is `family-claimed(unverified)` and the chip is
unstated. §4 names 950PR/950DT because that is where a future run of ours would happen, not
because upstream's evidence touched them. Nothing here is established for any 910-family board,
and no fact from the 910 book was used.

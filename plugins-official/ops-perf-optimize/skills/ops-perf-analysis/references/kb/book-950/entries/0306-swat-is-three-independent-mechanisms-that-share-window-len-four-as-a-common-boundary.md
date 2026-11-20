```
ID:        0306-swat-is-three-independent-mechanisms-that-share-window-len-four-as-a-common-boundary
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/swat_design.md:11-19 —
           "**SWAT** 就是针对 non-full-load 路径提出的组合调度策略，名字可以读成「**S**erpentine
           **W**indow + **A**daptive **T**ail」。它用三个相互独立、又互相约束边界的机制一次性解决
           上述三个问题" · "三者都沿用一个共同的常量 `WINDOW_LEN = 4`（serpentine 行窗口高度），
           从而保持 host tiling、device scheduler、device kernel 三层的切分边界对齐。"
SOURCE:    same file:95 — "Serpentine 把每 `WINDOW_LEN` 行打成一个行窗口，窗口内多核并行走 M，
           **沿 N 推进时奇数行窗口反向**，让两次推进的 N 边界继续落在同一个 B 片段" ; :142 —
           "关键不变量：**行窗口的边界在整个调度中是神圣的**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul on a named 950 board where disabling the odd-row N reversal (mechanism
           A alone, every other parameter held) leaves MTE2 bytes and kernel time unchanged outside
           the run spread — the serpentine order would then buy no B-side reuse, and the constant
           the other two mechanisms are aligned to would have no reason to exist.
```

# 0306 · SWAT is three independent mechanisms that share `WINDOW_LEN = 4` as a common boundary

## 1 · Claim
Upstream asserts that SWAT is not one scheduling policy but three, aimed at three distinct
pathologies of the non-full-load matmul path, and that their only coupling is a shared constant.
Mechanism A, serpentine row-window traversal, addresses B-side streaming bandwidth: rows are grouped
into windows of `WINDOW_LEN` rows, cores walk M inside a window in parallel, and odd-numbered
windows traverse N in reverse so that consecutive advances keep landing on the same B fragment.
Mechanism B, tail base-block merging, addresses M/N edge slivers. Mechanism C, last-round
two-dimensional re-splitting, addresses idle cores in the final round. Upstream asserts all three
use `WINDOW_LEN = 4`, and that this is what keeps host tiling, device scheduler and device kernel
agreeing about where the split boundaries are. Upstream states one invariant as governing:
`行窗口的边界在整个调度中是神圣的` — neither B's merge region nor C's sub-splitting may break a
window. Not established here.

Upstream asserts SWAT has two sub-modes selected by a compile-time tag, `NO_FULL_LOAD_MODE` (A and
B streaming, the version its analysis covers) and `A_FULL_LOAD_MODE` (A resident, mechanism C
simplified).

## 2 · The wrong branch this removes
An agent reads "SWAT" as one thing and either adopts or rejects it whole. Both moves are wrong in
the same way: the three mechanisms answer three different profile signatures, and an operator
usually has one of them.

- Saturated MTE2 with B streaming → mechanism A only.
- Core-time spread caused by one thin edge tile → mechanism B only.
- Cores idle in the final round → mechanism C only, *or* StreamK's DP+SK, and `0309`'s family says
  which by how close `baseM/baseN` already is to the cube granularity.

Rejecting SWAT because "the tail re-split did not help" discards the serpentine order, which is
the piece the family says every non-full-load kernel should have (`任何模式都应打开 SWAT 机制 A`).
Adopting SWAT wholesale on a shape with no tail pays mechanism B's host-side search and mechanism
C's branchy device path for nothing.

The second wrong branch is the constant. `WINDOW_LEN = 4` looks like a tunable and is not one in the
usual sense: three layers derive boundaries from it, and changing it in one place silently
mis-aligns the others. Upstream's word for the window boundary is `神圣的`, and the operational
content of that word is: this constant is a contract between files, not a knob.

## 3 · Ground / Source
The framing, `swat_design.md:11-19`:

```
**SWAT** 就是针对 non-full-load 路径提出的组合调度策略，名字可以读成「**S**erpentine **W**indow
+ **A**daptive **T**ail」。它用三个相互独立、又互相约束边界的机制一次性解决上述三个问题：

| 机制 | 定位 | 对应问题 |
| A. Serpentine 行窗口遍历 | 全局遍历顺序 | B 侧流式带宽复用 |
| B. 尾部基块合并（尺寸重排） | 稳态区与尾区之间的桥梁 | M/N 边缘薄片 |
| C. 尾块二维再切分 | 最后一轮局部处理 | 末轮空闲核 |

三者都沿用一个共同的常量 `WINDOW_LEN = 4`（serpentine 行窗口高度），从而保持 host tiling、
device scheduler、device kernel 三层的切分边界对齐。
```

The three pathologies it names, `:5-9`, are worth carrying because they are the routing signatures:
non-square blocking with B streaming (adjacent cores advancing N naively invalidate B repeatedly,
making MTE2 bandwidth the bottleneck); `M % baseM` / `N % baseN` slivers sharing a window with full
blocks, so the window's critical path is dragged to `baseM` and the sliver's saving is eaten; and
`totalCnt = mCnt × nCnt` not dividing `blockNum`, so only the first `endBlockIdx + 1` cores work in
the last round.

The window construction, `:106-108`:

```
mCoreNum_   = Min(WINDOW_LEN, mCnt_);      // 行窗口高度，封顶 4
mainRow_    = mCnt_ / mCoreNum_ - 1;       // 稳态区窗口层数
mTailCoreNum_ = mCnt_ - mCoreNum_ * mainRow_;  // 末窗口实际高度
```

and the reversal, `:137-139`: `if (rowIdx & 1) { nTileIdx = nCnt_ - 1 - nTileIdx; }`.

The invariant, `:142`:

```
关键不变量：**行窗口的边界在整个调度中是神圣的**——机制 B 的合并区、机制 C 的切分区都必须沿
`WINDOW_LEN` 对齐，不能打碎窗口。
```

The three-layer division of labour, `:344-358`, names which host function computes what:
`OptimizeEdgeBasicBlock` → mechanism B's `mBaseTailSplitCnt` / `mTailMain`; `CalcTailBasicBlock` →
mechanism C's `mTailTile` / `nTailTile`; the device scheduler rebuilds all of it from an eight-field
minimum description set (`:415`).

`WINDOW_LEN = 4` is corroborated *within the same repo* by the analysis-layer constant table
(`ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:36`, "`WINDOW_LEN` | 4 |
边缘合并滑动窗口，一次最多合并 4 个基本块") and by StreamK's own scheduler
(`streamk_design.md:92`). Two files in one repo are one origin (RULES.md Art. 3), so this raises nothing;
it is recorded because the *agreement across three files* is itself the evidence that the constant
is a contract rather than a local choice.

What upstream never states: why 4. No derivation, no measurement, no relation to any hardware
quantity. It is a literal in three layers.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The design isolates one
mechanism at a time, because the entry's claim is that they are independent and a combined run
cannot show that.

Baseline B0: non-full-load matmul, mechanisms A, B, C all off (linear row-major traversal, no tail
merge, no last-round split), at a shape with all three pathologies present —
`totalBlockCnt > aicNum` several times over, a real `m % baseM` sliver, and
`totalCnt % aicNum ≠ 0`.

Arm A: enable serpentine only. Record MTE2 total bytes (`msprof --aic-metrics=PipeUtilization`
plus the L2 read counters), MTE2 segment time and kernel time. Mechanism A's whole claim is B-side
reuse, so **bytes moved** is the primary readout and time is secondary; a time win with unchanged
bytes would mean the mechanism worked for some other reason.

Arm A′: enable serpentine but delete the odd-row reversal (`rowIdx & 1` branch), leaving the window
grouping. This separates "window grouping" from "reversal", which upstream does not, and it is what
the OVERTURN is written against.

Arm B: serpentine + tail merge. Record per-core busy time spread (max − min over cores) and kernel
time. Mechanism B's claim is critical-path shortening, so **core-time spread** is primary.

Arm C: serpentine + last-round split. Record active core count in the final round (echoed from the
kernel) and kernel time. Mechanism C's claim is core activation, so **active core count** is
primary; upstream's worked case predicts 5 → 20 (`0308`).

Arm ABC: all three, to check that the composition is not worse than its parts — the failure mode
the shared constant exists to prevent.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median,
reported beside every figure. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that `aicNum` is a literal (queried, `950:0207`) — every one of the
three mechanisms' gates is written against it; that the mechanisms are separable in the shipped code
(if a build refuses to disable one independently, that is reported as a finding, not worked around).

## 5 · Checker — acceptance declared before the run
Verdict variables, each tied to its mechanism's own claimed quantity, all with the floor.

`b_reuse` = (B0 MTE2 bytes − Arm A MTE2 bytes) / B0 MTE2 bytes. Pass: positive and outside the
floor. `spread_drop` = (B0 core-time spread − Arm B spread) / B0 spread. Pass: positive and outside
the floor. `core_gain` = Arm C final-round active cores / B0 final-round active cores. Pass: > 1.

`reversal_share` = (Arm A′ MTE2 bytes − Arm A MTE2 bytes) / (B0 MTE2 bytes − Arm A MTE2 bytes) —
the fraction of mechanism A's benefit attributable to the reversal rather than to the grouping. The
OVERTURN fires iff `b_reuse` is inside the floor. If `b_reuse` is real but `reversal_share` is
inside the floor, the entry is corrected in place: the window grouping would be doing the work and
the reversal would be decoration.

The exit code is not the verdict. Three guards. First, every arm's output is compared elementwise
against one CPU reference: mechanism B rewrites tile sizes and mechanism C rewrites GM offsets, and
both have off-by-one failure modes that produce a fast wrong answer (`0307`, `0308`). Second — the
input that makes this checker go red — Arm C is repeated with `mTailTile × nTailTile` forced past
the gate `(endBlockIdx_ + 1) × totalTailTile_ ≤ blockNum_`; the kernel **must** fall back to
`1 × 1` and the echoed active-core count **must not** exceed `blockNum`. If the echo reports more
active cores than exist, the echo is fabricated and every `core_gain` is void. Third, primary
readouts are per-mechanism quantities, never kernel time alone: a checker that only reads kernel
time cannot tell which of three mechanisms moved it, which is the exact failure this entry exists
to prevent.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Upstream supplies no timing
for SWAT at all — the file is a design and code walkthrough with two worked *arithmetic* examples
(`0307`, `0308`) and no measured before/after anywhere.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream gives no performance number for SWAT: not for the whole,
not for any mechanism, not for any shape. So this entry establishes a *design* and its stated
intent, and nothing about magnitude — a consuming skill must not attach a benefit figure to it. It
does not establish that the three mechanisms are separable in the shipped code, only that upstream
describes them as independent. It does not establish why `WINDOW_LEN` is 4; no upstream document
derives it, and the value's agreement across three files is agreement, not evidence. The
`A_FULL_LOAD_MODE` sub-mode is named by upstream and not analysed by it, and is not established here
at all. BOARD is `family-claimed(unverified)`: no file in this family names a chip (`0347`).
Nothing transfers to the other book (RULES.md Art. 1).

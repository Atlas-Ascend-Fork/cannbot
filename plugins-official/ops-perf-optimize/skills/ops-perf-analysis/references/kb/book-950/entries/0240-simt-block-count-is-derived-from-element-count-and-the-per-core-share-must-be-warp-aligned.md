```
ID:        0240-simt-block-count-is-derived-from-element-count-and-the-per-core-share-must-be-warp-aligned
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — two upstream files state it, both `upstream/skills-dev-main`, therefore ONE
           origin (RULES.md Art. 3). Nothing was compiled and no launch was measured.
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-simt-tiling-design/references/guide.md:15-25 — "## 核数切分 / 总核数 =
           ceil(输出元素总数 / 单核最少处理元素数) / 单核最少处理元素数建议 1024 / 单核最少处理元素需要
           对 warp (即 32) 进行对齐" … "- 合理设置 `perCoreElements` 避免负载不均 /
           - 避免总数据量少但启动核数多的场景"
SOURCE:    ops/ascendc-simt-tiling-design/SKILL.md:14-20 — "| 多核切分 | 按 UB 单次处理量切分 |
           按元素总量切分（ceil(总量/单核最少元素数)） | … | UB 使用 | 全量使用 | 仅核内共享场景使用，
           DCache >= 32KB |"
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:19-23 — "### 核数（Block Dim）/
           - 通过 tiling 侧 `SetBlockDim` 接口设置 / - 对应 CUDA 中的 Block 概念 /
           - 切分公式：`总核数 = ceil(输出元素总数 / 单核最少处理元素数)`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 SIMT kernel whose per-core element count is deliberately not warp-aligned and which
           shows no throughput penalty against an aligned one at the same total work — the alignment
           requirement would then be advice with no mechanism behind it.
```

# 0240 · SIMT block count is derived from element count, and the per-core share must be warp-aligned

## 1 · Claim
Upstream asserts that SIMT multi-core splitting works differently from SIMD: where a SIMD operator splits
by how much fits in UB per pass, a SIMT operator splits by **element count** —
`总核数 = ceil(输出元素总数 / 单核最少处理元素数)` — and the block count is set on the tiling side via
`SetBlockDim`. Upstream asserts a recommended per-core minimum of 1024 elements and a hard shape
constraint on it: the per-core element count must be **aligned to the warp size, 32**. Upstream asserts
two scheduling cautions: set `perCoreElements` so the load is even, and avoid launching many cores for a
small total. Upstream asserts that UB is not the splitting axis at all in SIMT — it is used only where
intra-core sharing is needed, with DCache ≥ 32 KB reserved. Not established here: nothing was compiled and
no launch was measured.

## 2 · The wrong branch this removes
The wrong branch is not arithmetic — it is that an agent brings the SIMD tiling method to a SIMT operator,
because that method is the one every other tiling document in this material teaches.

A SIMD tiling routine computes how much of the tensor fits in UB, derives a tile, and derives the block
count from the tile. Applied to a SIMT kernel this is doubly wrong. It sizes the split against a buffer
the kernel barely uses — SIMT reads GM directly (0243) and reserves most of UB for DCache (0237) — so the
derived tile is meaningless. And it produces a block count from the wrong quantity, so the launch may be
far too small or far too large for the work.

The alignment requirement is the part that fails silently. A per-core share that is not a multiple of 32
leaves a partial warp on every core: the hardware still schedules a full 32-lane warp, and the surplus
lanes execute with nothing to do. With 1000 elements per core instead of 1024, the last warp is 8/32
occupied — a small waste. With a per-core share of 40, it is 8/32 on the second warp, i.e. a quarter of
the launch idle. The kernel is correct in every case, the profile shows full warp occupancy because the
warps *are* resident, and nothing reports that the lanes inside them were masked.

The two cautions upstream attaches are the same failure from two directions. Uneven `perCoreElements`
means the slowest core sets the kernel's duration while the others finish early — a load-balance loss
that a per-core average hides completely. And launching many cores for a small total pays the launch cost
on every core to do almost nothing; upstream's separate guidance is that when threads idle, the remedy is
to reduce the **core count**, not the thread count (0232 §3), which only makes sense if the block count
is the free variable and the thread count is not.

The third branch: the 1024 figure is a *recommendation* (建议) and the 32 is a *requirement* (需要对齐).
An agent that treats both as hard, or both as soft, gets one of them wrong. 1024 is itself a multiple of
32, so following the recommendation satisfies the requirement automatically — which is precisely why an
agent that deviates from 1024 for a good reason may not notice it has broken the alignment.

## 3 · Ground / Source
`ascendc-simt-tiling-design/references/guide.md:15-25`, the core-splitting section in full:

> ## 核数切分
>
> ```
> 总核数 = ceil(输出元素总数 / 单核最少处理元素数)
> 单核最少处理元素数建议 1024
> 单核最少处理元素需要对 warp (即 32) 进行对齐
> ```
>
> - 通过 tiling 侧 `SetBlockDim` 接口设置
> - 合理设置 `perCoreElements` 避免负载不均
> - 避免总数据量少但启动核数多的场景

Note the register difference inside one code block: 建议 1024 (recommended) against 需要对 warp 对齐
(required). Upstream marks which is which and a reader copying the block keeps both words.

The model contrast, `ascendc-simt-tiling-design/SKILL.md:6-20`:

> SIMT 算子的切分设计与 SIMD 有本质差异。SIMD 以 UB 切分 + Buffer 规划为核心，SIMT 以核数切分 +
> 线程数设置为核心，不涉及 UB 切分和 Buffer 规划。
>
> | 要素 | SIMD | SIMT |
> |------|------|------|
> | 多核切分 | 按 UB 单次处理量切分 | 按元素总量切分（ceil(总量/单核最少元素数)） |
> | 单核并行 | UB Buffer + 向量指令 | 线程数（constexpr 编译期常量） |
> | 数据搬运 | 需显式 Load/Store | 支持直接读写 GM |
> | UB 使用 | 全量使用 | 仅核内共享场景使用，DCache >= 32KB |
> | Buffer 规划 | inQueue/outQueue/tmpBuf | TBuf（仅在需要共享内存时使用） |

不涉及 UB 切分和 Buffer 规划 — SIMT tiling does not involve UB splitting or buffer planning at all. That
is the sentence that removes §2's first wrong branch, and it is in the skill's opening paragraph.

The three-level hierarchy, `npu-arch/references/simt-arch-guide.md:13-23`, which places the block count
on the tiling side and the thread count on the kernel side:

> | 层级 | 概念 | 对应 CUDA | 设置方式 |
> |------|------|----------|---------|
> | 启动核数 | Block 数量 | Grid 中的 Block 数 | tiling 侧 `SetBlockDim` |
> | 启动线程数 | 单核线程数 | 单 Block 线程数 | kernel 侧 `constexpr` 常量 |
> | Warp | 32 线程分组 | Warp | 硬件自动分组 |
>
> ### 核数（Block Dim）
> - 通过 tiling 侧 `SetBlockDim` 接口设置
> - 对应 CUDA 中的 Block 概念
> - 切分公式：`总核数 = ceil(输出元素总数 / 单核最少处理元素数)`

Three rows, three owners: the host sets the block count, the kernel fixes the thread count at compile
time (0232), and the hardware groups warps with no one setting anything. The alignment requirement lives
at the boundary between the first and the third — a host-side number that must respect a hardware
quantum nobody controls.

The thread-stride loop that consumes the split,
`ascendc-simt-programming-best-practices/references/thread-stride-pattern.md:7-13`:

```cpp
for (uint64_t index = static_cast<uint64_t>(
         AscendC::Simt::GetBlockIdx() * AscendC::Simt::GetThreadNum() + AscendC::Simt::GetThreadIdx());
     index < count;
     index += (AscendC::Simt::GetThreadNum() * AscendC::Simt::GetBlockNum())) {
    // 每个线程处理 stride 间隔的元素
}
```

with the decomposition at `:25-33`: the initial index linearises the thread's global position, and the
stride is the total thread count across all cores, "确保每个元素只被一个线程处理". This is the grid-stride
idiom, and it matters here because it makes the kernel **correct for any block count** — the loop bound is
`count`, not a per-core share. So a wrong block count never produces wrong output; it produces idle lanes
or uneven load, which is exactly why §2's failures are silent.

All four files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3), stated in three skills.

Upstream supplies **no cost figure** for misalignment and no formula for `perCoreElements` beyond
"合理设置". So the requirement is stated and its magnitude is not.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — the alignment cost, total work held constant. Build one SIMT elementwise kernel and launch it with
per-core shares of 1024, 1023, 1000, 992 (= 31×32), 544 and 33, adjusting the block count so the *total*
element count is identical in every configuration. Minimum `aiv_time` over 50 repetitions. Under the
stated mechanism, shares that are multiples of 32 sit on one curve and non-multiples pay a penalty
proportional to the wasted fraction of the final warp. The penalty *pattern* is the readout, not any
single time.

Arm B — the block-count sweep, which tests the formula rather than the alignment. Hold the per-core share
at 1024 and sweep the total element count so the block count runs from 1 to beyond `GetCoreNumAiv()`
(0216, 0217). Record where throughput stops improving. Upstream's caution about launching many cores for
a small total predicts a regime where added blocks cost more than they contribute; locating it is the
number a tiling routine needs and no source supplies.

Arm C — the load-balance arm, which is upstream's other caution. Construct a split in which one core
receives a share 2× the others at the same total, and compare against an even split. The kernel duration
should track the slowest core. This is what makes "合理设置 `perCoreElements`" measurable rather than
exhortatory.

Arm D — the SIMD-method control, which prices §2's first wrong branch directly. Derive a block count the
SIMD way — from a UB-capacity tile — for the same operator and shape, and compare against the
element-count derivation. Both produce correct output (the grid-stride loop guarantees it); the
difference in duration is the cost of using the wrong model, and it is the only arm that measures the
mistake this entry exists to prevent.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. All configurations of one comparison run on one named die
in one session. Note that each configuration may need its own build if `LAUNCH_BOUND` must match the
launch (0232); build md5s are recorded and confirmed distinct where they differ.

## 5 · Checker — acceptance declared before the run
Verdict variable `alignment_penalty[share]`, from Arm A — `aiv_time(share)` divided by
`aiv_time(nearest multiple of 32 above)`, at constant total work.

Pass is declared now as: `alignment_penalty` within run variance of 1.0 for every share that **is** a
multiple of 32, **and** strictly above 1.0 for at least one share that is not. Both clauses in one
predicate. The second is the operative one: if no non-multiple share shows a penalty, the alignment
requirement has no observable mechanism on this board, and it is advice rather than a constraint — which
is a real finding and is declared now so a null result cannot be read as confirmation.

`useful_block_ceiling` (Arm B) — the block count beyond which throughput stops improving. Reported with
run variance, **no pass threshold**: upstream states a caution and no number, and inventing one would let
a convenient result read as validation.

`imbalance_cost` (Arm C) — duration of the uneven split divided by the even split. Pass iff it approaches
the ratio of the largest share to the mean, which is what "the slowest core sets the duration" predicts. A
value near 1.0 would mean the imbalance is absorbed somewhere and upstream's caution is unnecessary.

`wrong_model_cost` (Arm D) — reported. Either sign is informative; a near-zero cost would mean the two
derivations coincide at the shapes tested and the distinction matters less than §2 argues.

The positive fixture, declared before the run: Arm A must include a share of 32 exactly, with a block
count large enough to cover the same total. Its `alignment_penalty` must be 1.0 by construction — it is a
multiple of 32 — while its *absolute* time should be far worse than the 1024 case because of launch
overhead per core. If the harness reports the 32-share configuration as fast as the 1024 one, the block
count is not affecting the launch and every Arm A and Arm B figure is void. Without this the checker reads
only "some configurations were slower", which is the known blind species: at constant total work, many
things change when the share changes.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no block
count was set, and nothing was timed. Upstream supplies no cost figure for misalignment or for
over-launching anywhere in this scope, so there is not even an upstream measurement to record as upstream
text.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that warp misalignment costs anything, where the
useful block ceiling sits, or what an uneven split costs — Arms A-D are all open, and upstream states the
alignment requirement with **no magnitude**. There is **no second origin**: three upstream skills state it
and all are one repo, and no ini field or header expresses a tiling rule. The whole claim rests on the warp
quantum being 32, which is 0234 and is itself unverified with no ini backing — §4's fixture is designed
around that dependency. It does not establish the 1024 recommendation, which upstream marks 建议 and
which no source in this scope derives; note that 1024 satisfies the 32-alignment automatically, so
following it hides the requirement rather than testing it. It supplies **no formula** for
`perCoreElements` beyond upstream's 合理设置, so an agent choosing a share is choosing on judgement. It
says nothing about how the block count interacts with the thread count, which is a separate compile-time
constant capped at 2048 (0232) and whose product with the block count is what the grid-stride loop
actually consumes. It says nothing about UB or DCache sizing, which is 0237 and is the axis SIMT tiling
explicitly does *not* use. Nothing transfers to the other book (RULES.md Art. 1): upstream states SIMT hardware
does not exist before DAV_3510.

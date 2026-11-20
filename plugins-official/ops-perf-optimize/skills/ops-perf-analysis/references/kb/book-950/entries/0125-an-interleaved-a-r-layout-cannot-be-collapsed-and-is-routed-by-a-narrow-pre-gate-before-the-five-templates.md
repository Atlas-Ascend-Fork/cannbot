```
ID:        0125-an-interleaved-a-r-layout-cannot-be-collapsed-and-is-routed-by-a-narrow-pre-gate-before-the-five-templates
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:44-84 —
           "位于合轴之后、五模板决策树之前。仅处理 **不可合成单 R 的交错布局**；不命中则原样落入
           五模板。" · "平方和（及任何可交换归约）**不要求按 R 逻辑顺序累加**，可按内存**物理连续
           顺序**做大 burst 载入（16–64KB），把 A/R 分离从 HBM 碎读搬到 UB 内做**链式规约**。
           arch35 硬件 `ReduceSum` 只支持 AR/RA 两种排布"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured interleaved case on a named 950 board that satisfies every pre-gate
           condition and is still slower than the five-template fallback — the gate would then not
           be narrow enough, which is precisely the failure upstream already recorded twice (0127).
```

# 0125 · An interleaved A/R layout cannot be collapsed and is routed by a narrow pre-gate before the five templates

## 1 · Claim
Upstream asserts that when retained and reduced axes strictly alternate in memory, axis collapse
fails — adjacent axes have different types so they cannot merge, and no axis has size 1 so none can
be dropped — leaving multiple alternating A/R axes that cannot be pressed into a single R, so the
five templates' `(A1, R, A0)` precondition does not hold. Upstream asserts a pre-gate placed after
collapse and before the five-template tree, which either routes to one of two interleaved
continuous-load templates or falls through unchanged. Upstream states the reasoning: a square-sum,
and any commutative reduction, does not require accumulation in R's logical order, so data can be
loaded in physical memory order at large burst (upstream says 16–64 KB), moving the A/R separation
off HBM scattered reads and into a chained reduction inside UB. Upstream further asserts a hardware
constraint that shapes the design: `arch35` hardware `ReduceSum` supports only AR and RA layouts,
so an interleaved case is decomposed into two chained AR/RA steps inside UB. The pre-gate's
universal conditions: dtype in {fp32, fp16, bf16} (int32 excluded because integer squares must be
exact), `axisNum ≥ 6`, the inner block (last 4 axes) physically contiguous (innermost stride 1, and
the axis before the inner block having stride equal to the inner block's element count), and the
inner block's total bytes 32 B-aligned. Not established here.

## 2 · The wrong branch this removes
The wrong branch is not a bad plan — it is a plan that is 8× slower and looks reasonable. Upstream
states the mechanism at `:48`: an interleaved case pushed through the five templates makes `CopyIn`
transpose while it moves, gathering scattered R elements, and the innermost burst collapses to the
innermost R length — in their case #18, 2 elements, i.e. 8 bytes. MTE2 then saturates
(`ratio≈0.995`) at an effective bandwidth of about 145 GB/s, and every diagnostic an agent would
consult says "memory bound", which is true and useless. The agent optimises the wrong thing: it
enlarges tiles, adds double buffering, and none of it changes an 8-byte burst.

The second wrong branch is the inverse and upstream has already fallen into it: applying the
interleaved templates too widely. That is 0127, and it is why this entry insists the gate is narrow
rather than treating "interleaved" as sufficient.

The third is subtle and worth stating because it generalises past this family: the enabling
property is *commutativity of the reduction*, not any property of the layout. The optimisation
works because `Σ x²` may be accumulated in any order. For a non-commutative reduction the same
transformation is not slow, it is wrong.

## 3 · Ground / Source
`reduction/fallback/tiling-flow.md:44-84`, the pre-gate in full:

```
## 3.1 多轴交错前置判定（Step 0.5）

> 位于合轴之后、五模板决策树之前。仅处理 **不可合成单 R 的交错布局**；不命中则原样落入五模板。

**背景问题**：交错 case 若走五模板，CopyIn 会边搬边转置把散落的 R 聚拢，导致最内 burst 极小（如 #18 内块最内 R 长度=2 → burst **8B**）、MTE2 打满（ratio≈0.995）、有效带宽仅 ~145GB/s。

**核心洞察**：平方和（及任何可交换归约）**不要求按 R 逻辑顺序累加**，可按内存**物理连续顺序**做大 burst 载入（16–64KB），把 A/R 分离从 HBM 碎读搬到 UB 内做**链式规约**。arch35 硬件 `ReduceSum` 只支持 AR/RA 两种排布，故多轴交错在 UB 内用**两步 AR/RA 链式分解**完成。

输入: 严格交替后的 axisShape[], axisNum, isTailR, dtype, axisStride[], coreNum, ubSize

┌─ 不是纯交错病态？（任一不满足 → 回退五模板）
│    dtype ∉ {fp32, fp16, bf16}             → 五模板  // int32 平方需精确整数，不走 fast
│    axisNum < 6                            → 五模板
│    内块（末 4 轴）非物理连续              → 五模板
│         校验: 最内轴 stride==1
│                内块前的分块轴 stride==内块元素数
│    内块整块字节非 32B 对齐                → 五模板  // kernel 连续 DataCopy 载入要求
│
├─ axisNum 偶数且 isTailR（ARAR...AR，尾轴 R，S=axisNum-4）
│     → 【交错-tail-R / fast】两段式，见 §11.1
│       附加门控（全满足才命中）:
│         R1(最内 R)×dtypeSize ≤ 16B        // ★ burst 病态判据（连续化收益区）
│         rowsSize ≥ 8                      // ★ rows 太小则两步规约+屏障反超增益
│         chunkA0 ≥ 1 且 chunkA0 == szA0   // 内块 A0 无需分块（需分块实测负收益 #17 -9%）
│         groupCnt = ∏(外层 A 轴) ≤ coreNum
│       否则 → 回退五模板（如 #17 内块需分块，chunkA0=14<32）
│
├─ axisNum 奇数且 !isTailR（ARAR...A，尾轴 A，S=axisNum-4）
│     → 【交错-tail-A / fast-RARA】无 workspace，见 §11.2
│       附加门控（全满足才命中）:
│         slabCnt = ∏(内块外 A 轴) ≥ 1
│         slabCnt × 2 ≥ coreNum            // slab 太少并行度不足（#9 slabCnt=8 判负）
│         innerRowElems ≥ 512              // ★ 内块每行太小则连续载入无收益（#13/#15 回退）
│       否则 → 回退五模板/group
│
└─ 其余交错形态（其它轴数 / dtype 不符 / 内块不连续 / 非 32B 对齐）
      → 回退五模板（normal/group）

> ⚠️ **判据不是 `mte2_ratio`**。真正决定赢面的是 **基线最内 burst 大小**（tail-R：内块最内 R 长度）与 **内块每行大小**（tail-A：innerRowElems）。
```

The two templates' structures, `:401-435`. tail-R (`fast`, two-phase, even `axisNum ≥ 6`, inner
block `[A0,R0,A1,R1]`): cores within a group split the `rows` axis at index `S-1`; Phase 1 loads
contiguous inner-block slices, casts up to fp32, squares and accumulates, then reduces in two steps
— step 1 along the innermost `R1` (an AR reduction) giving a partial sum per `[A0,R0,A1]` plane,
step 2 a scalar accumulation over `R0` per `(a0,a1)` pair, which upstream notes is done to
`规避 adv_api AR 边界高估` — and writes partial sums to workspace; a `SyncAll` and Phase 2 merge
follow, except when `coresPerGroup == 1`, where the sync is skipped entirely.
`workspace 字节 = groupCnt × coresPerGroup × outLanes × 4`, `outLanes = A0 × A1`.
tail-A (`fast-RARA`, odd `axisNum ≥ 7`, inner block `[R0,A0,R1,A1]`): each core owns whole slabs,
so there is no cross-core R split, no workspace and no Phase-2 barrier; step 1 loads contiguously
along the outermost inner-block `R0` with `burst = innerRowElems × dtypeSize` and no gather, giving
`acc[innerRowElems] = Σ_R0 x²` with `innerRowElems = A0×R1×A1`; step 2 does an RA reduction along
`R1` per A-plane.

The comparison table, `:437-448`:

```
| 维度 | tail-R（fast） | tail-A（fast-RARA） |
|------|---------------|---------------------|
| 轴数 / 尾轴 | 偶数≥6 / R | 奇数≥7 / A |
| dtype | fp32/fp16/bf16 | fp32/fp16/bf16 |
| 内块 | `[A0,R0,A1,R1]`（末 4 轴 S..N-1） | `[R0,A0,R1,A1]`（末 4 轴 S..N-1） |
| 分核对象 | rows 轴（S-1），group 内多核切 | slab（∏外层A轴），每核独占 |
| workspace | 需要（coresPerGroup>1）；coresPerGroup==1 免 | **无** |
| Phase2 / SyncAll | 需要（coresPerGroup>1） | 无 |
| 内块规约 | step1 规约 R1 → step2 逐(a0,a1)标量累加 R0 | step1 连续载入累加 R0 → step2 逐平面 RA 规约 R1 |
| 实测代表 | #18 **8.29×**（1128→136µs，burst 8B，fp32） | #11 **1.39×**（171→123µs，内块 17KB，fp32） |
```

The concrete case that motivates the whole design,
`reduction/fallback/example/euclidean_norm/experience.md:101-107`:

```
`[4,2,2,640,32,32,2,2]` axes=[1,3,5,7] → `ARARARAR`，内块=末 4 轴 `[A0=32,R0=32,A1=2,R1=2]`：

- **走五模板会发生什么**：CopyIn 边搬边转置把散落的 R 聚拢，最内 burst = 最内 R1 长度 = 2 元素 = **8B**。MTE2 打满（ratio≈0.995），有效带宽仅 ~145GB/s → 1128µs。
- **走 tail-R fast**：按内存物理连续做大 burst（sliceStride=R0×A1×R1=128 元素/面），A/R 分离移到 UB 内两步 AR 规约（step1 规约 R1，step2 逐(a0,a1)标量累加 R0），跨核部分和经 workspace 两段式合并。→ **136µs，8.29×**。
- groupCnt=轴0×轴2=4×2=8≤72 ✓，chunkA0 算出 ==A0=32（内块整块放得下，无需分块）✓ → 命中。
```

Re-derived: `sliceStride = R0 × A1 × R1 = 32 × 2 × 2 = 128` elements ✓; `groupCnt = 4 × 2 = 8` ✓;
`1128.5 / 136.1 = 8.29` ✓.

A dtype-gate history note upstream discloses at `experience.md:140`, preserved because it scopes
the whole measured table: `⚠️ **dtype 门控已更新**：上表为 fp32-only 时代的实测（#19 等 fp16 case
因当时门控仅 fp32 而回退 normal）。当前 host 门控已放宽至 fp32/fp16/bf16（载入即升 fp32），
fp16/bf16 交错 case 现已具备命中 fast 的资格，但其最终选型仍受 burst 病态 / rowsSize / 32B 对齐 /
chunkA0 等硬阈值约束，**fp16/bf16 fast 路径需重新上板验证**`. Upstream's own measurements are
declared out of date for two of the three admitted dtypes, by upstream.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Reproduce #18 first, exactly: `[4,2,2,640,32,32,2,2]`, `axes=[1,3,5,7]`, fp32, at the queried core
count. Build both plans — five-template fallback and interleaved tail-R — with one compiler pin,
md5 each, host echo of `axisNum`, `isTailR`, `fastInnerStart`, `fastGroupCnt`, `fastCoresPerGroup`,
`fastInnerChunkA0`, `workspace_size`. Check both against an fp64 reference within a tolerance
declared in advance: the two plans accumulate in different orders, so bit-identity is not expected
and asserting it would be the wrong check. Record `aiv_time`, MTE2 ratio, achieved bandwidth and
the innermost burst size under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped, per case. The baseline arm's MTE2 ratio near 0.995 and bandwidth near 145 GB/s are
upstream's numbers on their platform and are treated as predictions to be confirmed or not, not as
givens.

Then the dtype arm upstream explicitly asks for: repeat #18 and #11 at fp16 and bf16, which
upstream's table never measured under the current gate. This is the arm most likely to produce a
new finding.

Then the gate-condition arm: for each of the four universal conditions, construct one case that
fails exactly that condition and passes the rest (int32 dtype; `axisNum = 4`; inner block made
non-contiguous by a stride change; inner block bytes not 32 B-aligned), force the interleaved
template anyway where the host allows it, and record what happens — a wrong result, a launch
failure, or merely a slower run. A gate whose violation costs nothing is a gate worth relaxing.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is 72
(queried, and `groupCnt ≤ coreNum` and `slabCnt × 2 ≥ coreNum` both depend on it); that `ubSize` is
192 KB (queried — 0131); that a forced template was the template used (echo required); that the
fp32 measurements transfer to fp16/bf16 — upstream says they do not.

## 5 · Checker — acceptance declared before the run
Verdict variable `fast_gain(case)` = baseline median `aiv_time` / interleaved median `aiv_time`.
Declared before the run: #18 reproduces iff `fast_gain ∈ [6.0, 10.0]` (upstream: 8.29×) and #11
iff `fast_gain ∈ [1.2, 1.6]` (upstream: 1.39×). A value outside those bands is reported as the
number measured, in either direction. The OVERTURN fires iff any case passing every pre-gate
condition has `fast_gain < 1.0` — the gate is then not narrow enough, which is the exact failure
upstream recorded for its earlier gate version (0127). The gate-condition arm's verdict is a
four-row table: per condition, `violation_cost ∈ {wrong-result, launch-failure, slower, no-effect}`.

The exit code is not the verdict. Two guards. First, template identity: the interleaved arm must
echo a non-zero `fastGroupCnt` (tail-R) or `raraSlabCnt` (tail-A) and the baseline arm must echo
neither; a silent fallback would otherwise make `fast_gain ≈ 1` read as an overturn. Second, burst
observability: the measured innermost burst of the baseline arm must be reported, and if the
profile cannot separate it the checker returns `void` for the mechanism claim rather than inferring
it from the timing — the timing alone cannot distinguish "burst was the cause" from "something else
was".

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 8.29×, 1.39×, 1128 µs,
136 µs, `ratio≈0.995` and ~145 GB/s figures quoted in §3 are upstream's readouts on upstream's
platform; this book has run nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish the burst threshold, the `rowsSize ≥ 8`
floor, the `innerRowElems ≥ 512` floor, or `axisNum ≥ 6` — those are 0126 and 0127's subject and
none is verified. It does not establish that `arch35` hardware `ReduceSum` supports only AR and RA
layouts; upstream asserts that as a hardware fact with no reference, and it is the load-bearing
premise of the two-step chained decomposition. It does not establish that the interleaved templates
are correct for any non-commutative reduction — upstream restricts them to commutative ones and so
does this entry. Upstream's measured table is declared by upstream to predate the current dtype
gate, so its fp16/bf16 rows establish nothing about the current gate. `arch35` and `Ascend 950 /
arch35（dav-3510）` name a family, not a board, so BOARD is `family-claimed(unverified)` and no
specific board is named anywhere in this family. §4 names 950PR/950DT because that is where our run
would happen. Nothing here is established for any 910-family board.

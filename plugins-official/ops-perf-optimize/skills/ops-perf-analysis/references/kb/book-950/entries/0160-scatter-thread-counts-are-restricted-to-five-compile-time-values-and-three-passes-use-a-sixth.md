```
ID:        0160-scatter-thread-counts-are-restricted-to-five-compile-time-values-and-three-passes-use-a-sixth
LABEL:     trap
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scatter/fallback/tiling-fields.md:45,50 —
           "`threads` ... **只能取 `{1024, 512, 128, 32, 8}`** —— `LAUNCH_BOUND` / `dim3` 要求编译期
           常量，核内按 `switch (threads)` 展开" · "②③④⑤⑥：`threads` 按 pass 固定（`add` 与两条仲裁
           pass 是 **256**，其余 1024）" ; scatter/fallback/tiling-flow.md:163,180-188 —
           "### 3.2 ②③④ 元素级并行：固定 1024 线程" · "**每 block 线程数按 pass 定，不是一律 1024**
           （实测值，非推导）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board that launches a scatter pass with 256 threads per block —
           256 is then a legal thread count and the stated five-value restriction is wrong; a build
           that refuses 256 kills the three passes that specify it instead.
```

# 0160 · Scatter thread counts are restricted to five compile-time values, and three passes use a sixth

## 1 · Claim
Upstream asserts that the per-block thread count for scatter passes may take only five values —
`{1024, 512, 128, 32, 8}` — because `LAUNCH_BOUND` and `dim3` require compile-time constants and the
kernel expands them with a `switch (threads)`. Upstream asserts, in the same file five rows later and
again in the flow document, that three specific passes use **256** threads per block: the ② arbitration
pass, the ③ winner pass, and ④'s `add`. 256 is not in the five-value set. Upstream additionally
asserts a section heading declaring element-level parallelism uses a fixed 1024 threads, and states
seventeen lines below it that the count is per-pass and explicitly not uniformly 1024
(`不是一律 1024`), marking those values `实测值，非推导` — measured, not derived. For path ① upstream
asserts a different rule: choose the largest candidate that still fills the machine, falling back to
the smallest, because a fixed 512 threads leaves shapes with few fibers on one or two cores, measured
at a 0.02× speed-up near `numFibers ≈ 1024`. Not established here.

## 2 · The wrong branch this removes
An agent implementing this family reads the restriction, builds a `switch` over five cases, and then
meets three passes specifying a sixth. Whatever it does next is wrong in some direction: adding 256
to the switch contradicts a stated interface constraint; rounding 256 to 512 or 128 discards a value
upstream marks as measured; taking the heading's "fixed 1024" discards all three. The three
resolutions differ in performance by an amount upstream elsewhere calls measurable, and none of them
is flagged anywhere.

The `实测值，非推导` annotation is the part worth carrying beyond this family. Upstream is marking
which of its numbers are measurements and which are derivations, in-line, at the point of use — and
for ④'s `add` it goes further, giving the mechanism as a conjecture rather than a fact
(`推测是原子冲突下的重试放大`) and attaching a re-measurement condition
(`换硬件/CANN 版本应重测`). That is a claim carrying its own overturn condition, written by upstream,
and it is the model this book's form exists to generalise.

Path ①'s rule removes a different wrong branch: fixing the thread count at a comfortable value. The
measured consequence is stated — a fixed 512 gives `numFibers ≈ 1024` shapes one or two cores and a
0.02× speed-up, i.e. a fiftyfold slowdown. The correct rule inverts the usual instinct: take the
*largest* thread count that still fills the machine, because total threads is fixed by `numFibers` and
the goal is spreading the memory issue across cores, not packing threads into few blocks.

## 3 · Ground / Source
The restriction, `scatter/fallback/tiling-fields.md:42-45`:

```
| 字段 | 类型 | 语义 |
|---|---|---|
| `blocks` | int64 | 该 pass 的 block 数，一律 `min(coreNum, ...)` |
| `threads` | int32 | 该 pass 每 block 的线程数。**只能取 `{1024, 512, 128, 32, 8}`** —— `LAUNCH_BOUND` / `dim3` 要求编译期常量，核内按 `switch (threads)` 展开 |
```

The sixth value, five rows later, `:47-51`:

```
各 pass 的取值来源见 [tiling-flow.md §3](tiling-flow.md#3-各路径的-tiling-推导)。要点：

- ① 纤维独占：`threads` 由"能铺满核的最大候选值"决定，`blocks = min(coreNum, ceil(numFibers/threads))`
- ②③④⑤⑥：`threads` 按 pass 固定（`add` 与两条仲裁 pass 是 **256**，其余 1024），`blocks = min(coreNum, ceil(count/1024))`
- ⑤：`blocks = min(coreNum, numFibers)`（一条 warp 一条纤维，每 block 32 个 warp）
```

The heading that says 1024 and the table that says otherwise,
`scatter/fallback/tiling-flow.md:163-188`:

```
### 3.2 ②③④ 元素级并行：固定 1024 线程，按元素数算 block

int64_t calc_scatter_blocks(int64_t count) {       // count = epTotal 或 numelData
    int64_t need = (count + 1024 - 1) / 1024;
    return min(coreNum, max<int64_t>(1, need));
}

各路径的 `count` 取值：

| 用途 | count |
|---|---|
| ②的 arb pass、③的 win pass、④的原子 pass | `epTotal` |
| ②的 init/unpack、③的 fill-zero、④半精度的 cast | `numelData` |
| ③的 apply pass | 见 §3.4（按密度二选一） |

**每 block 线程数按 pass 定，不是一律 1024**（实测值，非推导）：

| pass | 线程/block | 备注 |
|---|---|---|
| ② arb（打包键 `atomic_max`） | 256 | |
| ③ win（裁决 `atomic_max`） | 256 | |
| ④ `add` | **256** | 实测优于 1024，推测是原子冲突下的重试放大，**换硬件/CANN 版本应重测** |
| ④ `amin`/`amax`/`multiply` | 1024 | |
| ③ apply、fill-zero、⑤、⑥ | 1024 | |
```

Note also that `calc_scatter_blocks` divides `count` by the literal 1024 regardless of the pass's
actual thread count, so for a 256-thread pass the block count is computed as if each block held 1024
threads — under-provisioning blocks by 4× relative to the work, or, read the other way, relying on
the grid-stride loop to cover the remainder. Upstream does not comment on this. Registered as
C-950tiling-031.

Path ①'s selection rule and its measured motivation, `:145-161`:

```
### 3.1 ① 纤维独占：线程数是唯一调优点

并行宽度被 `numFibers` **死死卡住**，固定 512 线程/block 会让纤维数小的 shape 只拿到 1~2 个核（实测 `numFibers ≈ 1024` 时加速比 **0.02×**）。

> **策略：在能铺满核的前提下取最大的线程数；铺不满就取最小的。**
> 总线程数不变，但把访存发射摊到尽可能多的核上。

constexpr int32_t CANDIDATES[] = {1024, 512, 128, 32, 8};
int32_t chosen = 8;                                  // 兜底取最小
for (int32_t t : CANDIDATES) {
    if ((numFibers + t - 1) / t >= coreNum) { chosen = t; break; }   // 能铺满核的最大线程数
}
int64_t blocks = min(coreNum, (numFibers + chosen - 1) / chosen);

`LAUNCH_BOUND` / `dim3` 要求**编译期常量** ⇒ 线程数只能在这 5 个候选值里选，核内按 `switch (threads)` 展开。
```

Re-derived: the loop takes the first candidate whose block count reaches `coreNum`, scanning
descending, so it does select the largest satisfying value — the code matches the stated strategy. The
fallback `chosen = 8` is the smallest, matching `铺不满就取最小的`.

⑤'s rule, `:190-200`:

```
int64_t calc_scatter_warp_blocks(int64_t numFibers) {
    return min(coreNum, max<int64_t>(1, numFibers));
}

每 warp 的排序轮数 = `ceil(sIdx / 32)`，每轮 15 步 bitonic。**这个乘积是⑤的固定成本**，也是纤维数门槛的由来（§5）。
```

Upstream's own note on why per-case thread tuning was not done, `:366`:

```
| 逐用例挑最优线程数 | 未做 | 1024 净收益更好但不均匀（个别用例退化 8~24%）；按用例挑最优收益很小**且没有正当的形状判据** |
```

That is a declined optimisation with a stated reason — no legitimate shape-based criterion — which is
the same discipline as 0142's anti-extrapolation fence and worth recording as such: the number was not
tuned per case *because* tuning it would have no rule behind it.

Registered as C-950tiling-030 (the five-value restriction against the three 256-thread passes) and
C-950tiling-031 (the block formula's fixed 1024 divisor).

## 4 · Procedure
Proposed, runnable later on Ascend950PR — the board upstream names; a 950DT run is a separate claim.
Never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — is 256 legal? Build ④'s `add` pass at 256 threads per block and record whether it compiles
and launches. This alone settles C-950tiling-030: if it builds, the five-value restriction is wrong as
stated; if it does not, the three passes specifying 256 cannot be implemented as written. One
compiler pin; host echo of the launch configuration actually used, since a silently-clamped launch
would answer neither question.

Arm 2 — the per-pass values. For ④'s `add` on a `starved` shape, build at 128, 256, 512 and 1024
threads (those that are launchable) and record `aiv_time` and atomic retry counts if the profile
exposes them. Upstream predicts 256 fastest and conjectures retry amplification as the mechanism;
the retry counter, if available, is what tests the conjecture rather than just the ordering. Repeat
for ②'s arb pass and ③'s win pass.

Arm 3 — path ①'s selection rule. Sweep `numFibers` across the point where each candidate stops filling
the machine — around `coreNum × 8`, `× 32`, `× 128`, `× 512`, `× 1024` — and at each point build the
plan the rule selects plus a fixed-512 plan. Upstream predicts a 0.02× speed-up for fixed-512 near
`numFibers ≈ 1024`; that specific point is included.

Arm 4 — the block divisor. On a 256-thread pass, build with `blocks` from `ceil(count/1024)` and from
`ceil(count/256)` and record both times, so C-950tiling-031's consequence is measured rather than
argued.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is a
literal (queried, 0141 — every rule here contains it); that a requested thread count was the one
launched (host echo required); that the profile exposes atomic retries — if it does not, arm 2 reports
the ordering and explicitly declines the mechanism claim.

## 5 · Checker — acceptance declared before the run
Verdict variable `threads256_legal` from arm 1, a tri-state: `builds`, `refused`, or `clamped`.
Declared before the run: the five-value restriction is supported iff `threads256_legal = refused`; the
OVERTURN fires iff it is `builds`. A `clamped` result means neither and the checker reports it as
such rather than choosing.

Verdict `best_threads(pass)` from arm 2, the value with the lowest median `aiv_time`; upstream's
claim is supported iff it is 256 for all three named passes. Verdict `fixed512_penalty` from arm 3 at
`numFibers ≈ 1024`, compared against the stated 0.02×. Verdict `divisor_gain` from arm 4.

The exit code is not the verdict: a clamped launch exits 0 and runs correctly at a thread count nobody
requested, which would make `threads256_legal` read as `builds` from a launch that used 1024. The host
echo of the actual block and thread dimensions is therefore mandatory at every point and the checker
goes red on any mismatch. Second guard: every timed arm's output is compared elementwise against a CPU
reference on duplicated-index input (0158), because a thread-count change alters the atomic
interleaving and a wrong result would otherwise be timed as a win.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 0.02× figure, the
`256 优于 1024` ordering and the `8~24%` per-case degradation range are upstream's readouts on
Ascend950PR; this book has reproduced none of them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. `BOARD: 950PR` records the board upstream's evidence names; the stratum,
not the board field, says who measured. The entry does not resolve whether 256 is legal — Art. 7
forbids resolving a contradiction by preferring one sentence, and §4 arm 1 is what would settle it. It
does not establish any of the per-pass thread counts, and upstream itself attaches a re-measurement
condition to the most specific of them (`换硬件/CANN 版本应重测`), naming neither the hardware nor the
CANN version they were measured under. It does not establish the 0.02× figure or the 8–24 %
degradation range, neither of which carries a case identity. It does not establish that the fixed-1024
block divisor is a defect rather than a deliberate reliance on grid-stride coverage. Nothing here is
established for 950DT or for any 910-family board.

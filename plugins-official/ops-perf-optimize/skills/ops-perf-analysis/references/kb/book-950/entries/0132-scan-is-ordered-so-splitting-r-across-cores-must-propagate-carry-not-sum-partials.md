```
ID:        0132-scan-is-ordered-so-splitting-r-across-cores-must-propagate-carry-not-sum-partials
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/index.md:18 and
           scan/fallback/tiling-flow.md:208-238 — "Reduce 沿 R 求 1 个统计量（可交换，分核合并顺序
           无关）；Scan 输出每个前缀位置（**有序**，跨核/跨块合并必须**保序传播进位**）" ·
           "Phase A ... Phase B: 对 totals[0..rBorrow-1] 做 exclusive 前缀 combine（保序）→
           carry[p] ... Phase C" · "**轮空的核也必须走到 `SyncAll`**（提前 `return` 会死锁）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a cross-core scan on a named 950 board that produces correct output while merging
           segment totals in an order-independent way — the ordering requirement would then not
           bind, which this claim says it must.
```

# 0132 · Scan is ordered, so splitting R across cores must propagate carry, not sum partials

## 1 · Claim
Upstream asserts the structural difference between reduction and scan and its consequence for
multi-core tiling: a reduction produces one statistic along R and its cross-core merge is order
independent, while a scan produces every prefix position and is therefore ordered, so any
cross-core or cross-block merge must propagate carry in order — the earlier segment's accumulated
result becomes the later segment's initial value in the combine, not a partial sum to be added.
Upstream asserts the three-phase structure: Phase A computes each segment's local prefix scan and
records the segment-end `(val, idx)` as `totals[p]`; Phase B takes an exclusive prefix combine over
`totals[0..rBorrow-1]`, in order, producing `carry[p]`; Phase C combines `carry[p]` into each
segment's local prefix, with segment 0 taking no carry. Upstream asserts
`usedCoreNum = rBorrow` and `workspaceBytes = rBorrow × W × (sizeof(P)+4)`. Upstream asserts two
hard constraints on the single-launch form: a `PipeBarrier<PIPE_ALL>()` must precede `SyncAll` so
segment results have reached GM, and idle cores must still reach `SyncAll` — an early `return`
deadlocks, so the emptiness test must be written as `bool active = ...` rather than
`if (...) return`. Not established here.

## 2 · The wrong branch this removes
A harness agent that has just learned reduction's BlockSplitR (0124) will transfer it: split R
across cores, write partial results to workspace, `SyncAll`, merge. Three of those four steps are
right and the merge is wrong. For a reduction the merge is a commutative fold; for a scan the merge
must be an *exclusive prefix* over segment totals, and the result must then be re-combined into
every element of the following segments. An agent that folds instead of scanning produces output
that is correct in segment 0, correct in shape everywhere, and wrong in every later segment — and
wrong in a way that a spot-check of the first elements will not find.

The deadlock constraint removes a second wrong branch that is worse than wrong output. The natural
way to skip an idle core is `if (segCount == 0) return;`. With `SyncAll` in the code path, that
hangs the kernel: the barrier waits for cores that have exited. Upstream states the fix as a coding
shape — `bool active = ...` — because the failure is not detectable by reasoning about the algorithm
at all.

The third: Phase A's real job. Upstream is explicit that Phase A needs only the segment's
`(min, argmin)`, which is a *reduction*, not a scan, and therefore carries no log factor — reusing
the scan code and discarding its output costs a measured 38 %. And Phase A must not opportunistically
write its local prefix, because Phase B would then have to read the whole output back and rewrite
it, taking memory traffic from `x + output` to `x + 2×output`.

## 3 · Ground / Source
The distinction, `scan/fallback/index.md:18`:

```
> **Scan 与 Reduce 的本质区别**：Reduce 沿 R 求 1 个统计量（可交换，分核合并顺序无关）；Scan 输出每个前缀位置（**有序**，跨核/跨块合并必须**保序传播进位**）。因此 Scan 多核切 R 时的进位不是"部分和相加"，而是"前段累积作为后段初值"，见 [tiling-flow.md §4 保序进位](tiling-flow.md#4-跨核-r-分段的保序进位scan-特有)。
```

The three-phase structure and the three implementations,
`scan/fallback/tiling-flow.md:208-238`, in full:

```
## 4. 跨核 R 分段的保序进位（Scan 特有）

> **一等分支，不是可选增强。** 与 Reduce 的 group/BlockSplitR（可交换合并部分和）不同，Scan 跨核切 R 必须**保序传播进位**：前段的累积结果作为后段每个元素的初值参与 combine。

**触发**：`M×N` 极小（切行只能用满极少核，`items ≪ core_num`）且 R 超长（如 R≥4096）。典型 1D `[1000003]`（M=N=1）。

分段: R 切 rBorrow 段（≈ core_num），段 p 覆盖 [pStart,pEnd)，partLen=ceil(R/rBorrow)
Phase A（每核）: 段 p 局部前缀扫描 → 段内 y/idx（全局 r 索引），段末 (val,idx) 记为 totals[p]
Phase B: 对 totals[0..rBorrow-1] 做 exclusive 前缀 combine（保序）→ carry[p]
Phase C（每核）: 段 p 用 carry[p] 与段内局部前缀 combine → 最终 y/idx（p=0 无进位）

三种进位实现，推荐按 (B) → (C) 的顺序演进：

- **(A) 核内 SyncAll + 原地对数层 Sklansky**（cumsum 生产实现，`ceil(log2(rBorrow))` 层，
  无 workspace，进位读被扫核输出行）。需要 `SetScheduleMode(1)` 与 host 预算多层调度表，复杂。
- **(B) host 编排 2 次 launch**（先跑通用这个）：phase A 只读求段结果写 workspace，
  phase B 读回前序段进位重扫并写出，stream 顺序即跨核屏障，风险低。
- **(C) 单次 launch + `AscendC::SyncAll()`**（最终形态）：`kernel launch 的固定开销约 9 µs`，
  在小用例上和整个搬运时间同量级，值得用核间全同步换掉。

**(B) 的两个必须**：phase A 只需要段内的 `(min, argmin)`，那是**归约**不是扫描，
没有 log 因子，别复用扫描代码再丢掉输出（实测省 38%）；也别让 phase A 顺手写出局部前缀，
否则 phase B 要回读整个输出再写一遍，访存量从 `x + 输出` 涨到 `x + 2×输出`。

**(C) 的两个约束**：`SyncAll` 前要 `PipeBarrier<PIPE_ALL>()` 保证段结果已落 GM；
**轮空的核也必须走到 `SyncAll`**（提前 `return` 会死锁），所以判空要写成
`bool active = ...` 而不是 `if (...) return`。

`usedCoreNum = rBorrow`；`workspaceBytes = rBorrow × W × (sizeof(P)+4)`（val + int32 idx）。
```

The mode-3/4 workspace has a second, differently-shaped formula at `:203-204`:

```
**workspace 预算**（mode 3/4）：`workspaceBytes = M * wsSegs * WS_SLOT_I32 * sizeof(int32_t)`，
其中 `WS_SLOT_I32 = 8`（每段独占 32B 槽位，只用前 2 个 int32 存 val+idx）。
```

`rBorrow × W × (sizeof(P)+4)` at `:238` and `M × wsSegs × 8 × 4` at `:203` describe the same
workspace for the same path with different quantities: the first is dense (val + int32 index, no
slot padding), the second reserves a 32 B slot per segment and uses 8 bytes of it. At `M = W` and
`rBorrow = wsSegs` with `sizeof(P) = 4`, the first gives `rBorrow × W × 8` and the second gives
`M × wsSegs × 32` — a factor of 4. Registered as C-950tiling-013.

The 1D performance trap that motivates the whole branch, `:345`:

```
3. **1D 超长 R 的性能陷阱**：流式模板对 `M=N=1` 只出 1 个 work-item（W=1，单核，逐 r 微 DMA），实测 100 万点约 230µs。识别 `items ≪ core_num` 并转 §4 跨核借 R。
```

Three numbers in this section are measurements without conditions: `kernel launch 的固定开销约
9 µs`, `实测省 38%`, and `实测 100 万点约 230µs`. None carries a board, a dtype, a core count, a
tool or a repetition count. The 9 µs launch figure is the one most likely to be reused outside its
context — it is a platform property if true, and it is stated in a bullet about which carry
implementation to prefer.

A design update upstream published against itself, `:251-254`, preserved because a correction in
place is exactly the practice this book records:

```
> **更正**：先前记的「不要各核自己合并、必须三阶段」是错的。合并的是**向量**而非标量，
> `segs=9` 时只有 18 条向量 combine（约 100 条指令）；读放大
> `segs² × nLen × 8B = 83KB`，完全可忽略。**两阶段（各核归约 → SyncAll → 各核自己合并前序段
> 并重扫）就够了**。只有 `segs` 很大时才值得引入「派一个核算完前缀再写回」的三阶段。
```

The `N > 1` generalisation this correction belongs to (`:240-254`) is marked `尚未实现，已定方案` —
a designed but unbuilt path, with a measured counter-example (`M=1, R=1009, N=1021` fp16, `vec 62%`,
latency-bound, `nLen` pinned to 16 elements by 32 B alignment) motivating it.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Correctness arm first — the ordering claim is a correctness claim, so it is tested numerically, not
by timing. Take the 1D case `[1000003]` fp32 Cumsum and its Cummin variant. Build three kernels
with one compiler pin: (a) correct carry propagation per Phase A/B/C; (b) a deliberately wrong
merge that folds segment totals commutatively, as an agent transferring reduction's BlockSplitR
would write it; (c) single-core streaming as the reference. Compare (a) and (b) against (c) and
against an fp64 CPU reference elementwise, reporting the first differing index and the fraction of
elements wrong for each. Arm (b) is a poison arm and is retained in the report whether or not it
bites — if a commutative fold produces correct output, this entry is overturned.

Deadlock arm: build one variant of (a) with `if (segCount == 0) return;` in place of the
`bool active` shape, on a case with more cores than segments, and run it under a wall-clock timeout.
A hang is the expected result and is recorded as one; a completion is a finding that contradicts
upstream.

Barrier arm: build (a) with and without the `PipeBarrier<PIPE_ALL>()` before `SyncAll`, run each 50
times, and count mismatching runs. A race that fires rarely is still a race; a single run proves
nothing, which is why the repetition count is fixed in advance.

Launch-overhead arm: measure the fixed kernel launch cost directly — launch an empty kernel 200
times and take the median inter-launch device time — so upstream's `约 9 µs` becomes a number with
conditions attached, on a named board with a recorded toolkit pin.

Refuses to assume: that a free die stays free; that a die may be substituted; that `core_num` is 64
or 72 (queried, and `rBorrow ≈ core_num`); that a hang is a deadlock rather than a slow run — the
timeout is declared in advance at 100× the correct variant's time; that the 38 % Phase-A saving
transfers (it is not re-measured here and is not claimed).

## 5 · Checker — acceptance declared before the run
Verdict variable `wrong_fraction(arm)`, the fraction of output elements differing from the fp64
reference beyond the declared tolerance. Declared before the run: the ordering requirement is
supported iff `wrong_fraction(a) = 0` and `wrong_fraction(b) > 0`. The OVERTURN fires iff
`wrong_fraction(b) = 0` — a commutative merge would then be sufficient. `deadlock_observed` is a
boolean from the timeout arm; `race_runs` counts mismatching runs out of 50 in the barrier arm, and
a non-zero count with the barrier present would be a separate, more serious finding.
`launch_overhead_us` is reported with its board, pin and repetition count.

The exit code is not the verdict, and here that matters twice. A deadlocked kernel never exits at
all, so the timeout — not the exit status — is the instrument, and its value is declared in advance.
A kernel producing wrong results exits 0, so the elementwise comparison is the instrument for arms
(a) and (b). The specific blind mode this checker avoids: comparing only the first N elements, or
only a checksum. A commutative merge is correct in segment 0 and a checksum can coincide, so the
comparison is elementwise over the whole output and the checker reports the *first* differing index,
which localises the failure to a segment boundary and distinguishes a merge bug from a scan bug.
The checker fails red if any arm produced no comparison.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `约 9 µs`, `省 38%`,
`约 230µs` and `vec 62%` figures are upstream's, unconditioned; this book has measured nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the 9 µs launch overhead, the 38 % Phase-A
saving or the 230 µs 1D figure — none carries a board, dtype, core count, tool or repetition count.
It does not establish that implementation (C) is better than (B) or (A); upstream recommends an
evolution order and gives one unconditioned number to justify it. It does not resolve the two
workspace formulas (C-950tiling-013). It does not cover the `N > 1` generalisation, which upstream
marks as designed but unimplemented — nothing there can be established from a plan. It does not
establish the trigger threshold, which upstream states three different ways (0135). No board is
named anywhere in the scan family — the deep-dive that surveyed this skill recorded scan as the one
family with no chip named anywhere, and re-reading confirms it — so BOARD is
`family-claimed(unverified)` and every measured number in this family is unscoped. §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.

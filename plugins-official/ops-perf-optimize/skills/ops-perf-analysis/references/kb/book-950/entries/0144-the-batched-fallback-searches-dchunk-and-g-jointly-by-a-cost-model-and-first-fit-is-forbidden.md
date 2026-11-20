```
ID:        0144-the-batched-fallback-searches-dchunk-and-g-jointly-by-a-cost-model-and-first-fit-is-forbidden
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/topk.md:143-175 —
           "TopK(A union B) = TopK(TopK(A) union TopK(B))" · "{min(limit, align32(D)), 2048, 1024,
           512, 256, 128, 64, 32}; limit = 4096 (L) or 4000 (S)" · "cost(non-int64) = chunks *
           groups; cost(int64) = 2 * chunks - 1" · "选择最小 cost；cost 相同保留先遍历到的较大
           dChunk。禁止用「第一个能放进 UB 的候选」替代该模型。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured batched-fallback TopK on a named 950 board where the first candidate that
           fits UB is at least as fast as the minimum-cost candidate across a set of shapes — the
           cost model would then not be earning its complexity, which is exactly what upstream's
           prohibition asserts it does.
```

# 0144 · The batched fallback searches dChunk and G jointly by a cost model, and first-fit is forbidden

## 1 · Claim
Upstream asserts that the batched fallback avoids resident-in-UB long axes by using the TopK
decomposition identity `TopK(A ∪ B) = TopK(TopK(A) ∪ TopK(B))`: the first chunk's local TopK becomes a
running TopK, and each later chunk merges `running[k]` with `chunk[min(k, nC)]` into at most `2k`
candidates and re-runs TopK. Upstream asserts two layouts — L when `inner == 1` with contiguous input
rows and `dChunk <= 4096`, S when `inner > 1` with strided input and `dChunk <= 4000` to stay under
the 2D DMA `blockCount` ceiling — and a batch size of at most `G <= 128` rows per core. Upstream
asserts the search: iterate the de-duplicated candidate set
`{min(limit, align32(D)), 2048, 1024, 512, 256, 128, 64, 32}` from large to small, find for each the
largest `G` that fits the 240 KiB budget, and score with `chunks = ceil(D / dChunk)`,
`groups = ceil(rowsPerCore / G)`, `cost = chunks * groups` for non-int64 and `cost = 2 * chunks - 1`
for int64; take the minimum cost, breaking ties toward the larger `dChunk` reached first. Upstream
asserts the prohibition explicitly: substituting "the first candidate that fits UB" for this model is
forbidden. Not established here.

## 2 · The wrong branch this removes
First-fit is the obvious implementation and upstream names it as the thing not to do. The reason is
visible in the cost expression: `chunks * groups` is a product of two quantities that move in
opposite directions as `dChunk` grows — more elements per chunk means fewer chunks but a smaller
feasible `G`, hence more groups. The product has an interior minimum, so the largest `dChunk` that
fits is generally not the cheapest, and neither is the smallest. An agent that takes the first fit
gets a plan that is legal, correct and off the minimum by a factor no check reports.

The int64 cost formula removes a second wrong branch, and it is the more interesting one:
`cost(int64) = 2 * chunks - 1` has no `G` in it. Upstream states why — the safe int64 path needs two
call classes, chunk selection and running merge — so batching rows buys nothing there. An agent that
applies the non-int64 model to int64 will search `G` at real cost for no benefit and may pick a
smaller `dChunk` to enlarge a `G` that does not matter.

Third, the layout split. `dChunk <= 4000` for S rather than 4096 is not a rounding: it is stated as
avoiding the 2D DMA `blockCount` upper limit. An agent that unifies the two limits at 4096 produces
an S-branch plan whose DMA descriptor is out of range, which is a launch failure rather than a slow
run — and one that unifies at 4000 loses 96 elements per chunk on every L case.

## 3 · Ground / Source
`sort/topk.md:136-175`, §5.1 and §5.2 in full:

```
### 5.1 两种布局和公共算法

- L 分支：`inner == 1`，输入行连续，`dChunk <= 4096`。
- S 分支：`inner > 1`，输入跨步，`dChunk <= 4000`，避开 2D DMA blockCount 上限。

每个核批量处理最多 G 行，`G <= 128`。轴 D 分 chunk，使用：

TopK(A union B) = TopK(TopK(A) union TopK(B))

第一块局部 TopK 成为 running TopK；后续把 `running[k]` 与当前 `chunk[min(k,nC)]` 合并为不超过
`2k` 的候选并再次 TopK。这个等式使长轴无需完整常驻 UB，但要求 value/index 在所有阶段成对移动。

### 5.2 dChunk 与 G 联合搜索

按大到小遍历去重后的候选：

{min(limit, align32(D)), 2048, 1024, 512, 256, 128, 64, 32}
limit = 4096 (L) or 4000 (S)

对每个候选找 240 KiB UB 预算内的最大 G。先用实现推导的 API tmp 下界粗筛，再用真实
`GetTopKMaxMinTmpSize` / Sort tmp 查询复核；查询结果用 32 项环形缓存，避免 host tiling 重复执行
数百次昂贵查询。

候选成本：

chunks = ceil(D / dChunk)
groups = ceil(rowsPerCore / G)
cost(non-int64) = chunks * groups
cost(int64)     = 2 * chunks - 1

选择最小 cost；cost 相同保留先遍历到的较大 dChunk。int64 的成本与 G 无关，是因为安全路径需要
chunk 选择和 running merge 的两类调用。禁止用「第一个能放进 UB 的候选」替代该模型。
```

The UB accounting the `G` search runs against, `:177-194`:

```
预算至少包括：输入 compute buffer、输入 index、chunk 输出、running value/index、merge value/index、
API tmp、int64 输出 index。再按条件计入：

- fp16/bf16：raw 输入、fp32 cast、回转输出；
- int64：range-check / b64 Sort scratch；
- S：2D DMA stage、Gather offset、整块输入转置表、输出转置表和 tile；
- L int64：生命周期别名后的实际容量，而不是别名前所有 buffer 的简单相加。

Host 的每一项必须能对应 kernel `InitBuffer`；条件 buffer 必须同时出现或同时消失。关键对齐字段：

| 字段 | 约束 |
|------|------|
| `kPad` | compute dtype 的 32B 对齐行长 |
| `kIdxPad` | int32 index 的 32B 对齐行长 |
| `mergePad` | `2*k` 候选的对齐长度，且不得超过 4096 |
| `tmpSize` | radix floor、TopK API tmp、Sort scratch 的最大值，再按 32B 对齐 |
```

The `Host 的每一项必须能对应 kernel InitBuffer；条件 buffer 必须同时出现或同时消失` rule is the
same placement discipline as 0137's separate-allocation rule, stated as a correspondence obligation
rather than as a formula.

The per-branch gates, `:196-206`:

```
L 使用 `DataCopyPad` 搬 `[G, dChunk]` 连续块并连续写 `[G, k]`。int64 可在生命周期不重叠时复用
已死亡的 input/index buffer，但候选必须满足 `dChunk >= mergePad` 和别名容量门禁。

S 先用 2D Compact DMA 搬 `[dChunk, G]`，再 Gather 为 `[G, dChunk]`：

- 8 位 Gather source offset 不超过 65535B；16 位不超过 131071B；
- 整块输入 Gather 仅在 `dChunk <= 128`、容量和 offset 均满足时使用；旧注释中的 256 不是当前门槛；
- 否则逐行 Gather，但仍保留 batched TopK；
- 输出优先把 `[G, k]` 在 UB 中分块转成 `[k, G]` 后批量 DMA；G<8、容量或 offset 不满足才逐行写。
```

The line `旧注释中的 256 不是当前门槛` is a disclosed stale-constant correction — upstream is
telling the reader that a number they will find in comments elsewhere is wrong, and giving the
current one (128). That is the same practice as the reduction family's disclosed gate misfire (0127),
and it is worth recording as such rather than only as a threshold.

The 8-bit and 16-bit Gather source-offset ceilings (65535 B and 131071 B) are the only place in this
domain where a DMA descriptor field width is stated. `131071 = 2^17 − 1` and `65535 = 2^16 − 1`, so
these read as field widths rather than as calibrated policy — which would make them capability
limits, unlike the thresholds 0142 fences. Upstream does not say which they are.

The constants table at `topk_host_tiling.md:212-215` restates the ceilings:
`| fixed small-axis max tileWidth | 4096 |`, `| fallback L/S max dChunk | 4096 / 4000 |`,
`| fallback max G | 128 |`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Cost-model versus first-fit, which is the claim. Pick six batched-fallback cases spanning both
branches and three dtypes: L at (`inner=1`, `rows=4096`, `D=8192`, `k=64`) fp32 and int64; S at
(`inner=64`, `rows=1024`, `D=16384`, `k=32`) fp32 and fp16; plus one L and one S with `D` small
enough that `min(limit, align32(D))` is the first candidate. For each case enumerate the full
candidate set, compute the largest fitting `G` per candidate against the *queried* UB (0141, 0140),
record the whole `(dChunk, G, chunks, groups, cost)` table before building anything — the prediction
goes on record first — then build and run the minimum-cost candidate, the first-fitting candidate,
and the two candidates adjacent to the minimum. One compiler pin, md5 per binary, host echo of
`branch / rowsPerCore / G / dChunk / kPad / kIdxPad / mergePad / tmpSize`. Compare values *and*
indices elementwise against a CPU reference on every arm. Record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

int64 arm: on the int64 case, additionally build at two different `G` values with `dChunk` fixed, to
test upstream's claim that int64 cost is `G`-independent. If the times differ beyond the variance
floor, the int64 cost formula is incomplete.

Layout-ceiling arm: build an S case at `dChunk = 4096` (violating the stated 4000 limit) and record
whether it fails to launch or merely runs. This is a poison arm and is retained whether or not it
bites; it is what distinguishes a DMA field limit from a policy number.

Refuses to assume: that a free die stays free; that a die may be substituted; that the UB budget is
240 KiB (queried and probed per 0140); that the API tmp estimate equals the real query (both are
computed and the difference recorded, per 0141); that a candidate that fits was used (host echo
required); that value correctness implies index correctness.

## 5 · Checker — acceptance declared before the run
Verdict variable `model_gain(case)` = (first-fit median `aiv_time` − minimum-cost median
`aiv_time`) / first-fit median. Declared before the run: the cost model earns its complexity iff
`model_gain > variance_floor` on at least four of six cases and is never worse than
`−variance_floor`. The OVERTURN fires iff `model_gain ≤ variance_floor` on all six — first-fit would
then be sufficient. A second verdict `cost_ranks`: the Spearman correlation between predicted cost
and measured time over the four built candidates per case, reported per case; a negative correlation
on any case is a finding about the model's form, not just its winner. `int64_G_independent` is a
boolean from the int64 arm. `s_ceiling_kind ∈ {launch-failure, slower, no-effect}` from the layout
arm.

The exit code is not the verdict: a batched TopK whose running-merge drops an index exits 0 with
plausible values, which is why both outputs are compared elementwise and the checker fails red if
only one was. Second guard: the `(dChunk, G)` echo must match the candidate under test at every
point, and a mismatch excludes the point and is reported — a host that silently re-searched would
otherwise make first-fit and minimum-cost the same run and `model_gain` zero, a false overturn.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no candidate was enumerated against a real capacity. The entry does not
establish that the cost model beats first-fit, does not establish the 4096/4000/128 ceilings, and
does not establish whether the Gather offset limits are field widths or policy — upstream states them
without saying which, and 0142's fence covers only the numbers upstream explicitly labels policy. It
does not establish the `旧注释中的 256` correction beyond recording that upstream disclosed it. It
does not establish the UB accounting's completeness; upstream says `预算至少包括` — at least — which
is an open list by construction. It does not cover the API tmp query itself (0141). `Ascend 950 /
DAV_3510` names an architecture, not a board, so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT because that is where our run would happen. Nothing here is established for any
910-family board.

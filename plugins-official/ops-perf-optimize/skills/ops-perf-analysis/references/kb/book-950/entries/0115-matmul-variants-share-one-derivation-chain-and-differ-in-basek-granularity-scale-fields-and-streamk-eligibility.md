```
ID:        0115-matmul-variants-share-one-derivation-chain-and-differ-in-basek-granularity-scale-fields-and-streamk-eligibility
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-variants.md:5,11-16,
           36-40,101,131 — "所有变体共享同一套 SWAT → FullLoad → StreamK 推导链，仅在初始参数、Cube
           粒度、数据布局和特有约束上有差异" · "baseK | 16 | 32" · "baseK 上限 | 256 | 128" ·
           "**默认不启用 StreamK**（B ≥ 2 时与 batch 并行语义冲突）" · "**默认不启用 StreamK**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured batch_matmul (B ≥ 2) or group_matmul run on a named 950 board where forcing
           StreamK beats the default path on the same shape — that would make the two default
           disables a conservative default rather than a semantic conflict.
```

# 0115 · MatMul variants share one derivation chain and differ in baseK granularity, Scale fields, and StreamK eligibility

## 1 · Claim
Upstream asserts that the five matmul variants — `a16w16`, `mxfp4`, `mxfp8`, `batch_matmul`,
`group_matmul` — all run the same SWAT → FullLoad → StreamK derivation chain and differ only in
initial parameters, Cube granularity, data layout and variant-specific constraints. Upstream
states the specific deltas: `a16w16` is the baseline with FP16/BF16 operands, Cube granularity
`m0=k0=n0=16`, `baseK = 16`, its `stepKa/stepKb` not passed to the kernel (which reconstructs them
from `kL1/baseK`); the MX variants use `baseK = 32`, carry per-group Scale metadata with
`per-group = 32`, pass `stepKa/stepKb` down because the Scale factors depend on them, and cap
`baseK` at 256 for mxfp4 versus 128 for mxfp8; `batch_matmul` adds a three-dimensional
`B × mCnt × nCnt` core split and disables StreamK by default because at `B ≥ 2` it conflicts with
batch parallelism; `group_matmul` sub-routes to split-M or split-N, splits `kL1` into
`kAL1`/`kBL1`, omits `nBufferNum` entirely (the kernel's compile-time `L1_BUFFER_NUM` governs),
and also disables StreamK by default. Not established here.

## 2 · The wrong branch this removes
The shared chain is genuinely shared, which is what makes the deltas dangerous: an agent that
derives a plan for `mxfp4` using the `a16w16` steps gets a plan that is correct in shape and wrong
in three places at once — `baseK = 16` where the granularity is 32, no Scale reservation in the L1
budget, and `stepKa/stepKb` omitted from the emitted struct where the kernel needs them. The first
two silently shrink or overflow L1; the third produces a kernel reading fields that were never
written. None of these is a schema violation.

The field-name divergences are a second trap of the same kind. `l0cDB` for `a16w16` and `dbL0C`
for the others carry identical semantics; an agent that normalises the name loses the ability to
say which variant a plan was written for, and an agent that does not normalise reports a missing
field. Upstream flags this explicitly (`语义一致`), and the cross-check table at
`tiling-fields.md:132-144` is the artifact that carries it.

The two `默认不启用 StreamK` statements remove a third: for batch and group shapes with long K, the
StreamK gate may well pass, and an agent applying 0107's decision tree literally will take it. The
variant document says not to, for a stated reason in the batch case (parallel-semantics conflict)
and for no stated reason at all in the group case.

## 3 · Ground / Source
The shared-chain assertion, `matmul/fallback/tiling-variants.md:5`:

```
> 所有变体共享同一套 SWAT → FullLoad → StreamK 推导链，仅在初始参数、Cube 粒度、数据布局和特有约束上有差异。
```

The variant overview, `:11-16`:

```
| 维度 | a16w16 | mxfp4/8 | batch_matmul | group_matmul |
|------|--------|---------|-------------|-------------|
| dtype (A/B) | FP16 / BF16 | FP4(0.5B) / FP8(1B) | 随子变体 | 随子变体 |
| Scale | 无 | UE8(1B), per-group=32 | 随子变体 | 随子变体 |
| 特有维度 | — | — | batch (B) | group (g), M_i 不等 |
| baseK | 16 | 32 | 随子变体 | 随子变体 |
```

The MX sub-table, `:36-40`:

```
| 项目 | mxfp4 | mxfp8 |
|------|-------|-------|
| dtype (A/B) | FP4 (0.5B) | FP8 (1B) |
| Scale | UE8 (1B), per-group=32 | 同左 |
| baseK 上限 | 256 | 128 |
```

`a16w16`'s deltas, `:24-28`: `Cube 粒度：m0=16, k0=16, n0=16`; `SWAT 机制 A（BLOCK_TABLE 负载均衡）
为 a16w16 专属`; `stepKa/stepKb 不下发给 Kernel（Kernel 用 kL1/baseK 还原）`.

`batch_matmul`'s core split, `:76-92`, is a three-way decision tree on `totalTiles = B × mCnt ×
nCnt`: at `totalTiles ≥ aicNum` the batch dimension is split first because batches need no
cross-core synchronisation, with `singleCoreBatch = CeilDiv(B, batchAxisCoreNum)` and remaining
cores splitting the (M, N) plane; at `totalTiles < aicNum` it degrades to `singleCoreBatch = 1`
with each core taking part of one batch's (M, N); at `B > aicNum` it is pure batch splitting with
`usedCoreNum = aicNum` and `CeilDiv(B, aicNum)` batches per core. The heuristic at `:96`:
`若 mCnt×nCnt ≥ aicNum（MN 方向自己能满核），batch 维不参与切核`.

`group_matmul`'s sub-routing, `:112-117`, is a four-row condition table:

```
| 条件 | split-M | split-N |
|------|:------:|:------:|
| M_i 较大（≥ baseM×2），核间负载容易均衡 | ✅ | |
| M_i 很小，N 方向大 | | ✅ |
| A=BF16 无 Scale, B=mxfp 有 Scale（weight-quant） | | ✅ |
| A/B 均为 mxfp（全量对称量化） | ✅ | |
```

with `split-M` walking a cumulative-M index (`groupListGm`) to locate each group's boundaries and
`split-N` cutting N into a main-block-plus-two-tails structure. Its field deltas, `:125-127`:
`kL1 拆分为 kAL1/kBL1（stepKa 可能 ≠ stepKb）`; `不下发 nBufferNum（pingpong 深度由 Kernel 编译期
常量控制）`; `尾块由 Kernel 端按 groupListGm 动态推导，不需 Host 下发`.

The two StreamK disables, `:101` and `:131`, are quoted in the header. Only the batch one carries
a reason.

Two links in the field table point at variant documents that do not exist in this tree:
`tiling-fields.md:91` → `batch_matmul.md §2` and `:100` → `group_matmul.md §3.2`. Both targets are
absent from `matmul/fallback/`, so the variant-specific derivations for `batchAxisCoreNum` and for
split-N's tail structure are unreachable from here. Recorded in
`harvest/standing/950-tiling.md`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Arm 1 — the StreamK defaults, which is the falsifiable half. For `batch_matmul` at B=4 and
`group_matmul` at g=8, choose shapes whose per-instance K passes the SK gate under both readings
of 0108 (K = 65536, M=N=512). Build three kernels per case with one compiler pin: the default
path, StreamK forced on, and the default path with `aicNum` restricted so the MN split alone
cannot fill the machine (this is the regime where StreamK should help if it helps at all). md5
each binary; host echo of `skSingleCoreK`, `tailInfo.kCnt`, `usedCoreNum`; fp64 reference check
within the declared tolerance for every arm — StreamK changes accumulation order, so bit-identity
is not expected and the tolerance is declared before the run. Record `aic_time` and workspace
bytes under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Arm 2 — the granularity deltas. For `mxfp4` and `mxfp8`, build at `baseK ∈ {16, 32, 64, 128, 256}`
and record which values the generator accepts, which it clamps, and where each variant's stated
cap actually bites. This makes `baseK 上限 256 / 128` observable rather than assumed, and it is the
arm that would catch a cap that is stated but not implemented.

Refuses to assume: that a free die stays free; that a die may be substituted; that a `baseK` that
builds is the one that ran (host echo required); that the batch result transfers to group or the
reverse — they are separate cases with separate rows; that a result at B=4 transfers to other
batch counts.

## 5 · Checker — acceptance declared before the run
Verdict variable `default_is_right`, per variant: true iff the default path's median `aic_time` is
at least as good as the forced-StreamK arm's, on both the full-machine and the restricted-`aicNum`
case. Declared acceptance: the two `默认不启用` statements are supported iff `default_is_right` is
true for both variants. The OVERTURN fires iff forced StreamK beats the default by more than 5 %
on either variant with a correct result — the disable is then conservative, not semantic, and this
entry is corrected in place. Arm 2's verdict is `cap_observed`, the largest accepted `baseK` per MX
variant, compared against 256 and 128.

The exit code is not the verdict. The blind mode here is a forced-StreamK arm that silently fell
back: it would time identically to the default and score as confirmation. The guard is structural
and mandatory — the StreamK arm must echo a non-zero `tailInfo.kCnt` and a non-zero workspace
request, and the checker goes red at any case where it does not, rather than recording the
comparison. Arm 2's equivalent guard is the `baseK` echo: a clamped value is recorded as `clamped`
and never counted as an accepted value.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that the derivation chain really is shared —
upstream asserts it and this book has not checked the generated plans against each other. It does
not establish the `baseK` caps, the Cube granularity, or that the field-name divergence is purely
cosmetic. It says nothing about the two missing variant documents (`batch_matmul.md`,
`group_matmul.md`), whose content is simply unavailable here, so `batchAxisCoreNum` and split-N's
tail structure are unestablished by omission rather than by disagreement. It does not establish
why `group_matmul` disables StreamK — upstream gives no reason and this entry invents none. No
board is named in `tiling-variants.md`, so BOARD is `family-claimed(unverified)` and the chip is
unstated; §4 names 950PR/950DT because that is where our run would happen. Nothing here is
established for any 910-family board.

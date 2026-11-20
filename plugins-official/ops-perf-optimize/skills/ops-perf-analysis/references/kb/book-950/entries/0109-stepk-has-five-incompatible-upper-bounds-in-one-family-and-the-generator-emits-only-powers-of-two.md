```
ID:        0109-stepk-has-five-incompatible-upper-bounds-in-one-family-and-the-generator-emits-only-powers-of-two
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:35,159,375
           and matmul/fallback/tiling-fields.md:24,186 and mc2/index.md:64 — "STEPKA_THRESHOLD |
           4" · "stepK的最大值为8" · "stepK 取值 | {1, 2, 4} | SWAT/FullLoad（StreamK 有例外
           stepK=3）" · "上限 4，且只能取 2 的幂" · "stepK ∈ {1, 2, 4}（受上限 4 约束）" ·
           "step_k: 3"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul run on a named 950 board that builds, echoes and executes correctly
           with stepK = 8 — that kills the "上限 4" statements outright; symmetrically, a
           stepK = 3 build that is rejected or clamped kills the StreamK exception and the mc2
           emitted value.
```

# 0109 · stepK has five incompatible upper bounds in one family, and the generator emits only powers of two

## 1 · Claim
Upstream asserts five different things about the legal range of `stepK` — the number of `baseK`
blocks an operand's L1 buffer covers per movement — inside one operator family. In order of
appearance: `STEPKA_THRESHOLD = 4`, described as the StreamK truncation limit; `stepK的最大值为8`,
stated as an affinity constraint in the L1-split derivation; `上限 4，且只能取 2 的幂`, stated in
the field table; `stepK ∈ {1, 2, 4}（受上限 4 约束）`, derived from the generator's doubling
search; and `stepK 取值 | {1, 2, 4} | SWAT/FullLoad（StreamK 有例外 stepK=3）`, in the
cross-variant constant table of the same file whose own constant table declares the threshold to
be 4. A sibling family's worked output emits `step_k: 3`. Upstream separately asserts the
mechanism behind the power-of-two set: the first depth search round doubles (`depth_scale *= 2`),
so `depth_init` can only be a power of two, and `stepK = depth // DB_SIZE(=2)`. Not established
here.

## 2 · The wrong branch this removes
`stepK` sets `kL1 = baseK × stepK`, which is the K extent held in L1 per buffer, which sets the
L1 occupancy, which decides whether `nBufferNum` is 4 or 2 (0113) and whether FullLoad's budget
closes (0110). It is one of the two or three numbers a tuner would sweep first. Without this
entry an agent picks a bound and sweeps to it: bound 8 produces candidates that the generator
cannot emit and that the field table calls illegal; bound 4 excludes the value a sibling family
ships as its recommended output; `{1,2,4}` excludes 3 while the same table's own footnote admits
3 for StreamK. Each choice silently deletes or invents part of the search space, and every
resulting plan is schema-valid, so nothing downstream complains.

The deeper wrong branch is treating the power-of-two set as an architectural fact. Upstream is
explicit that it is not — it is a property of a doubling search in the generator
(`这并非"参考不支持 3"`), and upstream even shows the arithmetic for why 3 is the L1-optimal value
in an implementation that is free to choose it. Under the provenance rule (0104) every one of
these five bounds traces to a literal, not to a chip specification field: all five are software
经验值 and all five are therefore searchable. An agent that mistakes them for hardware limits
never tests the value upstream's own table shows to be best.

## 3 · Ground / Source
Statement 1 — `matmul/fallback/tiling-flow.md:35`, the constants table:

```
| `STEPKA_THRESHOLD` | 4 | StreamK 下 stepK 截断上限 |
```

Statement 2 — `matmul/fallback/tiling-flow.md:156-163`, the L1-split affinity constraints:

```
3. 亲和约束:
   当左矩阵不转置或者右矩阵转置时，要求kl1*sizeof(dtype)是256B对齐
   (al1Size + bl1Size)*sizeof(dtype)要超过48KB
   stepK的最大值为8

通过上述约束确认stepK，且在满足上述约束情况下，尽量选择小的stepK，令MMAD提前启动。
Tiling调优时可给出多组候选stepK。
```

Statement 3 — `matmul/fallback/tiling-fields.md:24`:

```
| `stepK` / `stepKa` / `stepKb` | A/B 在 L1 中每次搬运覆盖的 baseK 块数 | SWAT / Full-Load | SWAT: `depthA1/B1 ÷ DB_SIZE`，互为倍数对齐，上限 4，且只能取 2 的幂（depth 倍增搜索机制约束） | `_cal_step_ks()` / `CalStepKs()` |
```

Statement 4 — `matmul/fallback/tiling-fields.md:177-186`, the mechanism and its conclusion:

```python
depth_scale = 1
while depth_scale * per_depth_size < left_size:
    depth_scale *= 2
depth_scale = depth_scale if depth_scale == 1 else depth_scale // 2
```

> 倍增搜索使 `depth_init` 只能为 2 的幂（1, 2, 4, 8, …）。第二轮独立深度细化时虽逻辑不同（按
> `left_size // per_depth_size` 后做 512 对齐回退），结果仍是偶数。最终
> `stepK = depth // DB_SIZE(=2)`，因此 **`stepK ∈ {1, 2, 4}`**（受上限 4 约束）。

Statement 5 — `matmul/fallback/tiling-flow.md:375`, in the cross-variant constraint table:

```
| stepK 取值 | {1, 2, 4} | SWAT/FullLoad（StreamK 有例外 stepK=3） |
```

This row contradicts `:35` in the same file, where the StreamK-specific truncation is 4, and
contradicts `:305` (`kL1 | baseK × min(stepKa, stepKb, **4**)`), which truncates StreamK's `kL1`
at 4 rather than admitting 3 as an exception.

The emitted value — `mc2/index.md:60-67`:

```yaml
  long_qbmm_tiling:
    base_m: 256
    base_n: 256
    base_k: 256
    step_k: 3
```

Upstream's own arithmetic for why 3 is attractive, `matmul/fallback/tiling-fields.md:191-199`,
quoted because it is the only place in the whole tiling subtree where an L1 capacity is given a
number:

```
   | `L1_BUFFER_NUM` | `kL1` | singleBuffer | × 2 (pingpong) | vs L1 (524 288) |
   |:-:|:-:|:-:|:-:|:-:|
   | 2 | 512 | 139 264 | 278 528 | ✅ 53% |
   | **3** | **768** | **208 896** | **417 792** | **✅ 80%** |
   | 4 | 1024 | 278 528 | 557 056 | ❌ 溢出 |

   `L1_BUFFER_NUM=3` 是在 pingpong 双缓冲约束下 L1 利用率最高的合法值
```

Re-derived here rather than trusted: 139264 × 2 = 278528, and 278528 / 524288 = 53.1 %;
208896 × 2 = 417792, and 417792 / 524288 = 79.7 %; 278528 × 2 = 557056 > 524288. The table's
percentages check out, and it implies `L1 = 524288 B = 512 KB` — the only L1 figure in this
subtree, stated with no board attached, in a footnote of a FAQ. It is registered as a standing
question rather than adopted.

Upstream resolves the tension between statements 3/4 and the emitted 3 not by choosing but by
declaring the two things different concepts: `生成器输出的 stepK 与实施阶段的 L1_BUFFER_NUM 是两个
独立概念` (`:200`). That is a real distinction and it is recorded, but it does not reconcile
`最大值为8` with `上限 4`, which are both statements about the generator's `stepK`.

Registered locally as C-950tiling-003; extends `harvest/CONTRADICTIONS.md` C-008, whose four rows
are re-verified here at their stated lines and extended with `:305` and with upstream's own
L1-utilisation table.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Direct crossing of every disputed value. Fix one shape per dtype class where the L1 inequality
admits a wide `stepK` range — (M=1024, K=4096, N=2048, BF16) and (M=N=K=1024, FP8/mxfp8) — and
build with `stepK ∈ {1, 2, 3, 4, 6, 8}`, forcing the value into the tiling struct rather than
letting the generator choose. One compiler pin; md5 every binary; host echo of `stepK`, `kL1`,
`nBufferNum`, `depthA1`, `depthB1` for every build. For each point record: build result;
launch result; output match against an fp64 reference within the operator's declared tolerance;
`aic_time` and MTE2 bytes under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5
dropped, per case.

Second arm — the capacity the table implies. Read the L1 capacity from the platform at runtime
(the L1 counterpart of `GetCoreMemSize(CoreMemType::UB)`, per 0141) and evaluate upstream's
occupancy table at `baseM=baseN=baseK=256, FP4` against the queried value rather than against
524288. If the queried capacity differs from 524288 the whole `L1_BUFFER_NUM=3` argument moves,
and that is reported before any timing.

Refuses to assume: that a free die stays free; that a die may be substituted; that a `stepK` that
builds was the `stepK` used (host echo mandatory); that L1 is 512 KB on the board under test;
that a result at BF16 transfers to the MX dtypes, whose `baseK` granularity differs (32 vs 16,
`matmul/fallback/tiling-variants.md:16,66`).

## 5 · Checker — acceptance declared before the run
Verdict variable `legal_set`, the set of swept `stepK` values that build, echo the requested
value, launch, and produce a correct result. Declared before the run: statement group {3,4}
(`{1,2,4}`) is supported iff `legal_set = {1,2,4}`; statement 2 (`max 8`) is supported iff
`8 ∈ legal_set`; the StreamK exception and the mc2 emitted value are supported iff
`3 ∈ legal_set`. A second variable `best_stepK` is the value with the lowest median `aic_time`
among `legal_set`, reported per shape. The OVERTURN fires on `8 ∈ legal_set` (killing the "上限 4"
statements) or on `3 ∉ legal_set` (killing the exception and the mc2 output).

The exit code is not the verdict. This checker's known blind spot is clamping: a generator that
rewrites an out-of-range `stepK` back to a legal one produces a build that compiles, runs, and is
correct, which would place the requested value in `legal_set` on the strength of an execution
that used something else. The host echo of `stepK` AND of the derived `kL1` is therefore required
per point, any mismatch marks the point `clamped` and excludes it from `legal_set`, and the
checker goes red if any point is `clamped` without being reported. It also fails if the `msprof`
row count is short, rather than reading whichever rows exist.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no value was crossed. The entry does not pick a bound — Art. 7 forbids
resolving a contradiction by preferring an author — and it does not establish that any of the
five statements is wrong, only that they cannot all be right. It does not establish the L1
capacity: 524288 appears once, in a FAQ table, with no board and no provenance, and this entry
treats it as unverified. It does not establish that a legal `stepK` on one shape is legal on
another; the L1 inequality is shape-dependent, so `legal_set` is per case. No board is named in
any of the source files, so BOARD is `family-claimed(unverified)` and the chip is unstated. §4
names 950PR/950DT because that is where our run would happen, not because upstream measured.
Nothing here is established for any 910-family board.

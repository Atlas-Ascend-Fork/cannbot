```
ID:        0120-mc2-tiling-refuses-to-proceed-without-a-host-side-tilingdata-print
LABEL:     procedure
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/mc2/fallback/fallback-algorithm.md:28-30 —
           "Step 0 — 前置检查： ├─ baseM/baseN/N_core 缺失 → 返回「需先打印 TilingData」" ;
           mc2/index.md:34-41 — "TilingData 打印（前置必需） ... 检查 host tiling 代码中
           `PrintTilingData` 调用（通常被注释，如 `// PrintTilingData(tilingData);`） ...
           **长块和短块各有独立 tiling data**，须分别打印"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a documented MC² case where the comm-split parameters derived from inferred
           baseM/baseN/usedCoreNum match the printed TilingData values exactly across a set of
           shapes — the print would then be verifiable-by-inference rather than a precondition.
```

# 0120 · MC² tiling refuses to proceed without a host-side TilingData print

## 1 · Claim
Upstream asserts a hard precondition on the MC² tiling path: the comm-split derivation consumes
`baseM`, `baseN` and `N_core` (`usedCoreNum`) from the matmul tiling engine's actual output, and
if any of the three is missing the algorithm's Step 0 returns the refusal
`需先打印 TilingData` rather than proceeding. Upstream states how to obtain them: find the
`PrintTilingData` call in the host tiling code — usually commented out, as
`// PrintTilingData(tilingData);` — uncomment it or add a printf after the tiling computation for
`baseM`, `baseN`, `baseK`, `usedCoreNum`, `stepK`, referring to `quant_matmul_tiling_base.h`'s
implementation. Upstream further asserts that the long and short blocks have independent tiling
data and must be printed separately. Not established here.

## 2 · The wrong branch this removes
The wrong branch is inference, and it is very tempting: `baseM` and `baseN` look derivable from
the shape and the matmul family's own §3.2 selection rule (0112), and `usedCoreNum` looks like the
machine's core count. All three inferences are unsound here. `usedCoreNum` is not the core count —
`matmul/fallback/tiling-flow.md:186` makes it `tailBlockCnt × mTailTile × nTailTile` whenever a
tail exists and the block count is not greater than one, so it can be far below `aicNum`. `baseM`
and `baseN` come out of a scored enumeration whose capacity constraints use values this book
cannot resolve (0111), so an agent re-deriving them is re-deriving through unknowns. And every one
of the six comm-split parameters is computed *from* these three: `nBlockCnt = ceil(N / baseN)`,
`minMBlockCnt = max(1, ceil(N_core / nBlockCnt))`, `minLongMSize = minMBlockCnt × baseM`. An error
in any input propagates into the block structure, and the resulting plan is fully self-consistent
and wrong.

This is the same discipline as the skill's MC² data gate at the workflow level — capture first,
advise second — and it is the reason the refusal string is worth carrying as a claim: a
precondition that only exists in prose gets skipped, while a precondition expressed as a routing
leaf that returns a refusal gets executed. The `通常被注释` detail is what makes it actionable: the
print exists in the codebase and is disabled by default, so the work is uncommenting, not writing.

## 3 · Ground / Source
The refusal leaf, `mc2/fallback/fallback-algorithm.md:25-30`:

```
给定：M, N, baseM, baseN, N_core(usedCoreNum)

Step 0 — 前置检查：
  ├─ baseM/baseN/N_core 缺失 → 返回「需先打印 TilingData」
  └─ 齐备 → 进入 Step 1
```

The capture instructions, `mc2/index.md:34-43`, in full:

```
## TilingData 打印（前置必需）

MC² 流水配平的搜索算法依赖 baseM/baseN/usedCoreNum 等 matmul tiling 参数。host 代码须打印这些参数：

- 检查 host tiling 代码中 `PrintTilingData` 调用（通常被注释，如 `// PrintTilingData(tilingData);`）
- 取消注释或在 tiling 计算完成后添加 printf 打印：`baseM`、`baseN`、`baseK`、`usedCoreNum`、`stepK` 等
- 参考 `quant_matmul_tiling_base.h` 的 `PrintTilingData` 实现
- **长块和短块各有独立 tiling data**，须分别打印

详见 [comm-compute/pipeline_balancing.md](../../comm-compute/pipeline_balancing.md) 的「TilingData 依赖」章节。
```

Restated a third time as a flow prerequisite, `mc2/fallback/tiling-flow.md:5`:

```
> **前置依赖**：baseM、baseN、usedCoreNum 须从 host 侧 TilingData 打印获取（见 [pipeline_balancing.md](../../../comm-compute/pipeline_balancing.md) 的「TilingData 依赖」章节）。
```

Three statements, one repo, one origin — this does not corroborate, it repeats. What the repetition
does establish is that upstream treats the precondition as load-bearing enough to state in the
index, the algorithm's Step 0, and the flow's header.

Note what the refusal does *not* cover. `baseK` and `stepK` are in the print list at `mc2/index.md:39`
but not in Step 0's missing-input test, which checks only `baseM/baseN/N_core`. So a capture that
omits `baseK` passes the gate while leaving the long block's matmul tiling underdetermined. Minor
and recorded rather than adjudicated.

The detailed capture protocol for MC² measurement — how many iterations, warm-up, and the
max-across-ranks rule — lives in `comm-compute/`, outside this domain; this entry deliberately does
not restate it, and §4 below uses it without claiming it.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. MC² is
multi-rank: at most 4 dies under the shared-machine budget.

Device selection: `npu-smi info -l`; for each candidate chip `npu-smi info -t usages -i <id> -c
<chip>` three times at 20 s spacing; bind only chips idle in all three; record the chip ids;
re-sample all after the run and discard the case if any moved. Never exceed 4 dies; the rank count
is recorded with the result.

Inference-versus-print comparison, which is the only way to test whether the precondition is real.
Choose five MC² cases spanning the shape regimes that make `usedCoreNum` diverge from `aicNum`:
one with no tail (`M % (baseM × mCnt) == 0`), one with a large tail, one with `M` small enough that
`totalBlockCnt ≤ 1`, one with N small (so `nBlockCnt < N_core`), one prime `M`. For each: (a)
uncomment `PrintTilingData` in the host tiling code, run the host tiling only — no kernel launch
is needed for this arm — and record the printed `baseM`, `baseN`, `baseK`, `usedCoreNum`, `stepK`
for the long block and the short block separately; (b) independently, derive the same five values
by inference from shape and the matmul family's rules, recorded *before* opening the print output
so the prediction is on record; (c) compare field by field. Then derive the comm-split parameters
from both sets and, where they differ, build and time both plans (one compiler pin, md5 per
binary, fp64 reference check within the declared tolerance, per-rank capture of ≥10 iterations
with the first 5 as warm-up, mean of the last 5, maximum across ranks).

Refuses to assume: that a die free before the run stayed free; that a die may be substituted; that
`usedCoreNum` equals the platform's core count — that equality is exactly what arm (b) predicts
and arm (a) tests; that the host tiling engine in reach is the one that produced upstream's
examples (its version is recorded and the claim is scoped to it); that the inference arm may be
written after seeing the print.

## 5 · Checker — acceptance declared before the run
Verdict variable `infer_matches`, a per-case, per-field boolean over the five fields and both
blocks. Declared before the run: the precondition is supported iff `infer_matches` is false for at
least one field in at least one case — that is, inference demonstrably fails somewhere. The
OVERTURN fires iff `infer_matches` is true for every field of every case: the print is then
reproducible by inference across this shape set and the refusal is a convenience rather than a
gate. A second verdict `plan_gap` records the timing difference wherever the two derivations
produced different comm-split parameters, so the *cost* of the wrong inference is a number, not an
argument.

The exit code is not the verdict. The blind mode this checker must avoid is the one that makes
precondition claims easy to "confirm": running only cases where inference obviously fails. The
guard is the case-selection rule stated in §4 — the five regimes are fixed in advance and include
the easy no-tail case where inference should succeed — and the checker goes red if fewer than five
cases produced a complete field table, rather than reporting the cases that worked. It also
requires the inference arm's predictions to be timestamped before the print arm's output is read;
a missing or late prediction file fails the check.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no host tiling was run and no print was captured. The entry does not
establish that `usedCoreNum` differs from the core count on any real case, only that upstream's
own formula allows it to. It does not establish that `PrintTilingData` exists or is commented out
in any particular codebase — upstream describes a convention, and this book has not inspected the
code it describes. It does not cover the MC² measurement protocol (iterations, warm-up,
max-across-ranks), which lives in `comm-compute/` outside this domain and is used by §4 without
being claimed here. It does not address Step 0's omission of `baseK` from the missing-input test.
No board is named anywhere in the MC² directory, so BOARD is `family-claimed(unverified)` and the
chip is unstated; §4 names 950PR/950DT because that is where our run would happen. Nothing here is
established for any 910-family board.

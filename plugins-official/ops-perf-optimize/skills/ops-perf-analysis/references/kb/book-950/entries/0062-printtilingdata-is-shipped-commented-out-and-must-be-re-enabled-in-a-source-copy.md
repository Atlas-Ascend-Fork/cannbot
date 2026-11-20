```
ID:        0062-printtilingdata-is-shipped-commented-out-and-must-be-re-enabled-in-a-source-copy
LABEL:     procedure
LEVEL:     L0 (launch & host)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:253 — "host 代码的 tiling 引擎通常包含 `PrintTilingData` 方法但被注释掉。参考 `quant_matmul_tiling_base.h` 中的实现"
           ops/ascendc-perf-optimize/references/comm-compute/pipeline_balancing.md:272 — "长块和短块各有独立的 matmul tiling data（不同 M 大小 → 不同 baseM/baseN）。须分别打印长块和短块的 tiling data，用于各自的核利用率评估"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a host tiling engine on a named 950 board whose printed `baseM`/`baseN`/`usedCoreNum`
           differ from the values the kernel actually receives — the print would then not be a
           readout of the tiling in force, and every core-utilisation computation built on it would be
           computing from the wrong numbers.
```

# 0062 · PrintTilingData is shipped commented out and must be re-enabled in a source copy

## 1 · Claim
Upstream asserts that the parameters the balancing search needs — `baseM`, `baseN`, `usedCoreNum`,
`baseK` — are produced by the host-side tiling engine and must be obtained from its printed output;
that host tiling engines usually contain a `PrintTilingData` method that is commented out, which must
be re-enabled (in a source copy) and the operator re-run; and that long blocks and short blocks each
have their own complete matmul tiling data, so both must be printed separately for their respective
core-utilisation assessments. Not established here; nothing was built or run.

## 2 · The wrong branch this removes
`baseM` and `baseN` are internal tiling decisions, not operator inputs, so an agent that needs them
will do one of three things: guess them from the shape, take them from a document, or compute them
from a model of the tiling engine. All three produce a number that looks like `baseM` and is not the
one in force, and the error propagates silently into `mBlockCnt = ceil(longMSize / baseM)` and from
there into the core-utilisation pruning (0068) — which will then exclude the right candidates and
admit the wrong ones. The failure has no symptom: the search runs, produces fifteen candidates, and
they are the wrong fifteen.

The second wrong branch is printing once. Long and short blocks have different M, so the tiling
engine derives different `baseM`/`baseN` for each; a single print taken from the uniform-split
baseline describes neither of the two blocks in a non-uniform split.

## 3 · Ground / Source
`pipeline_balancing.md:238-272`, the TilingData 依赖 section. The requirement, `:240`: 搜索算法依赖
baseM、baseN、usedCoreNum 等 matmul tiling 参数来计算核利用率和搜索范围。这些参数由 host 侧 tiling
引擎生成，**必须从 host 代码打印输出中获取**. The four-row parameter table, `:244-249`, states each
parameter's use: `baseM` for `mBlockCnt = ceil(longMSize / baseM)`, `baseN` for
`nBlockCnt = ceil(N / baseN)`, `usedCoreNum` to confirm the actual available core count N_core,
`baseK` to assess L1 splitting.

The method, `:251-268`, with the code:
> // 在 tiling 引擎的 GetTilingData 方法中，取消注释 PrintTilingData 调用：
> void GetTilingData(...) { ... DoOpTiling(tilingData); PrintTilingData(tilingData); }
> void PrintTilingData(const QuantMatmulTilingData& tilingData) const {
>     printf("[TilingData] usedCoreNum=%u, m=%u, n=%u, k=%u, baseM=%u, baseN=%u, baseK=%u, stepK=%u, ...\n", …);
> }

and the warning at `:270` that without the print the search must not proceed (0061), plus the
long/short requirement quoted in SOURCE.

Consistent statements elsewhere: `comm-compute/index.md:114-117` makes TilingData collection Step 0
of the analysis flow and routes to this section; `index.md:155` assigns it to the data-collection
phase; `index.md:166` requires per-case recording of the parameters 含长块/短块各自的 tiling data;
`SKILL.md:75` lists it as a required Step 2 output. The copy discipline is MC-C3's (0059), stated
there for the isolation test and applying here by the same reasoning — this edit also changes the
user's source.

`pipeline_balancing.md:22` states the underlying fact that makes two prints necessary: 长块和短块
使用**各自独立的完整 matmul tiling data**（baseM/baseN/baseK/L1 参数等均不同）.

## 4 · Procedure
Later phase, needs a card to re-run the operator; the source edit needs none.
1. Copy the operator's host source to a scratch directory; record `sha256sum` before and after, and
   keep the diff. The user's tree is not edited (MC-C3).
2. Re-enable the `PrintTilingData` call in the copy — or add one if the engine has none — and rebuild.
3. Run at `tileCnt=1` and capture the printed line; then run with a non-uniform split configured and
   capture both the long-block and short-block prints.
4. Independently corroborate the printed values from the kernel side: read the same fields from the
   TilingData structure inside the kernel (or dump the tiling buffer) and compare. This step is not
   in upstream's procedure and is what turns a print into a readout.
5. Device selection per 0057 for the runs; board token per rank from the driver readout.

## 5 · Checker — acceptance declared before the run
Verdict variables `printed = {baseM, baseN, baseK, usedCoreNum}` per block, and
`kernel_side = the same fields read inside the kernel`. Acceptance: `printed == kernel_side` field by
field, for both the long and short block; and `printed(long) != printed(short)` in at least one
field for a non-uniform split, which is upstream's stated expectation.

Exit code is not the verdict. The captured stdout is preserved verbatim in the run record, since a
`printf` from host code can be interleaved or truncated under multi-rank forking — a missing line is
reported as `print_not_captured`, never as a zero.

Red input: a deliberately wrong `baseM` written into the print statement. The kernel-side comparison
must catch it. Without that arm, the check would confirm only that a number was printed.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; nothing built. It does not establish that any particular tiling engine has a
`PrintTilingData` method — upstream says 通常 and names one header as an example, and this book has
not read that header. It does not establish that the printed values are the values in force; that is
what step 4 exists to test and it has not been run. It says nothing about operators whose tiling is
computed on device, or about tiling engines that do not expose these fields. No board is implicated.

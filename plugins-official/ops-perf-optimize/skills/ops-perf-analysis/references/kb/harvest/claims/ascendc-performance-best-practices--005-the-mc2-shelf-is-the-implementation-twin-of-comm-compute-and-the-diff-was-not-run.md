# CARD · ascendc-performance-best-practices 005 — the MC² shelf is the implementation twin of comm-compute, and the diff was not run

**BOOK: 950 — candidate, deliberately deferred by the 950-bp a later harvest pass harvester. This card records
what was NOT done, so a later pass starts from the boundary rather than from the beginning.**

## What the twin relationship is
`ascendc-perf-optimize/references/comm-compute/` is the analysis layer and is already carried by
book-950 entries `950:0055`–`950:0075` (masking ratio, the tileCnt=1 baseline, the R-value bands, the MTE2
pollution test, pruning rule P4's defect, the 80 %/50 % core-utilisation cuts, Top-N = 15, Local
Matmul as bound-independent first choice, the MC2_JitterDiagnose orphan).

`ascendc-performance-best-practices/reference/mc2/` is the implementation layer: `guide.md`,
`local_matmul_design.md` (130 lines), `pipeline_balancing_design.md` (502 lines). The deep-dive
already recorded byte-identical blocks between the two shelves
(`comm-compute/local_matmul.md:62` ↔ `bp/mc2/local_matmul_design.md:117`;
`comm-compute/pipeline_balancing.md:37-38` ↔ `bp/mc2/pipeline_balancing_design.md:40-41`), which is
the same dual-maintenance pattern the scatter family declares explicitly
(`同源，改动请同步两处`).

## What was re-verified, 2026-08-24
`reference/mc2/guide.md:9-13`, the strategy table, which is genuinely a *routing* statement the
analysis shelf does not carry in this form:

> | **local_matmul** | 首选 | 所有 MC² 通算融合算子 | 将本 rank 数据的 matmul 从通信块循环中分离，
> 前置/后置独立执行以与通信重叠 |
> | **pipeline_balancing** | 中 | 所有 MC² 通算融合算子（在 Local Matmul 基础上叠加） | 按 Bound
> 类型确定长短块排布，**TilingData 驱动的系统搜索**（四条剪枝 + Top-N 候选实测）选最优切分 |
> | **matmul 计算效率优化** | 最低 | 仅计算 Bound（正交可叠加） | 参考 matmul 族优化策略
> （pingpong/streamk/fullload 等），提升单块 matmul 效率 |

and `:15`:

> Local Matmul 不依赖 Bound 判定，推荐优先实现。... **须先打印 TilingData (baseM/baseN/usedCoreNum)
> 并执行隔离测试获取 R 值**，再通过系统搜索算法（非经验值）确定最优 longMSize。

Both halves are already in book-950 — the bound-independence of Local Matmul as `950:0071`, the hard
data gate as `950:0061` and `950:0062`. So the guide adds a **priority ordering** (首选 / 中 / 最低)
and a **composition claim** (all three stack, the third only when compute-bound) that the analysis
shelf states less directly, and adds an explicit hand-off to the matmul family this block's
`950:0301`–`950:0313` now cover.

## Why it was deferred rather than mined
Three reasons, in order of weight.

1. **The anti-duplication rule bites hardest here.** Of the twin's material, `950:0055`–`950:0075` already
   carry twenty-one entries. A useful mining pass is a *diff*, not a read — and a diff of a 502-line
   design document against six already-entered analysis documents is the most expensive comparison
   in this brief's scope, not the cheapest.
2. **The scatter diff (the brief's named example) consumed the budget for one such comparison**, and
   it produced seven entries (`950:0322`–`950:0328`) plus three contradiction rows. That was the right place
   to spend it: the scatter twin is where upstream declares the dual-maintenance obligation in
   writing, so a divergence there is a defect by upstream's own standard.
3. **The 0351–0399 block is owned by another a later harvest pass agent** whose brief covers "regbase/simt/mc2
   remainder". Mining mc2 into 0301–0349 risked a collision that the anti-duplication rule cannot
   catch, because that agent's entries did not exist when this block was allocated.

## What a later pass should diff first
- `pipeline_balancing_design.md`'s search against `comm-compute/pipeline_balancing.md`'s, at the four
  pruning rules. `950:0066` records that P4 as written in the analysis shelf removes every
  non-uniform split. **Does the implementation shelf's P4 have the same defect?** If it does not,
  that is a divergence with a working version on one side, which is the most valuable thing a twin
  diff can find.
- The three different answers for `M_short` the deep-dive found in the analysis shelf
  (`:150`, `:175`, `:185`) — does the implementation shelf give one?
- `local_matmul_design.md:117`'s byte-identical block: confirm it is still identical, since the
  dual-maintenance obligation is unenforced.

## Evidence class
recipe-with-priority-ordering. No measurement in the guide; `pipeline_balancing_design.md` not read
past its first screen.

## OVERTURN sketch (for the deferral, not for a claim)
A reading of `pipeline_balancing_design.md` that finds a measured figure, or a corrected P4, absent
from the analysis shelf. Either would mean the deferral cost the books a real entry.

## Disposition
Deferred with a named starting point. Recorded in `harvest/standing/950-bp.md` Q-950bp-14. Not
entered in book-950.

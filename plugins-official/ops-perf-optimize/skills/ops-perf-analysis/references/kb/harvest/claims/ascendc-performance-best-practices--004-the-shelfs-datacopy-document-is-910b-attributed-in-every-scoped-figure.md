# CARD · ascendc-performance-best-practices 004 — the shelf's DataCopy document is 910B-attributed in every scoped figure

**BOOK: 910 (if any) — deliberately NOT mined into book-950 by the 950-bp a later harvest pass harvester.**

## Why this card exists
The a later harvest pass brief named `reference/common/` (datacopy, double-buffer etc.) as a target with an
explicit filter: **"950-marked rows only"**. This card records the result of applying that filter to
`datacopy_optimization_design.md`: there are none.

## The scoped figures, re-verified 2026-08-24
Every quantified statement in the file names Ascend 910B, and most of them say so twice:

`reference/common/datacopy_optimization_design.md:7`:
> - **非对齐访问惩罚**：数据未按设备最优粒度对齐时，DMA 效率大幅下降。以 Ascend 910B 实测为例，
> 32B 对齐的带宽约为 512B 对齐的 70%，不同设备的最优对齐值需实测确认。

`:17`:
> | 对齐访问带宽 | 未按最优粒度对齐: ~70% | 按设备最优粒度对齐 | 带宽提升最高 30%（Ascend 910B 实测）|

`:45`:
> 以下阈值基于 Ascend 910B 实测经验，不同设备的 DMA 控制器、总线宽度和缓存行大小不同，具体数值需
> 参考对应硬件手册或实测确认。

`:209-215` (the bandwidth ladder, in a code comment):
> // 以下数据为 Ascend 910B 实测结果，不同设备的最优对齐粒度可能不同。
> uint32_t offset = AlignUp(rawOffset, 512);  // 910B 上 512B 为最优粒度
> // 实测带宽对比（GM→UB，Ascend 910B）：按最优粒度（512B）对齐: ~100% / 256B 对齐: ~90% /
> // 32B 对齐:  ~70%（最差情况）

`:245` and `:349` repeat the 512 B optimum and the 256 B transfer floor with the same attribution.

A `grep -n "950\|3510\|arch35\|A5\|Atlas 350"` over the file returns **nothing**.

## Why this is a card and not an entry
Under RULES.md Art. 1 these figures are not book-950's. The file sits under 公共优化能力, which carries no
適用架構 marking at all, and its §1 says its target family is `conversion` — which the shelf index
*does* mark `DAV_3510`. So the routing is genuinely ambiguous at the family level and completely
unambiguous at the sentence level: the sentences name 910B.

The unscoped API facts in the file (`DataCopyExtParams`, `DataCopyPadExtParams`, `Nd2NzParams`, the
`rightPadding ≤ 255` uint8 limit, the `stride ≤ 65535` uint16 limit, the ND→NZ `dstNzC0Stride`
alignment of 16 elements for fp16 and 32 for fp8) are architecture-silent API shape facts, and
book-910 already carries that neighbourhood (`910:0021`–`910:0027`, `910:0068`, `910:0069`). Entering
them again in book-950 would be establishing the same claim twice from one origin, which STRATA's
hard rules permit only when the source names both families. This one names neither, and its measured
neighbours name 910B.

## The one row a later 950 pass should look at first
`:98` and `:133` give the ND→NZ C0 alignment as **fp16 → 16 elements, fp8 → 32 elements**. FP8 is a
dtype whose cube support this book records as generation-dependent (`950:0220` on low-precision cube
dtypes widening the MAC array; `910:0074` records fp8 excluded from the A2 atomic set). So the fp8
row is the closest thing in this file to 950-relevant content, and it is an alignment constant with
no attribution, not a measurement.

## Evidence class
measured-with-attribution, to the wrong family for this book. The 70 % / 90 % / 100 % ladder is the
best-attributed bandwidth figure in the whole shelf — it names the part, the direction (GM→UB) and
the comparison — and it names 910B.

## OVERTURN sketch (if a later agent disputes the skip)
The discovery, in this file, of a figure attributed to a 950-family part, or of a statement that its
thresholds are architecture-independent. Either would make the skip wrong and the file partly
book-950's.

## Disposition
Skipped, with reason. Recorded in `harvest/standing/950-bp.md` Q-950bp-14. Not entered in book-950.

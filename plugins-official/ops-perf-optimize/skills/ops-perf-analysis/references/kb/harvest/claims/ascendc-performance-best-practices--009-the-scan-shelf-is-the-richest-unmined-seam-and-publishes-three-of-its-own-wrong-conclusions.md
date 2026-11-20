# CARD · ascendc-performance-best-practices 009 — the scan shelf is the richest unmined seam, and publishes three of its own wrong conclusions

**BOOK: 950 — candidates, deliberately deferred by the a later harvest pass `950-td` harvester after drafting one
entry from this family (`950:0418`). This card records the boundary so a later pass starts from it
rather than re-reading eight files.**

All paths relative to `ops/ascendc-performance-best-practices/reference/scan/`. Every quote below was
produced by a full read of all eight files; a later pass **must** re-verify each against the file
before building on it (this domain logged two transcription failures, `SR-950td-01` and `-03`).

## Why this is the seam, not just a backlog item

The analysis shelf's scan family is already carried at `950:0132`–`0139`, and those entries record it
as bare: no chip anywhere, every measured number unscoped. **This shelf is the opposite** — it carries
a twelve-step measured optimisation trajectory with per-step scores, six-case ping-pong tables, a
net-negative optimisation costed on both sides, and three self-reported wrong conclusions. It is the
best evidence culture in the scan material and almost none of it is in the book.

## The five highest-value unmined items, in priority order

**1. A net-negative optimisation with both sides costed.** `templates/cum_tile_resident_scan.md:51-59`
— for cases 5 and 10 the plugin-side cost is 5269 µs / 877 µs against a kernel-side saving of ~900 µs /
~165 µs, giving `总体退化 2.7x / 3.0x`, with the conclusion `⚠️ case 5/10 的 MTE3 占比 74~80% 已是写带宽
天花板，不要再尝试通过减少写量来优化` and a redirect (`进一步优化应转向 R 轴切核`). A disclosed
net-negative with both arms quantified is rare in this repository; `950:0328`'s falsification list is
the only comparable instance and it carries no costs.

**2. One case, three published results.** `[1000003]` two-launch borrow-R, common baseline 2002 µs:
`guide.md:214` says `降到 34 µs`, `templates/cum_core_partition_scan.md:49` says `56 µs`,
`templates/usage_guide.md:177` says `59 µs（0.01x → 0.22x）`. Three files, one shelf, one optimisation.
Related divergences: two-row interleave `8%~18%` (`cum_lane_parallel_scan.md:131`, `guide.md:271`) vs
`约 3%` (`usage_guide.md:126`); ping-pong gain `12~31%` (`cum_row_kogge_stone.md:112`) vs `4%~31%`
(`guide.md:148`), where the second matches no table in the shelf and the first is identical to rows 1–4
of a table in a *different* file.

**3. The bank-conflict predicate is two incompatible rules, and the remedy has a disclosed
counter-example.** `950:0133` carries the 16-byte-multiple form from the analysis shelf. This shelf
states it **both** ways: power-of-two at `guide.md:187`, `:270` and
`templates/cum_lane_parallel_scan.md:82-83`; 16-byte-multiple at `usage_guide.md:121-122` and, in code,
`cum_lane_parallel_scan.md:94` (`return (s * cBytes % 16 == 0) ? (s | 1) : s;`). The single measurement
— `R=4096` bf16, `S=32`, `160 µs → 887 µs` (`cum_lane_parallel_scan.md:83-84`) — has a 64-byte stride
and therefore satisfies **both** predicates, adjudicating neither. And the remedy has a stated
counter-example the book does not carry: `cum_lane_parallel_scan.md:87-88` — `R=511 时错位反而慢 15%`,
because the padding region grows from `R` to `VLC·S`. Cite the 16 B form only to the three sites that
state it.

**4. The streaming template's own document contradicts the family on NaN — and is the one the entry
macro instantiates.** `950:0139` carries "NaN must be made sticky by hand" from the analysis shelf.
`templates/cum_streaming_scan.md:31` asserts the opposite — `Compare 对 NaN 返回 false → NaN 被取用并向
后传播，对齐 torch` — and specifies `GT` only (`:29`, `:30`, `:38`, `:43`), no `NE`, no `Or`.
`usage_guide.md:236-239` records that exact configuration failing: `只用 GT 时 20 用例中 case 14 精度
失败`. Tie semantics diverge too (`GT` vs `LE`). And `usage_guide.md:204`, inside `#define
CUMMIN_ENTRY`, instantiates `ScanOps::CumStreamingScan<TX, TP>` four times — the template four files
mark `仅作参考实现，勿用于性能路径`. `950:0136` records the analysis shelf's script doing the same
thing; this is the second, independent-in-artifact instance in the same repository.

**5. Six disclosed template-extraction defects, two marked 致命.** `usage_guide.md:273-310`, prefaced
`以下问题来源于将单文件参考实现提取为 .template 体系时发现的提取遗漏` — a shelf publishing the defects
its own packaging introduced. Includes a silent-nondeterminism item (`不报错，只出非确定性精度错误`,
`:281-282`) and a duplicated class line the reader must delete before use (`:309-310`).

## Also unmined, lower priority but real

- **`gsS` is a runtime gate on a symbol defined nowhere** (`usage_guide.md:26`, `:288`;
  `cum_row_kogge_stone.md:109-110`). `950:0138` carries `VLC`/`VREG`; this is a third, and it selects
  between two algorithms at runtime. Also `GUARD` (`usage_guide.md:263`) vs `VLC`
  (`cum_row_kogge_stone.md:41`) for one failure predicate.
- **The template roster is three non-coextensive enumerations**: six device templates with `.md` docs;
  eight Cumsum tiling keys `1001/1002/1011/1012/1101/1102/1111/1112`; `6 种 mode` claimed
  (`usage_guide.md:299`) with only five ever named — **`mode 2` appears nowhere**. `twoway` is named
  throughout and has neither `.md` nor `.template`.
- **Three unreconciled architecture markers in one shelf**: `dav310/` (paths), `arch35`
  (`usage_guide.md:198`), `--npu-arch=dav-3510` (`:217`). Feeds `950:0346` and `950:0421`.
- **Dangling references**: `usage_guide.md:60` cites a `§1.2` that does not exist; `:299` cites
  `scan_cummin_tiling.h`, absent from its own roster table and from the directory;
  `cum_tile_resident_scan.md:121-122` cites an `N > 1` generalisation in `cum_core_partition_scan.md`
  that has no such section.
- **A metric that misleads, disclosed**: `cum_tile_resident_scan.md:34-35` — GB/s and L2 hit rate
  mislead here because small footprints reach `2.1~2.7 TB/s` out of L2; use the four-pipe occupancy sum
  instead (`≈100%` serial, `>130%` real overlap). Same species as `950:0127`.

## Evidence class
Measured-with-case-identity throughout, and **board-free throughout**: the only hardware name in the
shelf is `72 核的 A5` (`cum_core_partition_scan.md:77`), describing another operator's core-truncation
defect rather than any measurement's platform. No repetition count, no variance, no error bars
anywhere. Tools named: `cann-bench`, `PipeUtilization`, `ResourceConflictRatio`.

## OVERTURN sketch (for the deferral)
Any of items 1–4 turning out to be already carried by `950:0132`–`0139` under a different formulation.
Checked at card time against those nine entries' §1 and §7: items 1, 2, 4 and 5 are absent from all
nine; item 3's remedy is carried but its second predicate and its counter-example are not.

## Disposition
Deferred with named starting points after one entry (`950:0418`, the ~30 µs dispatch floor and the
wrong conclusion it caused). Recorded in `harvest/standing/950-td.md` under deliberate skips. Priority
for a later pass: net-negative (1) → three-values-one-case (2) → bank predicate + counter-example (3) →
streaming NaN contradiction (4) → extraction defects (5).

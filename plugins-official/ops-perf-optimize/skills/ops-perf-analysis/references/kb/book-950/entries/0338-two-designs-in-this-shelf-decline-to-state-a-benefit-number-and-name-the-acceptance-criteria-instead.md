```
ID:        0338-two-designs-in-this-shelf-decline-to-state-a-benefit-number-and-name-the-acceptance-criteria-instead
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/tilingdata_cv_ssbuf_forwarding_design.md:95
           — "效果：减少 cube 侧 full TilingData 拷贝和启动 Scalar 指令。该案例未提供具体量化数据，
           因此不编造收益数字；落地时以启动 timeline、cube 侧头开销和主/control shape 精度作为验收。"
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/getvalue_cacheline_batching_design.md:91
           — "效果：减少连续 sparse index 读取与其他 Scalar GM 访问的交错，提高 DataCache line
           利用率。该案例未提供具体量化数据，因此不编造收益数字；落地时以 main/control shape、精度、
           Scalar/SCALARLDST counters 作为验收。"
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/guide.md:35-36 —
           "| `tilingdata_cv_ssbuf_forwarding` | 减少 A5 mixed AIC/AIV kernel 中 cube 侧 full
           TilingData 拷贝和启动 Scalar 指令 | | `getvalue_cacheline_batching` | 改善 sparse index /
           GM metadata 连续 `GetValue` 的 DataCache line 利用率 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  the discovery of a quantified benefit figure for either technique anywhere in the
           upstream repository — the refusal would then be a local omission rather than a stated
           policy, and this entry would be recording an accident.
```

# 0338 · Two designs in this shelf decline to state a benefit number, and name the acceptance criteria instead

## 1 · Claim
Upstream asserts, in two FlashAttention design documents, that the case behind each carried no
quantified data and that it will therefore not invent a benefit figure —
`该案例未提供具体量化数据，因此不编造收益数字`. Upstream asserts, in the same sentence in both files,
what a reader should use in place of the missing number: for the CV-SSBUF forwarding technique
(`0337`), the launch timeline, the cube-side header overhead, and accuracy on the main and control
shapes; for the GetValue cache-line batching technique, the main and control shapes, accuracy, and
the Scalar / SCALARLDST counters. Upstream asserts the same restraint one level up, in the family
index's "已验证效果" column, where the other three strategies carry percentages and these two carry
qualitative descriptions of what changed. Not established here — this entry records a documentation
practice, and nothing was measured.

## 2 · The wrong branch this removes
The wrong branch is not an implementation choice; it is what a consuming agent does with a document
that has a "benefit" heading and no benefit.

The default is to fill it. The shelf's own document template mandates
`优化目标 —— 效果与量化收益（kernel μs / MTE2 段 / CUBE busy 等）` as a required section
(`SKILL.md`, structure A, item 1), so every design document arrives with a slot for a number. An
agent extending this library, or a skill regenerating it, meets that slot and produces something —
an estimate, a range, a figure carried over from a similar technique. The result is a number with no
case behind it, indistinguishable in form from `0335`'s eight-case table, and it propagates.

This shelf contains the failure mode in the same building. `950:0002`'s neighbourhood records seven
`性能数据` sections in the sibling skill that carry a recipe under a heading promising data; the
`common/` documents in this shelf carry `UB 占用降低 30-60%` and `计算速度提升数倍` with no case,
shape, dtype or board (`0318` §7); `0312` records a results table whose "before" cell contradicts its
own worked example. The distance between those and these two files is exactly one sentence.

The second wrong branch is treating "no number" as "no evidence" and discarding the technique.
Upstream does the opposite and it is the useful move: it replaces the missing magnitude with a
*named observable*, so the technique is still actionable and still falsifiable — a reader can tell
whether it worked, just not by how much in advance. A benefit figure and an acceptance criterion do
different jobs, and the second is the one an implementer actually needs at landing time.

The third, and the reason this entry sits at L7 rather than in the FlashAttention block: the
acceptance criteria named are *technique-appropriate*, not generic. CV-SSBUF forwarding is a launch
technique, so its criterion is the launch timeline and cube-side header cost — measuring it by
kernel time on a large shape would read as zero (`0337` §5). Cache-line batching is a DataCache
locality technique, so its criteria are the Scalar and SCALARLDST counters, not bandwidth. Choosing
the readout that can see the effect is the part most often got wrong, and both files get it right
without having a number to defend.

## 3 · Ground / Source
The two refusals, verbatim.

`tilingdata_cv_ssbuf_forwarding_design.md:95`:

```
效果：减少 cube 侧 full TilingData 拷贝和启动 Scalar 指令。该案例未提供具体量化数据，因此不编造
收益数字；落地时以启动 timeline、cube 侧头开销和主/control shape 精度作为验收。
```

`getvalue_cacheline_batching_design.md:91`:

```
效果：减少连续 sparse index 读取与其他 Scalar GM 访问的交错，提高 DataCache line 利用率。该案例
未提供具体量化数据，因此不编造收益数字；落地时以 main/control shape、精度、Scalar/SCALARLDST
counters 作为验收。
```

The second file's own technique, for context, since this entry is its only appearance in the book.
Its subject is a hot loop that reads GM metadata — top-k indices, block ids, row ids — one or two
values at a time with other scalar GM traffic interleaved between them, so a DataCache line is
fetched and only partly consumed before being displaced. The change batches the metadata read
(`:26-31`: `tokenData[0..7] = consecutive GetValue(topk[k..k+7])`, then the downstream consumption
proceeds in its original pairwise granularity) and upstream is explicit that the *consumption*
granularity is deliberately unchanged — `读取阶段批量化，下游 KV copy 仍保持原来的 2 token 一组
逻辑，减少行为变化范围`. The batch size is 8, marked `8 是已验证案例值，迁移时需按 dtype / 寄存器
压力复测` (`:39`), and the tail is preserved by pre-filling `tokenData` with `-1` so the original
early-exit still fires (`:43`, `:73-78`). Its four disqualifiers include the two that matter —
randomly scattered indices, and a batch large enough to read data that is never used (`:87-88`).

So the technique has: a mechanism, a batch size with a stated scope caveat, a preserved-behaviour
argument, four named non-applicable conditions, and no number. That combination is what upstream is
declining to decorate.

The family index's effect column, `guide.md:30-36`, where the contrast is visible in one table:

```
| 策略 | 已验证效果 |
| `scalar_general_techniques` | 8 组 case Scalar 耗时平均下降 33.22%，端到端耗时平均提升 14.74%，
  SCALAR_BOUND 跳出 |
| `scalar_precompute` | 稳健减少 decode 热循环地址计算、除法和公共前缀重复计算；预期 SCALAR 下降 12% - 30% |
| `scalarldst_subbound` | 最长核 case cycle 从 18353 降至 18076，约 -1.51% |
| `tilingdata_cv_ssbuf_forwarding` | 减少 A5 mixed AIC/AIV kernel 中 cube 侧 full TilingData 拷贝和
  启动 Scalar 指令 |
| `getvalue_cacheline_batching` | 改善 sparse index / GM metadata 连续 `GetValue` 的 DataCache line
  利用率 |
```

Five rows, three registers. Row 1 is measured with a case count (`0335`). Row 3 is measured on one
unidentified case (`0336`). Row 2 is the interesting middle: `预期 SCALAR 下降 12% - 30%` — a range
explicitly marked as an *expectation*, in a column headed `已验证效果` (verified effect). Rows 4 and
5 are qualitative. So within one table upstream uses a measured figure, an expectation labelled as
one, and a refusal — and only the second is mis-placed, since an expectation under a
"verified effect" heading is the thing the other two rows avoid in opposite directions. Recorded in
`harvest/standing/950-bp.md`.

Note what the refusal is **not**. It is not "we did not measure"; it is `该案例未提供具体量化数据`
— the source case did not carry the data. Upstream is declining to fabricate a figure it never had,
which is a statement about provenance rather than about effort, and that is the honest form.

Nothing in this section is measured by this book.

## 4 · Procedure
This entry's claim is about two sentences in two files, and the honest procedure is a sweep, not a
run. Declaring a device procedure for a documentation practice would be the ceremony this book's own
form warns against.

Arm 1 — `[no-card]`, **run**: locate every `## 1. 优化目标` / `已验证效果` / `效果` slot across the
shelf's design documents and classify each as `measured-with-case`, `measured-unscoped`,
`expectation-labelled`, `qualitative-refusal`, or `recipe-under-a-data-heading`. The two refusals and
the one mis-labelled expectation in §3 are three points of that classification, found by hand.

Arm 2 — `[no-card]`, **not run**: complete the sweep across all thirteen families and publish the
counts. The value is comparative — the shelf's own distribution of evidence registers is what tells a
consuming skill how much of the library can be stated in measured voice, and it is directly what
`the delivered skill`'s pedigree rule needs. Owed in `harvest/standing/950-bp.md`.

Arm 3 — the only part that would need a card, and it belongs to `0337` and to a future entry for the
batching technique, not here: measuring the two techniques against the acceptance criteria upstream
named. This entry does not claim they work; it claims upstream declined to say by how much.

Refuses to assume: that a heading's presence implies data beneath it (the classification is by
content, not by heading); that a range is a measurement (row 2 is classified by its own label,
`预期`); that a qualitative statement is weaker than a number (row 4's `减少 cube 侧 full TilingData
拷贝和启动 Scalar 指令` is checkable by disassembly and is in that sense harder evidence than an
unscoped percentage).

## 5 · Checker — acceptance declared before the run
Verdict `register[doc]` for each design document, one of the five classes above. The deliverable is
the distribution, and there is no pass condition on it: a shelf with many qualitative rows is not
worse than one with many percentages, and the point of the classification is to stop treating the
two as interchangeable.

Verdict `refusals` = the set of documents containing the string `不编造收益数字` or an equivalent
refusal. Declared before the sweep: the entry is **supported** iff that set is non-empty and its
members carry named acceptance criteria in the same sentence. The OVERTURN fires iff a quantified
benefit for either technique is found elsewhere in the repository — the refusal would then be a
local omission and not a policy.

Verdict `mislabelled` = the set of rows carrying an expectation under a verified-effect heading.

The checker must be able to go red, and here is the input that does it. The classification is run
first against three documents whose class is not in dispute: `scalar_general_techniques_design.md`
(a per-case table, `measured-with-case`), `common/ub_resident_design.md` (`UB 占用降低 30-60%` with
no case, `measured-unscoped`), and any of the seven `性能数据` sections the sibling skill carries
with a recipe beneath them (`recipe-under-a-data-heading`, `950:0002`'s neighbourhood). The
classifier **must** place all three correctly. If it collapses `measured-unscoped` and
`measured-with-case` into one class, it cannot see the distinction this entry exists to draw, and
every verdict from it is void. A survey instrument that reports only "has a number / has no number"
is the known blind species applied to prose, and those three fixtures are what exclude it.

There is no exit code to be the verdict; the deliverable is a table.

## 6 · Evidence
NOT YET RUN as a device procedure — no readout exists, and nothing in this file is a measurement.
Arm 1 was performed as a file read under the phase-1 read-only exception, and its result is §3's
five-row comparison: two qualitative refusals with named acceptance criteria, one expectation
labelled as such under a verified-effect heading, and two measured rows. A classification of prose
is not a measurement, establishes nothing about any part, and cannot tell whether either technique
works.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry records a documentation practice in two files; it does
**not** establish that either technique is beneficial, and a consuming skill must carry both at
qualitative strength with the acceptance criteria attached — which is the whole content. It does not
establish that the practice is general to the shelf: the full sweep (Arm 2) was not run, and three
data points were found by hand. It does not establish that the two source cases genuinely lacked
data, only that upstream says so. The GetValue batching technique's batch size of 8 is marked by
upstream as a single verified case value requiring re-measurement per dtype, and nothing here
establishes it for any dtype. The `预期 SCALAR 下降 12% - 30%` range for `scalar_precompute` is
recorded as mis-placed under a "verified effect" heading and is not carried as evidence by this entry
or any other in this block. BOARD is `family-claimed(unverified)`: the family is marked DAV_3510 in
the shelf index and no file in it names a board. Nothing transfers to the other book (RULES.md Art. 1).

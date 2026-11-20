```
ID:        0482-one-optimisation-of-one-case-is-published-as-thirty-four-fifty-six-and-fifty-nine-microseconds-in-three-files
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/guide.md:214 —
           "别复用扫描代码再丢掉输出。实测 `[1000003]` 从 2002 µs 降到 34 µs。"
SOURCE:    same shelf, templates/cum_core_partition_scan.md:49 —
           "让 Phase A 只读、Phase B 重扫一遍，多花的是算力而不是带宽。实测 `R=1000003` 从 2002 µs
           降到 56 µs。" ; templates/usage_guide.md:176-177 — "让 phase A 只读、phase B 重扫一遍，
           多花的是算力而不是带宽，实测 `R=1000003` / 从 2002 µs 降到 59 µs（0.01x → 0.22x）。"
SOURCE:    same shelf, templates/cum_row_kogge_stone.md:112 — "实测快 12~31%" against
           guide.md:147 — "实测快 4%~31%" (the same ping-pong change) ;
           templates/cum_lane_parallel_scan.md:131 — "实测再快 8%~18%" and guide.md:271 —
           "再快 8%~18%" against templates/usage_guide.md:125 — "实测再快约 3%" (the same two-row
           interleave)
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a run of the same optimisation on a named 950 board reproducing any one of 34, 56 or 59 µs
           at `R=1000003` with a stated variance floor, together with a stated reason the other two
           differ — configuration, measurement point, or revision. The divergence would then be
           explained rather than unexplained, and this entry would narrow to "upstream published three
           revisions without dating them". Equally: a measured spread across three plausible
           configurations that spans 34-59 µs would show all three are right and the shelf simply
           never states what varied.
```

# 0482 · One optimisation of one case is published as 34, 56 and 59 microseconds in three files

## 1 · Claim
Upstream asserts, in three separate files of one shelf, the result of one optimisation on one
identified case. The case is the same in all three: `R = 1000003`, a one-dimensional Cummin,
`[1000003]`. The optimisation is the same in all three: making the first phase of a cross-core
R-partitioned scan read-only, so the second phase rescans instead of re-reading the output. The
baseline is the same in all three: 2002 µs. The result is stated as **34 µs**, as **56 µs**, and as
**59 µs**. Upstream asserts two further divergences of the same shape: one ping-pong change is `12~31%`
in the template that implements it and `4%~31%` in the family index, and one two-row interleave is
`8%~18%` in two files and `约 3%` in a third. Not established here; this entry records a divergence
inside one shelf.

## 2 · The wrong branch this removes
Without this entry an agent quotes whichever figure it read. 34, 56 and 59 µs are a 1.7× spread, and
each is presented identically — `实测`, measured — with no hedge, no range and no configuration. An
agent planning against 34 µs and reaching 59 µs will look for a defect in its own implementation, and
there may be none.

The deeper wrong branch is the inference an agent draws from a *precise* number. `59 µs` reads as a
measurement of a specific build; three such numbers for one change mean at least two of them describe
builds that differ in something the documents do not name. The candidates are visible in the shelf and
none is stated: `usage_guide.md:168` gives a further single-launch consolidation taking `35.7 µs → 19.2
µs`, so at least three configurations of this case exist at different times; `guide.md:214` sits in a
paragraph about the two-launch form while `usage_guide.md:177` gives its result with a score ratio
attached (`0.01x → 0.22x`), suggesting a different measurement harness. An agent cannot tell which
number belongs to which build, and the documents never date themselves.

The second wrong branch is treating this as a reason to discard the shelf's numbers. It is not. This
shelf carries the corpus's best evidence culture — case identities, a twelve-step trajectory with
scores, a costed net-negative (`0481`), a disclosed measurement floor (`0418`) — and the divergence is
visible *because* the shelf publishes enough to compare. The lesson is that a measured number without
a configuration and a date is not reproducible even by the team that took it.

## 3 · Ground / Source
Three files, one case, one baseline, three results.

`reference/scan/guide.md:214`:

```
别复用扫描代码再丢掉输出。实测 `[1000003]` 从 2002 µs 降到 34 µs。
```

`templates/cum_core_partition_scan.md:49`:

```
让 Phase A 只读、Phase B 重扫一遍，多花的是算力而不是带宽。实测 `R=1000003` 从 2002 µs 降到 56 µs。
```

`templates/usage_guide.md:176-177`:

```
让 phase A 只读、phase B 重扫一遍，多花的是算力而不是带宽，实测 `R=1000003`
从 2002 µs 降到 59 µs（0.01x → 0.22x）。
```

The second and third are near-identical sentences differing in one number. That is what makes this a
divergence rather than three measurements of three things: the prose was copied and the number was
not. Registered as `C-950fin-031`.

Two related divergences, both of the same shape.

**The ping-pong gain.** `templates/cum_row_kogge_stone.md:112` — `不做双缓冲时四条流水占比之和只有
~101%（完全串行），加上后升到 132%~173%，实测快 12~31%`. `guide.md:147` — the same sentence, same
occupancy figures, `实测快 4%~31%`. The occupancies agree exactly (101%, 132-173%) and the gain does
not. And the shelf's own six-case table (`cum_tile_resident_scan.md:38-45`, repeated at
`usage_guide.md:135-142`) gives the six changes as −25%, −31%, −31%, −12%, −2%, −0.3%. So `12~31%` is
exactly the range of the **top four** rows and `4%~31%` matches **no** subset of that table: there is
no 4% row. Recorded as `C-950fin-023`.

**The two-row interleave.** `templates/cum_lane_parallel_scan.md:131` — `实测再快 8%~18%（R 越小、
行数越多收益越大）`. `guide.md:271` — `再快 8%~18%`. `templates/usage_guide.md:125` — `实测再快约 3%`.
Two files agree, one differs by a factor of three to six, and the one that differs is the integration
guide a consumer reads first. Recorded as `C-950fin-024`.

What none of the three divergences has is a variance figure. The shelf states no repetition count and
no spread anywhere, and its own measurement-floor note (`usage_guide.md:189-194`, carried at `0418`)
establishes that the local timing method has a ~30 µs floor — which is comparable to the entire
34-59 µs spread. So a 34-versus-59 difference could be measurement floor rather than build
difference, and the shelf contains the sentence that would say so without connecting it. That
connection is this entry's sharpest observation and it is a reading, not a finding: the floor note
describes the *local torch dispatch* path and the cross-core numbers may have come from cann-bench's
device-side timing, which the same note recommends. Upstream does not say which was used for which
number. Recorded as `Q-950fin-28`.

One repository, one origin (RULES.md Art. 3) — which is why this is a contradiction register entry rather
than a corroboration.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 0 — the floor, before any comparison.** Establish the variance floor for both timing methods on
this board: the local dispatch path and device-side timing, at `n = 64` and at `n = 1000003`, per
`0418`. Until the floor is known, no figure in this entry's range is distinguishable from another.
This arm runs first and its result gates the rest.

**Arm 1 — the case, in the three plausible configurations.** `[1000003]` bf16 Cummin, built as: (a)
two launches with phase A writing local prefixes; (b) two launches with phase A read-only; (c) single
launch with `SyncAll`. Report the median of ≥20 runs of each with IQR, under both timing methods.
Upstream's 2002 µs is (a); its 34/56/59 are all attributed to (b); its 35.7 → 19.2 is (b) → (c).

**Arm 2 — the attribution.** From arm 1, state which of 34, 56 and 59 the read-only phase A produces
on this board, and whether the other two fall inside the measured spread. Three outcomes are possible
and all are declared before the run: they are one number with a wide spread; they are two or three
distinct builds; or none of them reproduces and the shelf's numbers do not transfer to this board.

**Arm 3 — the two related divergences.** Rebuild the ping-pong change across the six named shapes and
the two-row interleave across a row-count sweep, reporting per-case gains. `12~31%` versus `4%~31%`
is settled by whether any case gains ~4%; `8%~18%` versus `约 3%` by whether the gain depends on a
parameter (`R` and row count, which `cum_lane_parallel_scan.md:131` names and `usage_guide.md:125`
does not).

Refuses to assume: that a free die stays free, or that a die may be substituted; that a single run is
a number (every point is ≥20 runs with IQR); that the three published figures describe three builds
(arm 2 tests the alternative); that the timing method is irrelevant (arm 0 measures both, because a
30 µs floor spans the whole disagreement); that this board reproduces upstream's board, which is
unnamed.

## 5 · Checker — acceptance declared before the run
Verdict `floor(method)` from arm 0, in µs, reported before any other number is interpreted.

Verdict `t_readonly` from arm 1(b): median and IQR. Declared before the run:
`divergence_explained` is `spread` iff `[34, 59]` lies inside `median ± IQR`; `builds` iff the three
figures each match a distinct configuration's median within its IQR; `neither` otherwise. The OVERTURN
fires on `spread` or `builds` — both mean the divergence has an explanation, and this entry then
narrows to "upstream published three numbers without stating which configuration or method produced
each".

Verdict `pingpong_gain(case)` and `interleave_gain(rows, R)` from arm 3, as per-case values rather
than ranges — the entry's point is that a range without its cases is unfalsifiable, so the repair is
to publish the cases.

The exit code is not the verdict: every build here is correct, and the entry is about numbers rather
than behaviour. Guards: (1) no timing is reported without its method, its repetition count and its
IQR, and a figure reported bare is `untestable` — this is the exact defect the entry records upstream
having, and a checker that reproduced it would be useless; (2) **the input that makes this checker go
red**: arm 0 at `n = 64`, which per `0418` must show the dispatch floor — if the local method reports
a time proportional to `n` there, the floor does not exist on this board, `0418` does not apply, and
arm 2's `spread` verdict cannot be reached by that route; (3) every point carries its shape, dtype,
build configuration, timing method, board token and CANN pin — the six things the three published
figures lack.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The three sentences with their
three numbers, the two related divergences, the six-case ping-pong table and the measurement-floor
note are file reads performed at drafting time, each re-verified against its file. The observation that
`12~31%` is exactly the range of the top four rows of upstream's own six-row table while `4%~31%`
matches no subset of it is arithmetic over that table, not a measurement. The observation that the
~30 µs floor is comparable to the 34-59 µs spread is arithmetic over two of upstream's own figures;
whether the two were measured by the same method is not stated anywhere and is recorded as open.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish which of 34, 56 and 59 µs is right, or
whether any is — Art. 7 forbids adjudicating a source disagreement by preference, and §4 is the
procedure that would settle it. It does not establish that the three figures describe different
builds, nor that they describe one build measured three ways; both are live and `Q-950fin-28` records
the question. It does not establish that the measurement floor explains the spread — that connection
is a reading of two upstream notes that upstream does not connect. It does not establish the 2002 µs
baseline, which is the one figure all three agree on and which is therefore *not* evidence of anything
except that the prose was copied. It does not evaluate the optimisation itself, which is
`cum_core_partition_scan`'s subject and whose mechanism (`phase A 只读` is a reduction, not a scan, so
it carries no log factor) is stated identically in all three files. It does not cover the shelf's other
measured figures beyond the three named divergences. No board token appears in any of the three files,
so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen.
Nothing here is established for any 910-family board.

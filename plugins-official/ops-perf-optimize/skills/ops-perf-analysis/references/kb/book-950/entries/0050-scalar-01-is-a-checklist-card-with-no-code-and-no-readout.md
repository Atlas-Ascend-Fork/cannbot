```
ID:        0050-scalar-01-is-a-checklist-card-with-no-code-and-no-readout
LABEL:     boundary
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/scalar-01-scalar-bound.md:6 — "**占位卡**：手段清单已整理，`before/after` 代码与 msprof 实测数据**待增量补**（外部 VF 素材以向量为主，scalar 类需另采实测）"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/scalar-01-scalar-bound.md:30 — "**待增量补**：需在 scalar bound 算子上采 msprof `aiv_time` + `aiv_scalar_ratio` 前后对比"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a revision of the card in which any of the six listed measures carries a before/after
           code pair and an `aiv_time` readout with case identity — the absence recorded here
           would then be closed, and this entry becomes a pointer to the measurement.
```

# 0050 · scalar-01 is a checklist card with no code and no readout

## 1 · Claim
Upstream asserts a Scalar-bound technique card consisting of six measures — reduce redundant
scalar computation and merge branches; unroll small loops; minimise loop axes per tiling; select
more efficient scalar instructions; avoid unnecessary scalar↔vector transfers; and prefer
performance-friendly APIs (`set_flag`/`wait_flag` over Queue, `LocalTensor` over TBuf, dropping
superfluous TPipe) — and upstream asserts, in the card's own header and evidence section, that
its before/after code and its msprof data are outstanding, because the external VF material it
was assembled from is vector-centric and scalar cases need their own measurement. Not established
here; there is nothing to establish, and that is what this entry records.

## 2 · The wrong branch this removes
An agent that routes a Scalar-bound verdict into `techniques/` finds a card marked 写满 in one
place (`INDEX.md:27` lists it as 占位, but the routing tables link it like any other card) and
reads six imperative-sounding measures with an effect column. It will apply them and report an
optimisation performed. The card has no before/after, so "apply" means the agent invents the
transformation; it has no measurement, so "effect" is an expectation. The scalar branch of this
skill therefore terminates in advice with no evidence and no worked example — which is worth
knowing before the branch is taken, not after.

The second reason to record the absence rather than skip the card: a replacement skill that quietly
drops scalar-01 would look complete while removing the only pointer to a gap. An entry that names
the gap is what lets the gap be closed.

## 3 · Ground / Source
`scalar-01:1-6`, the header and the placeholder note quoted in SOURCE, with the routing note
`诊断特征见 ../scalar.md`. `scalar-01:8-11` gives the diagnostic conditions — high
`aiv_scalar_ratio` with SCALAR/SCALARLDST busy and VECTOR idle; very small total computation or a
small shape; low IPC; unnecessary synchronisation waits between SCALAR and VECTOR.
`scalar-01:19-26` is the six-row measures table (手段 / 操作 / 效果), whose effect column reads
降低 scalar 指令数, 提升 IPC（配合 vec-10）, 降低 scalar, 缩短关键路径, 减少搬移开销（配合
vec-04）, 减少封装带来的 scalar. `scalar-01:30` is the evidence line quoted in SOURCE.
`scalar-01:33-35` gives two stop rules — unrolling and loop-axis reduction are constrained by
tiling and must be changed together with it; scalar vectorisation belongs to vec-04 and must not be
re-implemented here.

Where the card is reached from: `index.md:61` maps Scalar/小 case to vec-04, vec-09, vec-10 and
scalar-01; `scalar.md:21` links it as the first-choice card for 冗余 scalar / 小循环 / 减循环轴 /
去封装开销. `INDEX.md:27` marks its status 占位 — the only status value other than 写满 in the
whole table, shared with nobound-01 (0051).

The one substantive, non-placeholder piece of scalar knowledge in this half of the skill is not in
this card at all: it is the tile-count claim on the diagnosis page, entry 0017.

## 4 · Procedure
Artifact-level; no device is implicated by the absence claim itself.
```bash
UP=upstream/skills-dev-main/ops/ascendc-perf-optimize
sha256sum $UP/references/single-core-pipeline/techniques/scalar-01-scalar-bound.md
  # 025a3efa53c6725280bdc616340ccaddadc67ca2f2bbe80dea064d30638e3c5d
grep -n "待增量补\|占位" $UP/references/single-core-pipeline/techniques/scalar-01-scalar-bound.md
grep -c "```" $UP/references/single-core-pipeline/techniques/scalar-01-scalar-bound.md   # code fences: expect 0
grep -n "us\b\|%\|aiv_time *[0-9]" $UP/references/single-core-pipeline/techniques/scalar-01-scalar-bound.md
```
The last two lines are the mechanical form of "no code and no numbers": zero fenced blocks and no
numeric readout. To close the gap rather than record it, the work is the measurement the card asks
for — six paired builds on a scalar-bound operator with `aiv_time` and `aiv_scalar_ratio` before
and after, on a named 950 board, device selected per 0010 — which is new work, not verification of
theirs.

## 5 · Checker — acceptance declared before the run
Verdict variable `card_is_placeholder` = (fenced code blocks == 0) AND (numeric readouts == 0) AND
(the placeholder marker is present). At the pinned blob the expected value is true; the entry is
superseded when it becomes false.

Exit code is not the verdict — `grep -c` returns non-zero status when it counts zero, which here is
the confirming observation and not a failure. The counts are printed and compared explicitly.

Red input: any other technique card, for example nobound-02, which has both fenced code and
numeric readouts. Running the same check against it must return false; a checker that reported
"placeholder" for every card would be measuring its own grep patterns.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
This entry establishes nothing about scalar performance on any board — it records that upstream's
scalar card contains no evidence. The six measures may all be sound; nothing here says otherwise,
and nothing here says they are. No board, no shape, no operator. The absence is recorded at one
pinned blob and may be closed upstream at any time without this book noticing.

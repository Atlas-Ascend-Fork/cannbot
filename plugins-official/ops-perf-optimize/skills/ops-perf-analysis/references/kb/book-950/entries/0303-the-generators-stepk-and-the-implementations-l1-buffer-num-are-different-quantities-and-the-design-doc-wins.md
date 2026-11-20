```
ID:        0303-the-generators-stepk-and-the-implementations-l1-buffer-num-are-different-quantities-and-the-design-doc-wins
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/pingpong_design.md:163 —
           "理论建模生成器 `tiling_gen.py` 输出的 `stepK=2` 是 K 向分步的理论档位（受 depth 倍增
           搜索机制约束只能为 2 的幂），与本文档的 `L1_BUFFER_NUM=3` 是两个独立概念。**实施时应以
           本文档的 `L1_BUFFER_NUM=3` 为准**"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-fields.md:24 —
           "上限 4，且只能取 2 的幂"   # the analysis-layer twin, carried by 950:0109
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board where setting `L1_BUFFER_NUM` to the generator's `stepK`
           produces the same L1 layout, the same outer-loop trip count and the same kernel time as
           setting it to the design document's value — the two would then be the same quantity
           under different names and the precedence rule would be empty.
```

# 0303 · The generator's `stepK` and the implementation's `L1_BUFFER_NUM` are different quantities, and the design doc wins

## 1 · Claim
Upstream asserts that two numbers which both describe "how much K one L1 buffer covers" are not the
same number: the tiling generator's `stepK`, which its own doubling search restricts to powers of
two, and the implementation document's `L1_BUFFER_NUM`, which is the largest integer whose doubled
buffer fits L1 (`0301`). Upstream asserts a precedence: at implementation time, the design
document's `L1_BUFFER_NUM` governs. In the worked case the two differ — the generator emits
`stepK = 2`, the design document uses `L1_BUFFER_NUM = 3`. Not established here.

This is the same disagreement `950:0109` records from the other side of the shelf, where the
analysis layer states `stepK` has five incompatible upper bounds inside one family. Here the
implementation layer says the question is malformed: the generator's value is a modelling rung, not
the kernel's constant.

## 2 · The wrong branch this removes
A harness agent that runs the tiling generator, reads `step_k: 2` out of its YAML, and writes it
into the kernel as the L1 depth. Nothing rejects that. The kernel builds, it is correct, and it
covers `2 × baseK = 512` of K per buffer instead of 768 — a third fewer, so a half again as many
outer-loop iterations, each paying pipeline start/stop. There is no error message, no profile
signature that says "your L1 depth came from the wrong document", and the 33 % occupancy left on the
table looks like normal headroom.

The reverse branch is equally available and louder: an agent that notices `L1_BUFFER_NUM = 3` is not
a power of two, concludes the design document contradicts the generator's stated constraint
(`只能取 2 的幂`), and "fixes" the design document down to 2. It has then reconciled two numbers
that were never the same number, and it has done so in the direction that loses performance.

The entry's real content is the reading skill, not the constant: when two upstream artifacts give
different values for what looks like one parameter, the first question is whether they are one
parameter. Here upstream answers it explicitly. Elsewhere in this shelf it does not (`950:0109`,
`0309`), and then the disagreement is real.

## 3 · Ground / Source
`pingpong_design.md:163`, the closing sentences of the `L1_BUFFER_NUM` selection note:

```
理论建模生成器 `tiling_gen.py` 输出的 `stepK=2` 是 K 向分步的理论档位（受 depth 倍增搜索机制
约束只能为 2 的幂），与本文档的 `L1_BUFFER_NUM=3` 是两个独立概念。**实施时应以本文档的
`L1_BUFFER_NUM=3` 为准**
```

Two assertions are packed there and they are different in kind. That the generator's value is
constrained to powers of two is a statement about a search algorithm — `950:0109` §3 quotes the
mechanism from the other side (`depth_scale *= 2`). That the two are "两个独立概念" is a semantic
claim about what each name denotes, and upstream states it without defining either denotation. The
precedence sentence is a normative instruction, not a fact about the machine.

The analysis-layer twin, for contrast, treats `stepK` as the kernel's L1 K-depth directly:
`ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-fields.md:24` gives "上限 4，且只能
取 2 的幂", and `tiling-flow.md:165-179` derives `nBufferNum ∈ {4, 2}` from an L1 capacity test —
a two-rung ladder, carried by `950:0113`. So the two shelves model L1 depth with different variables
and different admissible sets: `{1, 2, 4}` (analysis layer) against "largest integer that fits"
(implementation layer, here 3). Both files are in the same repo, so this is one origin disagreeing
with itself, not corroboration (RULES.md Art. 3). Recorded as `C-950bp-002`.

What upstream does **not** say, and this entry will not supply: whether `stepK` and
`L1_BUFFER_NUM` index the same physical extent at all. If `stepK` counts `baseK` blocks per
*movement* and `L1_BUFFER_NUM` counts them per *buffer*, they are genuinely different and the
precedence rule is a translation rule. If they are the same extent, upstream's own two shelves emit
contradictory kernels. §4 is written to tell those apart, because reading cannot.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — are they the same extent? Build the family's matmul three ways at the fixed shape
`M=1024, N=2048, K=4096, baseM=baseN=256, baseK=256`: (a) `L1_BUFFER_NUM = 3`, (b)
`L1_BUFFER_NUM = 2`, (c) the generator's plan with `step_k = 2` fed through unchanged. For each,
echo from the kernel: `kL1`, the byte offset of `B_ping` inside L1 (which pins the actual buffer
size), the outer-loop trip count, and total L1 requested. Two builds are the same quantity iff all
four echoes agree. Prediction if upstream is right about "独立概念": (b) and (c) agree on `kL1` but
may differ elsewhere; if (b) and (c) agree on *everything*, then `stepK` is `L1_BUFFER_NUM` under
another name and §1's semantic claim is empty.

Arm 2 — does the precedence rule pay? Time (a) and (c) at three K lengths (`1024`, `4096`,
`16384`), recording kernel time, MTE2 segment and trip count, with a variance floor established
first (one build, 30 in-process runs, 5 fresh-process runs, IQR over median). Upstream's
instruction predicts (a) wins. It is the instruction, not the arithmetic, that is on trial.

Arm 3 — the generator's constraint, checked rather than believed. Run `tiling_gen.py` (or the
`ascendc-perf-optimize` fallback script that plays its role) over a sweep of shapes and record every
`step_k` it ever emits. `950:0109` records that a sibling family's worked output emits `step_k: 3`;
if this generator also emits a non-power-of-two, the "只能取 2 的幂" premise on which the whole
"独立概念" argument rests is false, and the entry is corrected in place.

Device selection: operator names the index; probe echoes it with `compiler/version.info`; occupancy
sampled three times at 20 s spacing before binding and re-sampled after, case discarded if the die
moved; no die substituted. Arm 3 needs no device and is marked `[no-card]` — it is answerable in
this phase and has not been run, which is itself part of the record.

## 5 · Checker — acceptance declared before the run
Verdict `same_quantity` = true iff Arm 1's builds (b) and (c) agree on all four echoed values.
Declared now: `same_quantity == true` **overturns** §1's semantic claim; `false` supports it and the
entry then states *which* echo differed, because that is the operational content of "独立概念".

Verdict `precedence_pays` = true iff Arm 2's (a) is faster than (c) at every K outside the floor.
`false` at any K demotes the precedence sentence from a rule to a default and the entry says so.

Verdict `powers_only` = true iff every `step_k` Arm 3 observes is a power of two ≤ 4.

The exit code is not the verdict. Two guards. First, the four echoed values are echoed *from the
kernel*, not read from the host tiling struct: the failure this arm must be able to catch is a host
field that is set and then ignored, and a host-side read cannot see it. Second — the input that
makes this checker go red — build (c) is additionally compiled with the generator's plan
deliberately edited to `step_k = 1`; the echoed `kL1` and trip count **must** move. If they do not,
the plan is not reaching the kernel at all, every comparison against (c) is void, and the run is
reported as such rather than as a null result. That fixture is a positive the checker must find,
not a clean line it hopes to read.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `stepK = 2` and
`L1_BUFFER_NUM = 3` are upstream's stated values for one worked shape; no build was made, no plan
was generated, and no kernel echoed anything.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the two names denote different
extents — it establishes that upstream asserts they do and instructs which to follow. It does not
establish that following that instruction is faster. It does not resolve `950:0109`'s five-value
`stepK` disagreement and must not be read as doing so: that disagreement is inside the analysis
shelf, this precedence rule is about crossing between shelves, and both are one origin (RULES.md Art. 3),
so nothing here corroborates anything there. The generator named (`tiling_gen.py`) is not present in
this tree and its behaviour is taken entirely from one sentence about it. BOARD is
`family-claimed(unverified)`: no file in this family names a chip (`0347`). The claim is scoped to
the single worked shape; a different `baseK` moves both numbers and is not evidence about this one.
Nothing transfers to the other book (RULES.md Art. 1).

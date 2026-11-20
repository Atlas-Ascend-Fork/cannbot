```
ID:        0469-this-shelfs-matmul-family-covers-one-fusion-pattern-whose-multi-core-answer-is-the-opposite-of-the-general-familys
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/patterns.md:5-6 —
           "> 当前覆盖范围：**mxfp8 quantized matmul + eltwise 融合**（Div / Mul / Add / Relu / Cast /
           组合算子）。 / > 其它 matmul 形态（fp16/bf16 matmul、BatchMatmul 等）仍在规划中。" ·
           :15-17 — "Step 0 — 算子分类： / ├─ mxfp8 matmul + eltwise 融合 → 本文件 §Tiling 设计要素 /
           └─ 其它 matmul 形态 → 规划中（暂无正式指南，建议参考 Ascend C 官方示例）" ·
           :43 — "| 切分维度 | M × N 二维切分（K 轴在核内迭代，不参与核间切分） |" ·
           :46 — "| 核数计算 | `usedCoreNum = CeilDiv(M, singleCoreM) × CeilDiv(N, singleCoreN)`
           **强制动态计算**，禁止硬编码 |"
SOURCE:    same family, matmul-fusion-design-template.md:30 —
           "| 支持芯片 | Ascend950（mxfp8 仅 Ascend950 硬件支持） |" ; :3 —
           "> **本模板仅用于** mxfp8 matmul + eltwise 融合场景。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an mxfp8 + eltwise fusion case on a named 950 board at which splitting K across cores beats
           the M×N split by more than the variance floor — the scope-local rule "K does not cross
           cores" would then be a limitation of the SWAT engine rather than a property of the fusion
           pattern. Equally: an agent routed here by the taxonomy tick that produces a working plain
           fp16 matmul plan from this document would show the boundary costs nothing.
```

# 0469 · This shelf's matmul family covers one fusion pattern, whose multi-core answer is the opposite of the general family's

## 1 · Claim
Upstream asserts that the tiling-design shelf's matmul material covers exactly one scenario — mxfp8
quantised matmul fused with an elementwise epilogue (Div, Mul, Add, Relu, Cast, or combinations) — and
that all other matmul forms, naming fp16/bf16 matmul and BatchMatmul, are planned with no formal guide
and a suggestion to consult official examples instead. Upstream asserts, for that one scenario, a
multi-core decomposition: a two-dimensional M×N split with the K axis iterated **inside** the core and
not participating in the inter-core split, snake scheduling by a `BlockScheduler`, per-core work
`singleCoreM × singleCoreN` computed by a tiling engine named SWAT, and a core count
`usedCoreNum = CeilDiv(M, singleCoreM) × CeilDiv(N, singleCoreN)` that must be computed dynamically
with hard-coding forbidden. Upstream asserts a chip: mxfp8 is supported only on Ascend950 hardware.
Not established here.

## 2 · The wrong branch this removes
Without this entry an agent with a matmul requirement follows the taxonomy tick. The tiling-design
skill's MatMul row carries a `✅` — the same glyph as Reduction and FlashAttention — and links here
(`0467`). The agent arrives, finds a complete four-part tiling methodology with formulas, buffer
tables and a design template, and uses it. The document's scope line is its fifth line and is a
block-quote above the first horizontal rule, which is exactly where a reader skips to reach the
content.

What it then gets wrong is not a detail. **This document says the K axis does not cross cores.** The
general matmul family on the neighbouring shelf, already carried in this book, has StreamK — a strategy
whose entire purpose is splitting K across cores, with an entry gate stated at `K ≥ 32768` and computed
at `K ≥ 4096` (`0107`, `0108`, `0309`), an FP32 workspace and an AIV reduction to pay for it (`0310`).
Both are correct. They answer different questions: this document describes one fusion pattern whose
epilogue runs on the vector cores fed by a fixed Fixpipe path, and the neighbouring family describes
general matmul tiling. An agent that carries "K stays inside the core" out of this scope and into a
large-K fp16 matmul has taken a scope-local rule as a family rule, and the resulting plan leaves the
parallelism StreamK exists to recover on the table.

**This is a boundary, not a contradiction.** The two statements never meet: `patterns.md:5-6` scopes
this file to one pattern before it makes any claim, so nothing here contradicts `0107`–`0110` or
`0303`/`0309`/`0310`, and no contradiction row is filed. The failure mode is a routing failure, and it
is created by the taxonomy tick rather than by either document.

The second wrong branch is the mirror: an agent that reads the scope line, concludes this shelf has
nothing for it, and does not notice that the *fusion-specific* material here — ODD-M/ODD-N handling
(`0470`, `0471`), the `stageNum` rule (`0473`), the `DataCopyExtParams` unit split (`0475`) — is real
knowledge that no other shelf in this corpus carries.

## 3 · Ground / Source
The scope, `references/matmul/patterns.md:5-6`:

```
> 当前覆盖范围：**mxfp8 quantized matmul + eltwise 融合**（Div / Mul / Add / Relu / Cast / 组合算子）。
> 其它 matmul 形态（fp16/bf16 matmul、BatchMatmul 等）仍在规划中。
```

restated as the routing tree's own first step, `:13-18`:

```
给定：算子需求（含 mxfp8 量化 + eltwise 后处理？）

Step 0 — 算子分类：
  ├─ mxfp8 matmul + eltwise 融合 → 本文件 §Tiling 设计要素
  └─ 其它 matmul 形态 → 规划中（暂无正式指南，建议参考 Ascend C 官方示例）
```

So the document does route correctly *once opened*: an agent that reads Step 0 is sent away. The
mis-route happens one level up, at the taxonomy table whose `✅` and whose example column
(`MatMul, BatchMatMul`) name the operators this file's Step 0 declines. That is `C-950fin-014`, filed
against `0467`.

The multi-core decomposition, `:43-47`:

```
| 切分维度 | M × N 二维切分（K 轴在核内迭代，不参与核间切分） |
| 调度方式 | 蛇形调度（BlockScheduler），参考工程 `matmul_kernel_fused.h` |
| 单核任务量 | `singleCoreM × singleCoreN`（由 SWAT Tiling 引擎自动计算） |
| 核数计算 | `usedCoreNum = CeilDiv(M, singleCoreM) × CeilDiv(N, singleCoreN)` **强制动态计算**，禁止硬编码 |
| 负载均衡 | BlockScheduler 蛇形分配保证同 row/col 的核工作量一致 |
```

Three observations that are not in the text.

The core count is **derived, not chosen**. `usedCoreNum` is a function of the problem shape and the
per-core work, so it can exceed or fall short of the physical core count, and this document never
compares it against a queried `GetCoreNumAic()`. The FA family does exactly that comparison
(`usedCoreNum = min(aicNum, totalTasks)`, `flashattention/design.md:189`), so two families on one shelf
compute the same quantity by different means and only one clamps it. Recorded as `Q-950fin-18`.

`强制动态计算，禁止硬编码` is the one place in this shelf that states the rule this corpus records
being broken elsewhere: C-007 registers five different hard-coded core counts across the neighbouring
shelf's scripts (64, 72, 32, 8, 24), none chip-scoped. This document forbids exactly that, and the two
sit in one repository.

`SWAT` is named as the engine that computes `singleCoreM`, `singleCoreN`, `baseM/baseN/baseK` and the
L1 rolling depths (`:64`, `:66`, `template:167`, `:254-256`). It is named seven times across the two
files and never defined, located, or given an interface beyond a header path in a reference project.
Every tile-size decision in this family is delegated to it. Recorded as `Q-950fin-19`.

The chip, `matmul-fusion-design-template.md:30`:

```
| 支持芯片 | Ascend950（mxfp8 仅 Ascend950 硬件支持） |
```

This is a genuine 950 self-attribution and it is worth marking against `0347`, which records that the
*other* shelf's matmul family names no chip in any of its seven files. Different family, so no
contradiction — but the contrast is the useful part: the family that is scoped to one quantised
fusion says which hardware it needs, and the family that is general says nothing. `Ascend950` names
the family per this book's vocabulary map, not a board, so BOARD stays `family-claimed(unverified)`.

The template restates the scope in its own second line (`> **本模板仅用于** mxfp8 matmul + eltwise
融合场景。`), so the scope is stated three times across two files. Two files, one repository: one
origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first, reported beside every point.

**Arm 1 — the scope-local rule, inside its own scope.** An mxfp8 + Div fusion at shapes where K
dominates (`M, N` small, `K ∈ {8192, 32768, 131072}`), built two ways: the M×N split this document
prescribes, and a K-split with the FP32 workspace and vector reduction that the neighbouring family's
StreamK uses (`0310`). Report `aic_time`, `aiv_time`, workspace bytes and correctness for both. If the
M×N split wins everywhere, "K does not cross cores" is a property of this pattern; if not, it is a
limitation of the engine and the OVERTURN fires.

**Arm 2 — the derived core count.** Echo `usedCoreNum` from the formula alongside `GetCoreNumAic()`
across a shape sweep that makes the formula's value both smaller and larger than the physical count.
Record what happens in the second case. `Q-950fin-18` asks whether anything clamps it; this arm
answers it by construction rather than by reading.

**Arm 3 — the routing consequence.** Give an agent that has not read this entry a plain fp16
`BatchMatMul` requirement plus the tiling-design skill, and record which document it opens and whether
its plan splits K across cores. Repeat with the taxonomy row's glyph changed to `⚠️`. This is a
procedure over an agent, and it is the same arm `0467` proposes for the same row; running them together
costs one experiment rather than two.

**Arm 4 — retained because it may not bite.** Build the mxfp8 fusion with `usedCoreNum` hard-coded to
the values C-007 records from the neighbouring shelf's scripts (64, 72, 32) and compare against the
dynamic computation at a shape where the correct value is none of them. If the hard-coded builds are
merely slower, the prohibition is a performance rule; if any of them is wrong or faults, it is a
correctness rule, and upstream does not say which.

Refuses to assume: that a free die stays free, or that a die may be substituted; that the two split
strategies differ only in the K axis (each arm echoes its full tiling); that `usedCoreNum` is what the
host computed (echoed from the device); that SWAT's outputs are reproducible across builds (each build
echoes `baseM/baseN/baseK`, `depthA1/depthB1`, and a point whose echoed tiling differs from the
previous build's is a finding, not a discard — `Q-950fin-19`); that a fast fusion is a correct one.

## 5 · Checker — acceptance declared before the run
Verdict `mn_split_wins(K) := median t(M×N) < median t(K-split) − floor`, declared before the run.
Acceptance for the scope-local rule: `mn_split_wins` true at every swept `K`. The OVERTURN fires iff it
is false at any `K`, which would make the rule an engine limitation.

Verdict `core_count_clamped` from arm 2 ∈ {`clamped`, `unclamped_ok`, `unclamped_fails`}.

Verdict `misroutes_on_tick` from arm 3 ∈ {`yes`, `no`}, with the document actually opened recorded
either way.

Verdict `hardcode_outcome` from arm 4 ∈ {`slower`, `wrong`, `faults`, `same`}.

The exit code is not the verdict: both split strategies in arm 1 are correct by construction, and
arm 3's outcome is a document choice rather than a return code. Guards: (1) every timing point carries
its echoed tiling, its floor and an elementwise comparison against an FP64 reference — a matmul with a
wrong `K` padding exits 0 and is fast (`0471`); (2) **the input that makes this checker go red**:
arm 1 at small `K` with large `M×N`, where the M×N split must win decisively — if the K-split wins
*there*, the two builds differ in more than their split axis and every crossover in the sweep is an
artifact; (3) arm 2 must report at least one shape where the formula exceeds the physical core count,
and is reported `untestable` otherwise, since a sweep that never reaches the interesting case cannot
answer the question it was built for.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The scope statements in their
three locations, the routing tree's Step 0, the five-row multi-core table, the chip line and the
template's own scope line are file reads performed at drafting time. The observations that
`usedCoreNum` is derived rather than clamped, that SWAT is named seven times and never defined, and
that this family names a chip where the neighbouring general matmul family does not (`0347`), are
readings of upstream's own lines and of an existing entry, not observations of a build. **No
contradiction row is filed against `0107`–`0110`, `0303`, `0309` or `0310`: the two multi-core answers
are scoped to different operator classes and never meet.**

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the M×N split is right for the
fusion pattern, nor that a K split would be wrong there — upstream states the decomposition and gives
no measurement, no shape and no comparison. It does not establish anything about general matmul: this
document declines that scope in its own Step 0, and this book's general matmul entries stand
untouched. It does not establish that mxfp8 is Ascend950-only, only that upstream says so; no header,
no board and no test is cited for it, and `Ascend950` names a family rather than a board. It does not
establish what SWAT computes or how (`Q-950fin-19`), nor whether `usedCoreNum` is clamped anywhere
(`Q-950fin-18`). It does not cover the snake scheduler beyond naming it, nor `BatchMatmul`, which this
family explicitly defers. It does not evaluate the taxonomy tick itself, which is `0467`'s subject.
No board token appears in any quoted passage, so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT only as where our run would happen. Nothing here is established for any 910-family board.

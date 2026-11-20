```
ID:        0399-maskpredicate-is-a-gate-and-an-injection-and-never-the-paradigm-that-writes-the-design
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream states the
           routing with ⛔ prohibitions and names no enforcement mechanism. Nothing was compiled and no
           design was generated.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/mask_predicate/patterns.md:3-11 —
           "## 范式定位：门禁路由 + 能力补充 / MaskPredicate **不是独立的设计文档生成范式**。正确流程：/
           1. **先路由**：门禁校验通过后，按 `spec.yaml` 的 `paradigms` 字段选定基础范式 / 2. **再生成**：
           **⛔ 禁止按本范式写设计文档**——必须使用路由到的基础范式的 `patterns.md` 产出完整的设计文档。…
           3. **后补充**：基础范式设计文档写完，再读取 [补充能力] 向指定章节注入 mask 谓词判定相关的计算
           逻辑与约束 / 完整设计文档的骨架（Tiling 切分 / 调度 / 同步 / 数据搬运 / 内存管理 / API 验证等）
           由**基础范式**独占负责。"
SOURCE:    same file:17-20 — the two gate conditions: "**逐元素对应**：mask 的每个元素必须整体作为一个谓词
           判定单元（1 个 mask 元素 → 1 个 data 元素），禁止将 mask 元素的各个 bit 展开为独立谓词。…
           **value dtype 可转换性**：填充源 dtype 必须能安全转换到数据源 dtype，否则和上一条一样忽略本范式。"
SOURCE:    same file:24-30 — the routing: "1. 若 spec.yaml 的 `paradigms` 字段**含 `MaskPredicate` 以外的
           范式** → 按照设计文档的生成规则，使用`MaskPredicate` 以外的其他范式进行设计文档的生成。/
           2. 若 spec.yaml 的 `paradigms` 字段**仅含 `MaskPredicate`**（或为空）→ 按 shape 关系路由：/
           - mask shape 与 data shape 完全相同（或 value 为标量、所有输入同形）→ elewise 范式 … /
           - mask 可广播到 data shape 但不一定同形 → Broadcast 范式 … / - 两者皆不满足 → 走兜底模板。"
SOURCE:    same file:60-85,93-97 — the injected content and its single injection point: the three
           self-check questions, "极性错一个 = 输出整体取反", the four correspondence requirements, and
           "**注入位置**：注入到基础范式设计文档的 **VF 代码之前**，新增 `##### mask 极性分析与逐元素对应`
           子节"; "**未列出章节**（Tiling 切分 / 调度 / 同步 / mask 数据搬运与类型转换 / 输出搬运 /
           内存管理 / VF 函数签名等骨架章节）→ **完全由基础范式负责，MaskPredicate 不介入**。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `masked_fill`-class operator whose design document, generated from the MaskPredicate file
           alone, is complete by the base paradigm's own section list — which would make the ⛔
           prohibition an editorial preference rather than a structural rule. Equally: a mask whose bits
           are legitimately expanded into independent predicates and which the base paradigms handle
           correctly, which would make the first gate condition too strict.
```

# 0399 · MaskPredicate is a gate and an injection, and never the paradigm that writes the design

## 1 · Claim
Upstream asserts that MaskPredicate is **not** a design-document-generating paradigm, and states a
three-step order: gate first, then route to a base paradigm, then generate the complete design document
from the base paradigm's own `patterns.md`, and only afterwards inject the mask-predicate content into
named sections. Upstream asserts two ⛔ prohibitions: it is forbidden to write the design document
according to MaskPredicate, and it is forbidden to consult the supplementary capability section while
generating the base paradigm's document. Upstream asserts that the complete document's skeleton — tiling
split, scheduling, synchronisation, data movement, memory management, API validation — is the base
paradigm's exclusive responsibility. Upstream asserts two gate conditions: each mask element must act as
one whole predicate unit driving one data element, with bit-level expansion forbidden; and the fill
source's dtype must be safely convertible to the data source's dtype. Failing either, the operator is
routed by `spec.yaml`'s other paradigms or to a fallback template. Upstream asserts the routing when
MaskPredicate is the only listed paradigm: identical mask and data shapes (or a scalar value with all
inputs同形) route to elewise; a mask broadcastable but not identically shaped routes to Broadcast; neither
routes to the fallback. Upstream asserts one injection point — a new subsection immediately before the VF
code — and asserts that every unlisted section is entirely the base paradigm's. Not established here:
nothing was compiled, no design was generated, and upstream names **no enforcement mechanism** for either
prohibition.

## 2 · The wrong branch this removes
A file named `<paradigm>/patterns.md` sitting beside `elewise/patterns.md`, `broadcast/patterns.md` and
`reduction/patterns.md` looks like a peer. It is not, and the shape of the directory says it is.

**What an agent does without this.** It routes to MaskPredicate because the operator has a mask, opens
`mask_predicate/patterns.md`, and generates a design from it. What it gets is a gate, a routing table and
one injection subsection — 99 lines against `broadcast/patterns.md`'s 322 and `reduction/patterns.md`'s
535. So the resulting design has a polarity analysis and **no tiling split, no scheduling, no
synchronisation, no data movement plan, no memory management and no API validation**. Those are not
sections the agent forgot; they are sections its source does not contain. And the omission is invisible
from inside: the document it produced is internally coherent and complete with respect to the file it was
generated from.

That is why upstream's prohibition is ⛔ and repeated: the failure is not a wrong section, it is six
absent ones, and nothing in the generated artifact indicates absence.

**The second prohibition is subtler and is about ordering.** 在生成过程中禁止查看补充能力 — do not read the
supplementary capability while generating the base document. The reason is not secrecy; it is that mask
logic read early *shapes* the base design. An agent that has the polarity analysis in mind while writing
the tiling section will tile around the mask, and the base paradigm's tiling rules — which are about the
data shape — get bent to accommodate a predicate that should be a per-element operation inside the VF.
The result is a design that is neither the base paradigm's nor a coherent alternative, which is the
hybridisation failure 0370 records in a different setting.

**The gate's first condition is a real machine constraint, not a scoping convenience.** One mask element
→ one data element. Upstream's counter-example is explicit: a `uint8` mask value `00110011` read
bit-wise would mean one mask element driving *eight* data elements. That is a different data movement
problem entirely — the mask tile and the data tile have an 8:1 element ratio, so every CopyIn count, every
`UpdateMask` extent and every store extent differs between the two operands. The base paradigms' tiling
assumes matched counts. So the gate is protecting the base paradigm's arithmetic, and an operator that
fails it and is forced through anyway produces a kernel whose mask and data loops are off by a factor of
eight — silently, because both loops are individually well-formed.

**Polarity is the cheapest catastrophic error in this family.** 极性错一个 = 输出整体取反 — get the polarity
wrong and the entire output is inverted. `masked_fill(x, mask, value)` is `mask==1 ? value : x`;
`where(mask, x, y)` is `mask==1 ? x : y`. An agent that has both operators in context and writes one's
polarity into the other produces a tensor of exactly the right shape, dtype and magnitude distribution,
with every element from the wrong branch. A tolerance-based comparison reports total failure and gives no
hint that the cause is a single inverted predicate rather than a broken compute chain — which is why
upstream demands a written answer to three specific questions rather than a review pass.

**The three questions are the artifact, not the reasoning.** 必须独立成节 — must be its own section — and
the required output is a regbase code block stating what happens at mask 0 and mask 1 and how the mask
drives the computation. That is a check that leaves evidence: a reviewer can read the section and disagree
with it. A polarity decision made in an agent's head leaves nothing to disagree with, which is the same
principle 0360 records for naming the logical unit in a tiling design.

## 3 · Ground / Source
The positioning and the three steps, `mask_predicate/patterns.md:3-11`:

> ## 范式定位：门禁路由 + 能力补充
>
> MaskPredicate **不是独立的设计文档生成范式**。正确流程：
>
> 1. **先路由**：门禁校验通过后，按 `spec.yaml` 的 `paradigms` 字段选定基础范式（详见路由规则）
> 2. **再生成**：**⛔ 禁止按本范式写设计文档**——必须使用路由到的基础范式的 `patterns.md` 产出完整的设计
>    文档。**⛔ 必须严格按照设计文档生成的要求，使用除了MaskPredicate范式以外的其他选定范式生成完整的设计
>    文档，禁止跳过任何章节，在生成过程中禁止查看补充能力。基础范式的所有关键产物，要求的伪代码都必须生成**
> 3. **后补充**：基础范式设计文档写完，再读取 [补充能力](#maskpredicate-补充能力) 向指定章节注入 mask 谓词
>    判定相关的计算逻辑与约束
>
> 完整设计文档的骨架（Tiling 切分 / 调度 / 同步 / 数据搬运 / 内存管理 / API 验证等）由**基础范式**独占负责。

Two ⛔ markers in one numbered item, plus 禁止跳过任何章节 and 禁止查看补充能力 — four prohibitions in three
lines. That density is unusual in this subtree and is itself evidence about what upstream expects to go
wrong.

The gate, `:17-20`, quoted in SOURCE, with the bit-expansion counter-example in full:

> 例如：mask 为 uint8 值 `00110011`，若以 bit粒度展开意味着该 mask 元素的 8 个 bit 分别对应 8 个 data
> 元素（1 个 mask 元素 → 8 个 data 元素），这种情况下忽略本范式

The routing, `:24-30`, quoted in SOURCE. Note that failing the gate and having no other paradigm both lead
to 兜底模板 (`general-methodology.md`), so the fallback is the terminal state for anything the two named
base paradigms cannot express.

The injected content, `:60-85`. The three self-check questions:

> | # | 问题 | 答案来源 |
> | 1 | mask 为 1（非零/真）时算子执行什么操作？ | 由算子计算表达式定 |
> | 2 | mask 为 0（假）时算子执行什么操作？ | 由算子计算表达式定 |
> | 3 | 1 个 mask 元素是否驱动 1 次对 data 元素的操作？mask 与 data 是否一一对应？ | 由算子语义定 |

the polarity examples and the consequence at `:74` — "确认 mask 真假分支后，再判定后续操作的的真假与上述
分支是否一致——极性错一个 = 输出整体取反" (the doubled 的的 is upstream's) — and the four correspondence
requirements at `:80-83`, of which the third is the operational one:

> 3. **搬入搬出数量校验**：严格检查 regbase 计算时 mask 与 data 的 CopyIn 搬入数量、StoreAlign 搬出数量
>    是否一一对应，禁止数量错位。

That names `StoreAlign` specifically, which ties the requirement to 0257's store contract: the mask's
extent and the data's extent must agree at the store, and a masked store's mask is a `MaskReg` whose lane
count is derived per 0252 — so a mask operand tile and a `MaskReg` are different objects and the
requirement is about the former.

The injection point and the exclusions, `:85` and `:93-97`, quoted in SOURCE. One injection point, before
the VF code; everything else explicitly out of scope.

The Pre-flight checklist at `:46-52` has exactly one row — "已确定基础范式" — which is the whole discipline
in one line.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3). The other paradigm families
(`elewise/`, `broadcast/`, `reduction/`, `layout_transform/`, `quantization/`, `matmul/`, `recurrence/`,
`stateful/`, `numerical_stable/`, `design-check-lite/`) total some 3 800 lines and were **not** mined in
this block; that omission is recorded in §7 and in the final report.

## 4 · Procedure
The claim is about a document-generation process, so most arms are generation experiments. Two need a
board.

Arm A — the completeness gap, measured. Generate a design document for one `masked_fill`-class operator
twice: once from `mask_predicate/patterns.md` alone, once by the prescribed route (gate → elewise →
inject). Diff the section lists against `elewise/patterns.md`'s required outputs. The count of sections
present in the second and absent from the first is the measurement, and it is what turns the ⛔ into a
number.

Arm B — the ordering prohibition. Generate the base document twice with two agents: one that has read the
supplementary capability first, one that has not. Compare the tiling and data-movement sections. §2
predicts the first bends its tiling around the mask. Any systematic difference in those sections is the
evidence for the second ⛔; no difference means the prohibition is protecting against something that does
not happen with this generator.

Arm C — the gate's first condition, on a board. Build one operator whose mask is element-wise
(1 mask element → 1 data element) and one whose mask is bit-packed (1 → 8), both forced through the
elewise base paradigm with matched *tile* counts. Record correctness. §2 predicts the second is wrong by
a factor of eight in its mask extent; recording *how* it is wrong — every eighth element correct, or the
first eighth correct — is what a debugging agent needs.

Arm D — polarity, made detectable. Build `masked_fill` with correct and inverted polarity and compare
each against a host reference. Record the error signature: §2 claims an inverted polarity produces a
plausible tensor with every element from the wrong branch. Confirming that the signature is
*indistinguishable from a broken compute chain* under a tolerance metric is the point — and 0396's metric
rule applies: report the worst samples and their neighbourhoods, since a contiguous-versus-scattered
pattern is what would separate the two causes.

Arm E — the dtype-convertibility gate. Build the fill path with a value dtype that is not safely
convertible to the data dtype (int32 value into a bf16 data tensor) and record whether anything rejects
it — at spec generation, at tiling, at compile, or not at all. Upstream makes it a gate condition and
names no enforcement.

Device selection, for Arms C, D and E: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`missing_section_count` (Arm A) — the number of base-paradigm-required sections absent from the
MaskPredicate-only document. Pass iff ≥ 1; predicted ≥ 6. Reported as a list of section names, not a count:
which sections are missing decides how serious the omission is, and a count would treat "API validation"
and "tiling split" as equivalent.

`ordering_effect` (Arm B) — a diff of the tiling and data-movement sections between the two generation
orders. Reported, not gated: upstream states a prohibition and no predicted difference, so any systematic
divergence is the finding and none is also informative.

`bit_expansion_failure_mode` (Arm C) — three-valued: rejected, wrong by a factor of eight, or correct.
Reported with the failing element pattern. "Correct" is a live outcome and would mean the gate's first
condition is stricter than the base paradigms require.

`polarity_error_signature` (Arm D) — max absolute error, max relative error, and the worst-20 sample
neighbourhoods, for the inverted build. Reported per 0396's metric rule and never as a single figure.
Declared in advance: the question is whether the signature is *distinguishable* from a compute-chain
defect, which no scalar can answer.

`dtype_gate_enforced` (Arm E) — four-valued by where the rejection occurs, or `not enforced`. Reported.

The positive fixture, declared before the run: Arm A must include a **control generation** of the same
operator from `elewise/patterns.md` alone, whose section list must match the prescribed route's — if it
does not, the diff is measuring the generator's variance rather than the paradigm's content, and the
missing-section count is an artefact. And Arm D must include a **correct-polarity** build whose error
against the reference is at the tolerance floor; if it is not, the comparison is reporting an unrelated
defect and the inverted build's signature attributes nothing. Without both, the checker reads only "the
document was shorter and one build was wrong", which cannot distinguish the claim from generator noise —
the known blind species.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No design was generated, no
operator built, no mask applied, no die contacted. The quoted passages are re-verified file reads of the
upstream tree performed during this harvest, as are the line counts of the sibling paradigm files.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or generated. The entry does not establish that a MaskPredicate-only design is
incomplete, that reading the supplementary capability early distorts the base design, that a bit-expanded
mask fails, or that the dtype gate is enforced anywhere — Arms A through E are all open, and upstream
states the prohibitions with **no enforcement mechanism**.

It does not establish the base paradigms' content. `elewise/patterns.md` (46 lines) and its `tiling.md`
(215), and `broadcast/patterns.md` (322), are the documents this routing sends an agent to, and **none of
them was mined in this block**. So the section list Arm A would diff against is unknown to this book, and
the claim "six sections are missing" is upstream's own list of the skeleton's parts, not a verified
inventory of either base paradigm.

**The paradigm families are sampled, not mined.** `references/paradigms/` carries roughly 3 800 lines
across ten families; this block took one file. `layout_transform/`, `quantization/`, `matmul/`,
`recurrence/`, `stateful/`, `design-check-lite/`, the reduction and broadcast template subtrees, and the
worked example packages are all unharvested. What they contain is unknown to this book, and this entry
must not be read as covering the paradigm layer.

It does not establish the routing's completeness. Two shape relations route to two paradigms and everything
else goes to a fallback template (`general-methodology.md`) that this harvest did not read; whether the
fallback is a real path or a placeholder is unestablished.

It does not establish what `spec.yaml`'s `paradigms` field contains or who writes it — the routing's first
branch depends entirely on it, and no file in this harvest's scope documents the field. 0364 §3 records the
same file's `aliasing` field being generator-defaulted and manually corrected, which is a reason not to
assume `paradigms` is reliably populated either.

It says nothing about how the injected polarity section relates to the `MaskReg` and mask-generation APIs
(`CreateMask`, `UpdateMask`, 0255) — the requirement at `:82` names `CopyIn` counts and `StoreAlign`
extents, which are about the mask *operand tile*, and the relationship between that tile and a `MaskReg`
lane count (0252) is drawn by no source in scope.

BOARD is `family-claimed(unverified)`: the file names no board token this book recognises and no board was
contacted.

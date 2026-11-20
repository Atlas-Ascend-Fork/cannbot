```
ID:        0466-a-feature-that-adds-or-removes-a-tbuf-needs-its-own-compile-target-because-a-runtime-skip-cannot-undo-a-layout-shift
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:404-418 —
           "**判定标准**(通用规则见 `development-guide §6 性能调优纪律`): /
           | 改动**会**引入 / 删除 TBuf 成员或改变片上 buffer slot 数 | **必须**编译宏分离独立 target | /
           | 改动只是数值参数变化 | 运行期 if(或 Tiling 透传)| /
           **理由**:TBuf 成员存在性本身影响编译器 UB 布局,运行期跳过 InitBuffer 不能避免布局漂移。 /
           **FA 类常见编译宏分离场景**: / - `dtype`(fp16 / bf16):影响 typedef 与 Mmad 模板参数同型链,
           **必须**编译宏分离 / - `causal` on / off:影响 causal mask TBuf 是否声明,**必须**编译宏分离 /
           - `sparse` on / off:同上(若涉及 TBuf 变化) / 按 overview §4.3 列出的特性笛卡尔积组合,
           各自一个 target。"
SOURCE:    same shelf, overview.md:225 — "此清单决定 design.md §6 编译宏分类(哪些必须编译宏分离独立
           target)与 §1.6 校验门禁规划(每个组合需要的 atol)" ; design.md:392 — "> 紧贴 §4 内存划分——
           编译宏判定标准的核心依据是"该特性是否引入 / 删除 TBuf 成员或改变片上 buffer slot 数"。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a FlashAttention build on a named 950 board in which a `causal`-mask `TBuf` is declared but
           its `InitBuffer` skipped at runtime, whose non-causal path's UB offsets and output are
           byte-identical to a build compiled without the declaration — the layout drift would then
           not occur, and the compile-macro rule would be a build-hygiene preference rather than a
           correctness requirement. Equally: a measured offset difference between the two builds is
           the observation this entry predicts, and its size is the number the entry lacks.
```

# 0466 · A feature that adds or removes a TBuf needs its own compile target, because a runtime skip cannot undo a layout shift

## 1 · Claim
Upstream asserts a two-way test for every optional feature of a FlashAttention operator: if enabling or
disabling it introduces or removes a `TBuf` member, or changes the number of on-chip buffer slots, the
feature must be separated into its own compile target behind a macro; if it only changes a numeric
parameter, a runtime `if` or a value passed through tiling is sufficient. Upstream asserts the reason:
the *existence* of a `TBuf` member itself affects the compiler's UB layout, so skipping `InitBuffer` at
runtime does not avoid layout drift. Upstream asserts three common cases for this family — dtype
(fp16 versus bf16, because the typedefs and the Mmad template's same-type chain change), `causal` on
or off (because a mask `TBuf` is or is not declared), and `sparse` on or off where a `TBuf` changes —
and asserts that the enumerated feature combinations from the analysis phase each get a target. Not
established here.

## 2 · The wrong branch this removes
Without this entry an agent handles optional features the way optional features are normally handled:
one binary, a flag in the tiling data, and an `if` in the kernel. That is the right answer for most
parameters and it is cheaper on every axis — one target to build, one to test, one to ship, and no
combinatorial explosion of binaries. The specific failure it produces is not "the disabled feature
runs"; it is that the *enabled* and *disabled* paths of the same binary see different UB layouts than
they would have had, because the declaration is what the compiler lays out, and the runtime branch
comes too late to matter.

The normal checks do not catch it because both paths are self-consistent. The kernel with a declared,
uninitialised mask `TBuf` still allocates the space; every other buffer sits at a different offset than
it would in a build without it; and the operator is correct — merely with less UB available and a
layout the design did not compute. The failure surfaces when the UB budget is tight, which is exactly
the regime this family is in (`0456`, `0458`), and it surfaces as an overrun whose cause is a feature
that was switched *off*.

The second wrong branch is the opposite over-correction: separating everything. Upstream's test is
specifically about `TBuf` membership and slot counts, and a Cartesian product over every feature is
what the analysis phase's enumeration produces (`overview.md:223`, `特性维度笛卡尔积清单`). A target
per combination of dtype × causal × sparse × quantisation is already eight or more binaries; adding
the numeric parameters would make it unbuildable. The test exists to keep the product small, not to
justify it.

## 3 · Ground / Source
The test, its reason and its cases, `references/flashattention/design.md:400-418`:

```
### §5.2 编译宏 vs 运行期 if 判定标准

回答:**每个条件性功能用编译宏分离独立 target,还是运行期 if 跳过?**

**判定标准**(通用规则见 `development-guide §6 性能调优纪律`):

| 条件 | 处理 |
|---|---|
| 改动**会**引入 / 删除 TBuf 成员或改变片上 buffer slot 数 | **必须**编译宏分离独立 target |
| 改动只是数值参数变化 | 运行期 if(或 Tiling 透传)|

**理由**:TBuf 成员存在性本身影响编译器 UB 布局,运行期跳过 InitBuffer 不能避免布局漂移。

**FA 类常见编译宏分离场景**:
- `dtype`(fp16 / bf16):影响 typedef 与 Mmad 模板参数同型链,**必须**编译宏分离
- `causal` on / off:影响 causal mask TBuf 是否声明,**必须**编译宏分离
- `sparse` on / off:同上(若涉及 TBuf 变化)

按 overview §4.3 列出的特性笛卡尔积组合,各自一个 target。
```

The reason sentence is the whole entry, and it is worth being precise about what it claims and what it
does not. It claims that `TBuf` member *existence* affects the compiler's UB layout. It does not claim
the layout is wrong, or that the operator misbehaves — it claims a **drift**, a difference between the
layout the design computed and the layout the compiler produced. Whether that difference is
consequential depends on how close the design's UB budget is to capacity, which upstream does not
discuss here and which its own §4.1 Q3 check (`Σ 单槽容量 × depth ≤ GetCoreMemSize(UB)`) computes from
the design's list rather than from the compiler's layout. So the two checks are computed from different
inputs and upstream never reconciles them. Recorded as `Q-950fin-16`.

Note also that the three named cases are not three instances of one mechanism. `causal` and `sparse`
are `TBuf`-membership cases, which is what the test is about. `dtype` is not: fp16 versus bf16 changes
typedefs and the Mmad template's same-type chain (`0460`), which is a *type* separation, not a buffer
one — and a type change in Ascend C is a template parameter, which cannot be a runtime `if` at all. So
the dtype row is filed under a test it does not need, and the reason given for it is a different reason
from the one the test states. Recorded as `C-950fin-012`.

The rule's placement is stated deliberately, `:392`: `紧贴 §4 内存划分——编译宏判定标准的核心依据是
"该特性是否引入 / 删除 TBuf 成员或改变片上 buffer slot 数"`. So the build-system decision is derived
from the memory division, not from the feature list — which is the ordering the design dependency chain
at `:26-42` also gives (`§4 内存划分 → §5 编译宏`). This is one of the few places in the corpus where a
toolchain decision is explicitly downstream of a memory decision.

The other end of the chain is the acceptance side, `overview.md:225`:

```
此清单决定 design.md §6 编译宏分类(哪些必须编译宏分离独立 target)与 §1.6 校验门禁规划(每个组合需要的 atol)
```

— so each target also carries its own tolerance. **Both section numbers in that sentence are wrong.**
Compile-macro classification is `design.md` **§5** (`design.md:390`, `## §5 编译宏分类:必须回答的问题`);
its §6 is Host Tiling decisions (`:424`). And `§1.6` does not exist: `design.md`'s §1 is a nine-row
must-produce table, whose row 9 is the precision gate and whose pointer is `见 overview §4.4` — back to
the file that made the reference. One sentence, one repository, two bad pointers, one of them
circular. Recorded as `C-950fin-013`, the same dangling-reference species the scan shelf carries three
of (`0487`).

Two files, one repository: one origin (RULES.md Art. 3). The `development-guide §6` it defers to for the
general rule is a plugin document in the same repository and adds no origin.

## 4 · Procedure
Proposed, runnable later; the decisive arm needs a compiler but no device, and is still not run in this
phase because it contacts the toolchain rather than reading a file. The confirming arm needs a named
950 board (950PR or 950DT).

**Arm 1 — the layout drift, which is the claim (compile-only).** Three builds of one GQA kernel for a
DAV_3510 target under a stated toolkit pin: (a) causal mask `TBuf` not declared; (b) declared and
`InitBuffer` called; (c) declared and `InitBuffer` skipped at runtime — upstream's forbidden form.
Extract every buffer's UB offset and size from the build artifacts (map file or the kernel's own echo
of `GetTBufAddr`-equivalent addresses) and diff (a) against (c). Upstream's claim is that they differ.
Report the offsets, not a boolean: *which* buffers moved and by how much is what tells a designer
whether the drift is consequential.

**Arm 2 — the consequence, on device.** Take the design's UB budget to within one chunk of capacity
(the regime `0456` and `0458` describe), then run (a) and (c) on the non-causal path across the shape
sweep. Report elementwise agreement and the echoed total occupancy for each. If (c) overruns where (a)
does not, the drift is consequential at a measured margin, which is the number `Q-950fin-16` asks for.

**Arm 3 — the dtype row.** Attempt a single-target build carrying both fp16 and bf16 paths behind a
runtime `if`, per `C-950fin-012`. The prediction from §3 is that it fails to compile for a reason that
has nothing to do with UB layout — the Mmad template's same-type chain (`0460`). Record the verbatim
diagnostic. If it compiles, the dtype row belongs under the test after all and §3's reading is wrong.

**Arm 4 — the slot-count half, retained because it may not bite.** A feature that changes a buffer's
`depth` rather than its existence, switched at runtime. Upstream's test covers `改变片上 buffer slot
数` alongside member existence; this arm is the only one that tests that half separately. If runtime
slot-count changes produce no drift, the test's second clause is unnecessary here.

Refuses to assume: that a free die stays free, or that a die may be substituted; that "the layout
differs" implies "the operator is wrong" (arms 1 and 2 are separate for that reason); that the design's
UB sum and the compiler's layout are the same quantity (`Q-950fin-16` exists because they may not be);
that a compile failure means what its message says (`0460`); that `TBuf` addresses reported by the host
are the addresses the kernel sees — every offset is echoed from the device where possible.

## 5 · Checker — acceptance declared before the run
Verdict `layout_delta = { buffer : offset_a(buffer) ≠ offset_c(buffer) }` from arm 1, declared before
the run as a *set with magnitudes*, not a boolean. Acceptance for the reason upstream gives:
`layout_delta` is non-empty. The OVERTURN fires iff `layout_delta` is empty — a declared-but-uninitialised
`TBuf` would then cost nothing in layout, and the rule would be hygiene rather than correctness.

Verdict `overrun_margin` from arm 2: the smallest UB headroom at which (c) disagrees and (a) agrees,
`+∞` if (c) never disagrees.

Verdict `dtype_needs_macro_for_layout_reason` from arm 3 ∈ {`yes`, `no`, `fails_for_type_reason`}, the
third value being §3's prediction and `C-950fin-012`'s resolution.

The exit code is not the verdict: build (c) compiles, runs and produces correct output in the regime
where UB is not tight, which is the regime a test suite uses. Guards: (1) arm 1 fails red if any
buffer's offset could not be extracted — a layout diff over the subset of buffers the tooling happened
to report is the blind-checker species and would show an empty delta for the wrong reason; (2) **the
input that makes this checker go red**: builds (a) and (b) diffed against each other, which *must*
differ, since (b) genuinely has an extra initialised buffer — if that diff is empty, the extraction is
not seeing the layout at all and arm 1's result is meaningless; (3) no offset is reported without its
build id, its macro set, the toolkit pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no compiler was invoked.
The two-way test, the reason, the three named cases, the Cartesian-product instruction, the placement
statement and the tolerance-per-combination line are file reads performed at drafting time. The
observations that the dtype case is a type separation rather than a buffer one, that the design's UB
sum and the compiler's layout are computed from different inputs, and that both section pointers in
`overview.md:225` miss their targets, are readings of upstream's own lines, not observations of a
build. The two section numbers were checked against the headings actually present in `design.md`
(`:390` for §5, `:424` for §6, `:8` for §1) at drafting time.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish that a declared-but-uninitialised
`TBuf` shifts the layout — upstream asserts it as the reason for a rule and shows nothing. It does not
establish that any such shift matters; the magnitude is unstated and `Q-950fin-16` records that the
design's own UB check would not see it. It does not establish that the dtype case belongs under this
test (`C-950fin-012`), nor repair the two bad section pointers (`C-950fin-013`). It does not establish
the three named cases as the complete set for this family, nor say what to do when the Cartesian
product becomes unbuildable — upstream instructs one target per combination and never bounds the count.
It does not cover the slot-count half of the test with any example. It says nothing about compile-macro
policy for any other operator family. No board token appears in any quoted passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT and a DAV_3510 compile target only as where our run
would happen. Nothing here is established for any 910-family board.

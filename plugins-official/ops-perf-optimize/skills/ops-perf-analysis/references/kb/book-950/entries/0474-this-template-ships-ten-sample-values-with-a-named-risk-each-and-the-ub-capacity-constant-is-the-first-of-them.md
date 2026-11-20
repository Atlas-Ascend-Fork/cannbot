```
ID:        0474-this-template-ships-ten-sample-values-with-a-named-risk-each-and-the-ub-capacity-constant-is-the-first-of-them
LABEL:     procedure
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/matmul-fusion-design-template.md:382-395 —
           "### 5.3 [SAMPLE] 重评清单 / | 编号 | 样例项 | 风险 | 处理要求 | /
           | S1 | `UB_SIZE` | 不同芯片 UB 容量不同 | 按目标芯片重定义 | /
           | S2 | `using DataType = float` | dtype 迁移后链路不一致 | 同步修改 alias 与 `sizeof` | /
           | S4 | `ALIGN_ELEM = 32/sizeof(float)` | dtype 改变后对齐错误 | 改为 `sizeof(DataType)` | /
           | S7 | batch=1 假设 | 批量场景不成立 | 超范围场景单独扩展 | /
           | S8 | RowMajor 假设 | 布局变更导致偏移错误 | 保持 RowMajor 或全链路调整 |"
SOURCE:    same file:8-10 — "> 标注约定： / > `[PATTERN]` 固定结构禁改；`[USER]` 按算子语义填写；
           `[SAMPLE]` 样例需重评； / > `[MODIFY]` 必改点；`[EXTEND]` 扩展点；`[CONFIG]` 配置点。" ;
           :369 — "- [ ] `[SAMPLE]` 项已按 §5.3 [SAMPLE] 重评清单 逐项评估" ;
           :342 — "│       ├── hardware_constants.h            # [PATTERN]+[SAMPLE] UB_SIZE 等"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a fused matmul operator delivered on a named 950 board whose `[SAMPLE]` items were carried
           over unchanged from the reference project and which is nevertheless correct across a sweep
           covering a different chip, a different dtype and a batched shape — the register's risks
           would then be hypothetical for that migration, and the re-evaluation would cost nothing.
           Equally: any single `[SAMPLE]` item whose unchanged value produces a wrong result is a
           demonstration the register is load-bearing, and its symptom is what upstream does not give.
```

# 0474 · This template ships ten sample values with a named risk each, and the UB capacity constant is the first of them

## 1 · Claim
Upstream asserts a six-level annotation scheme for its matmul fusion design template — `[PATTERN]`
fixed structure that must not be changed, `[USER]` filled per operator semantics, `[SAMPLE]` example
values requiring re-evaluation, `[MODIFY]` mandatory change points, `[EXTEND]` extension points,
`[CONFIG]` configuration points — and asserts a ten-row register enumerating every `[SAMPLE]` value in
the reference project with, per row, the value, the risk of carrying it over, and the required action.
Upstream asserts that `UB_SIZE` is the first of those rows, with the risk stated as "different chips
have different UB capacity" and the action "redefine for the target chip", and asserts that the
constant lives in a header annotated `[PATTERN]+[SAMPLE]`. Upstream asserts a pre-review checklist item
requiring every `[SAMPLE]` row to have been evaluated. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent starting from a reference project does what reference projects invite:
change the epilogue and ship. The template's whole design is aimed at that instinct — it separates
what must not change (`[PATTERN]`) from what must (`[MODIFY]`) from what merely *looks* like a
constant but is a sample of one case (`[SAMPLE]`). The third category is the one without a compiler
error attached. `using DataType = float` compiles at any dtype the operator does not use; `batch = 1`
compiles for any batch; `UB_SIZE` compiles on any chip.

The specific wrong branch this book cares about is S1. This corpus has spent nine contradiction rows on
hardware constants copied without scope: C-003 records a chip-agnostic capacity table matching neither
architecture, C-004 an intra-skill disagreement about UB on 950, C-006 four different UB defaults
across one script subtree with none chip-scoped, C-007 five different core counts. **This register is
the only place in the corpus that treats a UB constant as a re-evaluation risk rather than as a
number.** It does not say what the value should be — it says the value is a property of the target chip
and must be set from it. That is the discipline the other nine rows record being absent.

The second wrong branch is treating the register as a checklist to be ticked. `逐项评估` — evaluate
each item — is the checklist's wording, and the register gives per-row *actions* rather than per-row
*checks*. Nothing verifies that the action was taken. This is the same shape as the PipeBarrier
redundancy accounting (`0464`): a marker the implementer can satisfy by asserting it. Recorded as
`Q-950fin-23`.

## 3 · Ground / Source
The annotation scheme, `matmul-fusion-design-template.md:8-10`:

```
> 标注约定：
> `[PATTERN]` 固定结构禁改；`[USER]` 按算子语义填写；`[SAMPLE]` 样例需重评；
> `[MODIFY]` 必改点；`[EXTEND]` 扩展点；`[CONFIG]` 配置点。
```

Six levels, of which `[SAMPLE]` is the only one that describes a *hazard* rather than an obligation:
the others say what to do with a region, this one says the value in it is one case's value. Note the
combination `[PATTERN]+[SAMPLE]` on the hardware constants header (`:342`,
`hardware_constants.h # [PATTERN]+[SAMPLE] UB_SIZE 等`) — the file's structure must not be changed and
its values must be re-evaluated, which is a precise and unusual thing to say about a constants header.

The register, `:382-395`:

```
| 编号 | 样例项 | 风险 | 处理要求 |
|------|--------|------|---------|
| S1 | `UB_SIZE` | 不同芯片 UB 容量不同 | 按目标芯片重定义 |
| S2 | `using DataType = float` | dtype 迁移后链路不一致 | 同步修改 alias 与 `sizeof` |
| S3 | `stageNum = 2` | 输入路数变化导致布局错配 | 按 1/2/3 路重设 |
| S4 | `ALIGN_ELEM = 32/sizeof(float)` | dtype 改变后对齐错误 | 改为 `sizeof(DataType)` |
| S5 | `rowBytes = ... * sizeof(float)` | stride 字节数错误 | 按输出 dtype 重算 |
| S6 | `divisor*` 命名 | 语义漂移 | 按业务重命名 |
| S7 | batch=1 假设 | 批量场景不成立 | 超范围场景单独扩展 |
| S8 | RowMajor 假设 | 布局变更导致偏移错误 | 保持 RowMajor 或全链路调整 |
| S9 | `sizeD = m*n*sizeof(...)` | 广播输入 shape 不匹配 | 同步改 Host 与 Epilogue |
| S10 | `input_d.bin` 文件名 | 语义不匹配 | 按算子语义改名并同步脚本 |
```

Ten rows, and they are not ten of a kind. Four (S2, S4, S5, S9) are one hazard in four places: a
`sizeof` or a shape written for the sample's dtype. Two (S7, S8) are unstated *assumptions* rather than
values — `batch=1` and RowMajor are not constants in the code, they are properties the code relies on,
and S8's action is honest about the cost (`保持 RowMajor 或全链路调整`, keep it or change the whole
chain). Two (S6, S10) are naming, whose stated risk is semantic drift rather than wrongness. S1 is
hardware. S3 is a partition count (`0473`).

Three of the rows are already this book's subjects from other directions: S1 against C-003/C-004/C-006
and against `0472`'s `TOTAL_UB_SIZE`; S3 at `0473`; S4 and S5 at `0471`, where the same `ALIGN_ELEM`
appears as a literal 8 in the twin file. That overlap is the register working — it names, in advance,
four of the places this book found problems by reading.

What the register does not carry is a symptom for any row. Every "风险" is a category (`不一致`,
`错配`, `错误`, `不成立`, `漂移`) and none is an observable. So a reviewer cannot use the register to
decide whether an action was taken; only to ask. Recorded with `Q-950fin-23`.

The pre-review checklist item, `:369`: `- [ ] `[SAMPLE]` 项已按 §5.3 [SAMPLE] 重评清单 逐项评估`.

One file; with `patterns.md`'s references to `[SAMPLE] S1` (`:109`), two files in one repository — one
origin (RULES.md Art. 3).

## 4 · Procedure
This entry is about a template's structure and a migration discipline. Its verification is partly a
document procedure and partly a device procedure; neither is run here.

**Arm 1 — the register's coverage, mechanically (no device).** A script that greps the reference
project named in the template (`references/matmul_fusion_kernel/`, in the sibling skill) for every
occurrence of `[SAMPLE]` and for every literal that the register's ten rows name, and reports: rows
with no corresponding site in the code, sites annotated `[SAMPLE]` with no register row, and literals
matching a row's pattern at sites the register does not list. A register that misses a site is the
failure mode a checklist cannot catch.

**Arm 2 — one row, made real (device).** Take S1. Build the fusion twice on a named 950 board: once
with `UB_SIZE` at the reference project's value, once at the value queried from
`GetCoreMemSize(CoreMemType::UB)` on this board. Echo both. Report whether the two differ, and if they
do, whether the unchanged build overruns (sentinel past the computed budget, per `0472`) or merely
under-uses UB. This turns S1's risk category into an observation on this hardware, which is what the
register does not have.

**Arm 3 — the four `sizeof` rows together (device).** Migrate `DataType` to `half` and run four
builds: all four of S2/S4/S5/S9 applied, and each one omitted in turn. Report correctness per build.
The prediction is that the four are not independent — S4's `ALIGN_ELEM` feeds S5's `rowBytes`
(`0471`) — so omitting one may be masked by another, which is exactly why a per-row checklist is weak.

**Arm 4 — the assumption rows, retained because they may not bite (device).** Run the reference build
at `batch > 1` (S7) and with a ColumnMajor output (S8). Report what fails and where. Upstream's action
for S7 is `超范围场景单独扩展` — extend separately for out-of-range scenarios — which concedes the
reference does not support it; this arm records what "does not support" means in practice.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `UB_SIZE` as
written equals the queried capacity (arm 2 echoes both, and this corpus records four incompatible
values for the constant, C-006); that the ten rows are the complete set of sample values (arm 1 tests
that); that the rows are independent (arm 3 is built on the expectation that they are not); that an
unchanged sample value fails loudly.

## 5 · Checker — acceptance declared before the run
Verdict `register_complete` from arm 1: `true` iff all three reported sets are empty. Declared before
the run; a non-empty "sites with no row" set is the register's own gap and is the most useful possible
outcome.

Verdict `ub_size_matches_hardware` from arm 2, boolean, with both values reported; and
`unchanged_build_outcome` ∈ {`overrun`, `under_uses`, `identical`}.

Verdict `sizeof_rows_independent` from arm 3: `true` iff each single omission produces a wrong result.
A `false` — some omission masked by another row — is declared now as the expected outcome and is a
finding about the checklist form, not about any row.

Verdict `assumption_failure_mode(S7)`, `(S8)` from arm 4, each ∈ {`fault`, `wrong_values`, `correct`}.

The exit code is not the verdict: an unchanged `[SAMPLE]` value compiles, runs and, in the reference's
own configuration, is right. Guards: (1) arm 1's script fails red if it found zero `[SAMPLE]`
annotations or fewer than ten register rows — a grep that matched nothing would report empty sets,
which is the blind-checker species, and the ten rows are the positive fixture it must find; (2) **the
input that makes this checker go red**: arm 2 run with `UB_SIZE` set deliberately to twice the queried
capacity, which must overrun — if it does not, the harness's overrun detector is not working and the
`identical` outcome carries no information; (3) no build is reported without its `[SAMPLE]` value set,
the queried UB capacity, `DataType`, the CANN pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The six-level annotation
scheme, the ten register rows with their risks and actions, the `[PATTERN]+[SAMPLE]` header annotation
and the pre-review checklist item are file reads performed at drafting time. The observations that the
ten rows are four kinds rather than ten of a kind, that four of them are one `sizeof` hazard in four
places, that two are assumptions rather than values, and that no row carries an observable symptom, are
readings of upstream's own table, not observations of any build or migration.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or migrated. The entry does not establish that any `[SAMPLE]` value
carried over unchanged causes a failure — every "risk" in the register is a category and none is a
readout. It does not establish `UB_SIZE`'s correct value on any board; the register says to set it from
the target chip and this book's own UB constants are contested across four contradiction rows
(C-003, C-004, C-006, and `0472`'s `TOTAL_UB_SIZE`). It does not establish that the register is
complete (`Q-950fin-23` records that nothing verifies the actions were taken; arm 1 records that
nothing verifies the rows cover the code). It does not evaluate the reference project itself, which is
in a sibling skill this wave did not mine. It covers the mxfp8 + eltwise fusion template only
(`0469`); the annotation scheme is this template's and no other document in this corpus uses it. No
board token appears in any quoted passage, so BOARD is `family-claimed(unverified)`; §4 names
950PR/950DT only as where our run would happen. Nothing here is established for any 910-family board.

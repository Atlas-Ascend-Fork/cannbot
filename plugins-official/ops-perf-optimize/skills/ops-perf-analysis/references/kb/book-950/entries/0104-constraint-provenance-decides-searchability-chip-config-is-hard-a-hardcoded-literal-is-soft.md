```
ID:        0104-constraint-provenance-decides-searchability-chip-config-is-hard-a-hardcoded-literal-is-soft
LABEL:     knowledge
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/parameter-analysis.md:46-53 —
           "- 来自芯片规格配置（buffer 容量、核数、对齐粒度）→ **硬件约束**，不可放松
            - 来自硬编码字面量 → **软件经验值**，可纳入搜索
            判定方法：沿赋值链追溯到原始定义——是平台配置字段还是常数。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured case on a named 950 board where a value the provenance rule classifies as a
           software 经验值 (traced to a hardcoded literal) is exceeded and the kernel produces
           wrong results or fails to launch — that would make the literal a hardware constraint
           the trace-to-definition method mis-classified.
```

# 0104 · Constraint provenance decides searchability: a chip-config field is hard, a hardcoded literal is soft

## 1 · Claim
Upstream asserts a classification rule for every range limit on every tiling parameter: trace the
limit along its assignment chain to its original definition, and if that definition is a chip
specification field (buffer capacity, core count, alignment granularity) the limit is a hardware
constraint that may not be relaxed, whereas if the definition is a hardcoded literal the limit is
a software 经验值 (empirical value) that may be admitted into the search space. Upstream states
the discriminating method explicitly — follow the assignment chain to the original definition and
ask whether it is a platform configuration field or a constant. Not established here.

## 2 · The wrong branch this removes
This is the single most transferable rule in the whole tiling reference set, and without it a
harness agent does one of two symmetric wrong things. Either it treats every number it finds in a
tiling script as inviolable — in which case the search space is bounded by whatever a previous
engineer happened to type, and the best plan is unreachable by construction; or it treats every
number as tunable — in which case it proposes a plan that exceeds a real capacity and gets a
wrong-result or launch failure that looks like a code bug. Neither failure is caught by normal
checks, because both produce a schema-valid tiling and a kernel that builds. The rule converts an
unanswerable question ("is 4 a real limit?") into a mechanical one ("where was 4 assigned?").

The rule is load-bearing for the rest of this block. This same subtree contains four incompatible
UB literals and five incompatible `coreNum` literals (recorded upstream-wide as C-006 and C-007 in
`harvest/CONTRADICTIONS.md`), a `stepK` upper bound stated as five different things (0109), and a
StreamK entry gate stated one way and computed another (0108). Under this rule every one of those
is a literal with no chip-config pedigree — i.e. a software 经验值 that a search may cross —
rather than an architectural boundary. That is a large consequence to hang on one paragraph, which
is why it is entered as its own claim with its own overturn condition.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/parameter-analysis.md:32-53`, §2 in full:

```
## §2 参数分类与约束追溯

对 §1 中每个参数做两件事：

### 类型判定

| 类型 | 判定 | 搜索行为 |
|------|------|---------|
| 固定输入 | 直接来自用户指定的问题规模 | 不搜索 |
| 独立可调 | 存在搜索/选择逻辑，有多合法值 | 搜索维度 |
| 派生 | 由其他参数公式计算 | 随独立变量自动计算 |

### 约束来源追溯

对每个参数的每个取值范围限制，追溯定义来源：

- 来自芯片规格配置（buffer 容量、核数、对齐粒度）→ **硬件约束**，不可放松
- 来自硬编码字面量 → **软件经验值**，可纳入搜索

判定方法：沿赋值链追溯到原始定义——是平台配置字段还是常数。

输出：分类表 + 约束来源表 + 被软件截断的参数列表（标注截断值和硬件上限）。
```

Two independent readers' surveys of this repo both named this passage the single best reusable
rule in the skill; the earlier of them cited it as `:47-50`, and re-verification against the file
puts the two-bullet rule at `:48-49` and the method sentence at `:51`. The drift is one line and
changes nothing, but it is recorded because a survey is one contact and its line numbers are the
part most likely to have moved.

The same file's §4 (`:65-73`) states the operational consequence — candidates are enumerated over
the hardware-limited range at hardware alignment step, `不受软件截断值限制` — which this book
carries as its own claim, 0106.

Upstream applies its own rule inconsistently: `sort/topk_host_tiling.md:81` obtains UB capacity by
runtime query (`GetCoreMemSize(CoreMemType::UB)`, see 0141), which is the chip-config side of the
rule done correctly, while six scripts in the same subtree hardcode `248 * 1024`. The rule is
stated once, in a file the family flows do not link to as required reading.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The rule
is a classification method, so the procedure tests its output, not the sentence: it takes limits
the rule classifies as *soft* and tries to break the kernel by crossing them.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after the run and
discard the case if the die moved.

Step 1 — build the provenance table for one family end to end. Take `matmul/fallback/` and, for
each parameter in `tiling-fields.md`, trace every stated limit to its definition site in the
upstream text and in the tiling script that owns it. Classify by the rule. Expect: `stepK ≤ 4`
soft (literal, and stated four other ways — 0109), `STEPKA_THRESHOLD = 4` soft (a named constant
in a table), L1 capacity hard (chip config), 512 B alignment hard (alignment granularity).

Step 2 — cross each soft limit, one at a time, on a real case. For `stepK`: build the same shape
at `stepK ∈ {1, 2, 3, 4, 8}` (3 and 8 are the values the five contradictory statements disagree
about) and record for each whether the kernel builds, whether outputs match the fp64 reference
within the operator's declared tolerance, and its `aic_time`. For each hard limit, cross it once
in a throwaway build and record the failure mode — the hard/soft distinction is only meaningful if
the hard side actually fails.

Refuses to assume: that a die free before the run stayed free; that a die may be substituted; that
a limit which holds at one shape holds at all shapes (each crossing is per-case, no representative
sampling); that "builds and runs" implies "correct" — every crossing carries a numeric comparison.

## 5 · Checker — acceptance declared before the run
Verdict variable `soft_survives`, a boolean per crossed soft limit: true iff the build succeeds
AND the output matches the reference within the declared tolerance AND the host echo confirms the
requested value was actually used. Declared acceptance: the rule survives iff `soft_survives` is
true for every limit it classified as soft, and false for every limit it classified as hard.
Declared falsification: any soft-classified limit whose crossing produces wrong results or a
launch failure — that is a mis-classification and kills this entry as written.

The exit code is not the verdict. A kernel that silently clamps `stepK` back to a legal value
exits 0 and produces correct output, which would score as `soft_survives = true` for a limit that
was never actually crossed. The host-echo requirement is what makes that visible: the checker
fails red when the requested and echoed values differ, so "the limit could not be crossed" is
distinguished from "the limit was crossed and nothing broke". Without that guard this checker
would be the read-only-what-it-expects species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no board was touched; no limit was crossed. The entry does not establish
that any particular upstream number is soft — it establishes only that upstream states a method
for deciding, and this book's other entries apply that method to name candidates. It does not
establish that a platform configuration field is itself correct: upstream's own truth-source skill
warns that `ini 文件是发现硬件参数的必要不充分条件`, so "traced to chip config" means "traced to a
better-pedigreed number", not "measured". The chip is unstated in `parameter-analysis.md` — the
file names no board and no arch — so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT
because that is where our future run would happen, not because upstream measured there. Nothing
here is established for any 910-family board, and the rule's transfer to that family is not
claimed.

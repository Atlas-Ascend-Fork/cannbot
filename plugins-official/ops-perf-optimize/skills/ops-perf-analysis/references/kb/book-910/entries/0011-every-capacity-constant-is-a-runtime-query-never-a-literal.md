```
ID:        0011-every-capacity-constant-is-a-runtime-query-never-a-literal
LABEL:     procedure
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin, which states the rule three times in three files; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:116 — "**运行时始终以该接口返回值分块**，禁止硬编码"; ibid:39 — "即便以上参数通常一致，代码中仍应通过 `GetCoreMemSize` 获取，避免硬编码"; ibid:126 — "算子代码**必须通过 `PlatformAscendC` 接口运行时获取**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a capacity accessor (`GetCoreMemSize`, `GetCoreNumAic/Aiv`) is shown to return a value that disagrees with the hardware it runs on, making the literal the more reliable source. Alternatively: no accessor exists for a capacity a tiling decision needs.
```

# 0011 · Every capacity constant is a runtime query, never a literal

## 1 · Claim
Upstream asserts that hardware capacities must be obtained at runtime through the
`PlatformAscendC` interfaces — `GetCoreMemSize(CoreMemType::…)` for buffer capacities,
`GetCoreNumAic()` / `GetCoreNumAiv()` for core counts — and that hardcoding them is prohibited.
Upstream states this rule even for the parameters it has just declared constant across every
architecture. Not established here.

## 2 · The wrong branch this removes
This entry exists to remove a whole class rather than one instance. Without it a competent agent
does the reasonable thing: it looks up the right number for the target part, writes it as a named
constant with a comment, and moves on. That is defensible engineering and it is wrong here for a
reason the agent cannot see locally — the identifiers that would let it detect a mismatch have
collapsed (0001, 0002), the counts genuinely differ within one arch (0009), and one of the
capacities is upstream-contradicted at 6× (0007). A literal is a silent assertion that the part
under the code is the part in the developer's head, and on this family that assertion has no
checkable basis.

The normal checks do not catch it because a hardcoded constant makes the code MORE deterministic,
not less: tests pass, results are reproducible, and the tiling arithmetic is self-consistent. The
defect only appears on a part nobody in the loop has.

The specific downstream symptom to watch for: a capacity literal that is *correct* today is an
artefact that outlives the reasoning that justified it. The next sub-model ships and the literal
is still there, still commented, still wrong.

## 3 · Ground / Source
Upstream states the rule three times, in three registers, all in
`ops/npu-arch/references/npu-hardware-params.md`:

- line 39, after the cross-architecture-constant table — "> **注意**：即便以上参数通常一致，代码中
  仍应通过 `GetCoreMemSize` 获取，避免硬编码。" (the strongest form: even the constants)
- line 116, after the per-arch buffer tables — "> **关于 UB 容量**：表内值为 INI `ub_size` 字段，
  即 `GetCoreMemSize(CoreMemType::UB, ...)` 返回的用户可用容量。**运行时始终以该接口返回值分块**，
  禁止硬编码。"
- line 126, in the varying-parameter section — "算子代码**必须通过 `PlatformAscendC` 接口运行时
  获取**。"

The accessor form is given at `ops/npu-arch/SKILL.md:24-30`:
```cpp
#include "utils/tiling/platform/platform_ascendc.h"
auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
NpuArch npuArch = ascendcPlatform.GetCurNpuArch();
platform_ascendc::SocVersion socVer = ascendcPlatform.GetSocVersion();
```
with documented failure returns at line 32 — `NpuArch::DAV_RESV` and
`SocVersion::RESERVED_VERSION`. A query that can fail needs a failure branch; a literal has none,
which is the one respect in which the literal is simpler and the reason the rule needs stating.

Same repo, one origin, at the level of practice: `ops/npu-arch/SKILL.md:36` — "> 详细硬件参数真值见
`references/npu-hardware-params.md`。运行时必须以 `PlatformAscendC` 接口获取实际值，禁止硬编码。"

The complete accessor set, `ops/npu-arch/references/npu-arch-guide.md:198-209` — seven capacities
and two core counts in one block, **including L2**:
```cpp
uint32_t aicNum = ascendcPlatform.GetCoreNumAic();
uint32_t aivNum = ascendcPlatform.GetCoreNumAiv();
uint64_t ubSize, l1Size, l0aSize, l0bSize, l0cSize, l2Size, btSize;
ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB,   ubSize);
... L1, L0_A, L0_B, L0_C, L2, BT ...
```
The same file at `:74` states its own standing in the repo: "> ⚠️ **核心原则**：本节作为 NPU 架构
知识在 skills 仓中的上游真源，下游 skill 应消费本节数据，**反向自引用即视为风险**。" — so a
downstream skill's hardcoded constant is not merely undisciplined, it is upstream-declared risk.

Contrast, showing the cost of not following it — every one of these is a hardcoded capacity that
upstream itself ships and that disagrees with a sibling: `harvest/CONTRADICTIONS.md` C-003 (a
chip-agnostic 256 KB UB matching no family), C-004, C-006 (four UB literals in one subtree) and
C-007 (five coreNum literals in one subtree). Those rows are 950-side or agnostic and are cited,
not re-filed; they are the evidence that this rule is violated in practice by its own authors.

## 4 · Procedure
Proposed, runnable later; not run. This entry's procedure is a lint, not a benchmark, and most of
it needs no card.

1. Static arm, no device: over any kernel or tiling source under review, flag every integer
   literal that equals a known capacity (196608, 192*1024, 524288, 131072, 65536, 1024, 24, 48,
   20, 40) or appears as an operand of a division by `sizeof(...)`. For each hit, require either a
   `GetCoreMemSize` / `GetCoreNum*` call reaching that expression, or a written justification.
2. Dynamic arm, on a named die (occupancy before and after, no substitution): run the same kernel
   under two parts with different counts (per 0009) and confirm the tiling output changes. A
   correctly-queried tiling changes; a hardcoded one does not.
3. The dynamic arm needs two physically different parts and is inconclusive with one. Record that
   rather than working around it.

## 5 · Checker — acceptance declared before the run
Verdict variable `unjustified_literals`, the count from arm 1.
PASS iff `unjustified_literals == 0`.
The checker's positive fixture — required by RULES.md Art. 5 and stated here so this file's own rule
applies to itself: a scratch source containing `constexpr uint32_t UB = 192 * 1024;` must be
FOUND. If the lint is run and reports zero on a file that contains that line, the lint is broken
and its result is void, regardless of what it says about the real sources. A lint that can only
confirm cleanliness is the known blind species; this one is required to bleed on a planted
positive before its clean verdicts count.
Note the literal must be caught in its `192 * 1024` form as well as `196608` — a matcher that
reads only the decimal spelling is the same blind species one level down.
Exit code is not the verdict: arm 1 exits non-zero on a parse error as well as on a finding.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. This entry does not establish that the accessors return
correct values — that is assumed by upstream and untested here, and the OVERTURN condition names
exactly that assumption. It does not establish that an accessor exists for every capacity a
decision needs, though for L2 one does — see the correction note below. It does not cover compile-time constants
that are genuinely architectural rather than capacity-shaped (the 32 B data block of 0021, the
255-repeat parameter cap of 0031); those are different kinds of number and this rule is not an
argument for querying them.

**Correction, 2026-08-24, by the drafting agent.** This section previously asserted that "L2 has no
accessor named in any source in scope, so for L2 the rule has no implementation and the entry's
advice is empty." **That was wrong.** `ops/npu-arch/references/npu-hardware-params.md` and
`ops/npu-arch/SKILL.md` — the two npu-arch files this entry was drafted from — do not name one, but
`ops/npu-arch/references/npu-arch-guide.md:208` does:
`ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::L2, l2Size);`. The error came from
building a negative claim ("no source names one") on a subset of a skill's files without reading the
rest — the same species this book records at 0051 and 0052: a conclusion drawn from the lines the
reader happened to open. The rule of 0011 therefore applies to L2 as fully as to UB, and 0007 §4 is
corrected in the same change. Recorded here rather than silently edited, per the phase-1 plan's
self-report requirement.

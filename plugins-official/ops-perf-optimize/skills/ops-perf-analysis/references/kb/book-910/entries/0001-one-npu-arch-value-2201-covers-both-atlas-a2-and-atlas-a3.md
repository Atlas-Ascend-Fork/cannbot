```
ID:        0001-one-npu-arch-value-2201-covers-both-atlas-a2-and-atlas-a3
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin (npu-arch, the repo's self-declared 真源); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:17-18 — "| Atlas A2 训练/推理 | ASCEND910B | DAV_2201 | 2201 | Ascend910B1~B4, Ascend910B2C |" and "| Atlas A3 训练/推理 | ASCEND910B | DAV_2201 | 2201 | Ascend910_93 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a compiled kernel on an Ascend910_93 part reports a `__NPU_ARCH__` value other than 2201, or `GetCurNpuArch()` returns something other than `NpuArch::DAV_2201`.
```

# 0001 · One `__NPU_ARCH__` value (2201) covers both Atlas A2 and Atlas A3

## 1 · Claim
Upstream asserts that the Atlas A2 product line (Ascend910B1–B4, Ascend910B2C) and the Atlas A3
product line (Ascend910_93) map to the *same* NpuArch `DAV_2201` and the same `__NPU_ARCH__`
compile macro value 2201. Upstream asserts the same table row for the SocVersion: both lines
report `ASCEND910B`. Not established here.

## 2 · The wrong branch this removes
A harness agent asked to "target A2" writes `#if defined(__NPU_ARCH__) && (__NPU_ARCH__ == 2201)`
and believes it has fenced A2 off from A3. It has not: the same branch compiles for Ascend910_93.
Every A2-specific tuning constant inside that fence silently applies to A3 parts as well. The
normal checks do not catch it because the code compiles, runs, and produces correct results —
only the *performance* assumption is misplaced, and only on hardware the developer never had.
The inverse error is equally available: an agent that finds `__NPU_ARCH__ == 2201` in a log
concludes it is on A2, when the part may be A3.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md` §0 产品映射表, lines 15-21, verbatim rows:

```
| Atlas A2 训练/推理 | ASCEND910B | DAV_2201 | 2201 | Ascend910B1~B4, Ascend910B2C |
| Atlas A3 训练/推理 | ASCEND910B | DAV_2201 | 2201 | Ascend910_93 |
```

The same file, line 23, states the one-to-many relation explicitly:
"**一对多关系**：一个 NpuArch 可对应多个 SocVersion / 芯片型号。例如 `DAV_2201` 对应
Ascend910B1~B4、Ascend910B2C、Ascend910_93。"

The file declares itself the shared truth source for the skill (line 11: "**本表为 SKILL.md 与
`npu-arch-guide.md` 共用的真源**"). `ops/npu-arch/SKILL.md:15` defines the derived form:
"**archXX** | 算子仓目录简写，取 DAV 编号前两位（如 DAV_3510 → arch35）" — so arch22 is
likewise A2+A3 together.

Corroboration is NOT available inside this repo: `ops/npu-arch/SKILL.md` restates the mapping but
is the same origin (RULES.md Art. 3, STRATA S2). A second origin would be the vendor's published CANN
documentation or an installed `platform_config/*.ini`, neither consulted here.

Consequence carried by 0002 (the SocVersion enum collapses the same way) and 0047 (upstream's own
most-measured 910 document refuses to carry A2 results to A3 — which only makes sense if the two
are materially different despite sharing 2201).

## 4 · Procedure
Proposed, runnable later; not run.

1. Device selection: name the die explicitly (`ASCEND_RT_VISIBLE_DEVICES=<n>`), do not accept a
   scheduler-assigned default, and record `npu-smi info` for that die before and after. The
   procedure refuses to assume that a second die of the "same" board answers for the first, and
   refuses to substitute a die if the named one is busy — it aborts instead.
2. On a part known from its purchase record to be Atlas A2 (e.g. Ascend910B2), compile a trivial
   kernel that stores `__NPU_ARCH__` into a GM word, plus a host-side print of
   `PlatformAscendC(...).GetCurNpuArch()` and `.GetSocVersion()`.
3. Repeat on a part known to be Atlas A3 (Ascend910_93).
4. Record all six values (macro, NpuArch, SocVersion) per part.

Both halves are required: a single-part run establishes nothing about the mapping being
*many-to-one*.

## 5 · Checker — acceptance declared before the run
Verdict variable `arch_collapses`, computed as
`(macro_A2 == macro_A3) && (npuarch_A2 == npuarch_A3)`.
PASS (claim upheld) iff `arch_collapses` is true AND both macro values equal 2201.
The process exit code is NOT the verdict: a kernel that fails to launch exits non-zero without
distinguishing "A3 reported a different arch" from "the toolchain is broken", so the verdict is
read from the recorded six values only.
This checker can go red: if the A3 part reports 2202, or `DAV_RESV` (the documented failure
return, `ops/npu-arch/SKILL.md:32`), `arch_collapses` is false and the claim is overturned. It
does not read only the lines it expects — it records all six values unconditionally and compares
afterwards, so an unexpected third value is captured rather than skipped.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
No board was touched; nothing here was measured. This entry does not establish that A2 and A3 are
*interchangeable* — only that upstream says one arch number names both, which is the opposite
concern. It does not establish what, if anything, DOES separate A2 from A3 at compile time or
runtime; upstream names no such discriminator, and this book poses that as an open question
(STANDING_QUESTIONS: "What separates Atlas A3 from Atlas A2 at build or runtime?"). It does not
cover Ascend910B2C or the individual B1/B3/B4 parts beyond their appearance in the quoted row.
The operator's term "910C" appears nowhere in this mapping table and is not used here.

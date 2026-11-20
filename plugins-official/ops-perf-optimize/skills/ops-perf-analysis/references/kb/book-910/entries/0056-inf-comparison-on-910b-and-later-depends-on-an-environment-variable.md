```
ID:        0056-inf-comparison-on-910b-and-later-depends-on-an-environment-variable
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-precision-standard/reference/special_cases.md:64-66 — "**Ascend910B及之后：** is_before_910a=True（INF_NAN_MODE_ENABLE=0）：inf不参与比较 / is_before_910a=False（INF_NAN_MODE_ENABLE=1）：要求inf输出一致"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a named 910B-family board is shown to produce identical inf behaviour with `INF_NAN_MODE_ENABLE` set to 0 and to 1.
```

# 0056 · Inf comparison on 910B and later depends on an environment variable

## 1 · Claim
Upstream asserts that on Ascend910B and later chips, whether infinities participate in precision
comparison is governed by the environment variable `INF_NAN_MODE_ENABLE`: with it set to 0, inf
values do not participate in the comparison; with it set to 1, inf outputs are required to match,
or to be closer to a higher-precision golden reference than the golden itself. Upstream asserts
that on Ascend910A and earlier, inf never participates. Not established here.

## 2 · The wrong branch this removes
An accuracy verdict that depends on an environment variable is a verdict that can differ between
two machines running identical code on identical hardware. An agent that validates a kernel on a
machine with `INF_NAN_MODE_ENABLE=0` and ships it to one with 1 has shipped something that was
never tested against the stricter rule — and the difference is invisible in the source, the build
and the kernel binary.

The direction of the surprise matters. Setting the variable to 1 makes the comparison *stricter*,
so the failure appears downstream of a passing validation. And it appears only for inputs that
produce infinities — overflow in an exponential, a division by zero, a large-magnitude
accumulation — which is exactly the input class a functional test suite is least likely to cover
and most likely to have deliberately excluded as an edge case.

The second branch is the parameter's name. The comparison helper takes `is_before_910a`, a boolean
about *chip generation*, which upstream then documents as being set by an *environment variable*
on 910B and later. So a parameter that reads as hardware configuration is really a mode selector,
and an agent reading the signature would set it from the SoC version — getting the wrong answer
whenever the environment disagrees with the chip.

## 3 · Ground / Source
`ops/ops-precision-standard/reference/special_cases.md`, lines 61-66, verbatim in full:
"**Ascend910A及之前：**
- inf不参与比较
**Ascend910B及之后：**
- is_before_910a=True（INF_NAN_MODE_ENABLE=0）：inf不参与比较
- is_before_910a=False（INF_NAN_MODE_ENABLE=1）：要求inf输出一致"

The call forms, lines 73-78:
```python
# Ascend910A及之前芯片,或910B+且INF_NAN_MODE_ENABLE=0
result = check_inf_nan_consistency(npu_output, golden_output, is_before_910a=True)
# Ascend910B+且INF_NAN_MODE_ENABLE=1
result = check_inf_nan_consistency(npu_output, golden_output, benchmark_output, is_before_910a=False)
```
Note the second form takes an additional `benchmark_output` argument — the stricter mode needs a
higher-precision reference that the looser mode does not, so switching modes is not a flag change
but a change in what the test harness must produce.

The commercial standard's version,
`ops/ops-precision-standard/reference/golden/COMMERCIAL_OPS_PRECISION_DOCS.md`, lines 732-733:
"* Ascend910A及之前的芯片，或者Ascend910B及之后的芯片配置环境变量**INF_NAN_MODE_ENABLE = 0**
（未开启inf模式）的场景下，inf的计算值不参与精度比较。
* Ascend910B及之后的芯片配置环境变量**INF_NAN_MODE_ENABLE = 1**（开启了inf模式）的场景下，要求
inf的输出情况一致，或者和更高精度的Golden相比，npu更加接近Golden值。"

Same repo, so one origin (STRATA S2) — though the second is a vendor-document transcription, which
would be an independent origin if the vendor document itself were consulted. It was not.

**Scoping note.** "Ascend910B及之后" is upstream's phrase. It is a generation boundary, not a
board and not an NpuArch — and per `ops/npu-arch/references/npu-hardware-params.md` §0 the
910B/910_93 family is DAV_2201 while "之后" would include DAV_3510, which is another book's
territory. This entry claims only the 910B side, and BOARD is `family-claimed(unverified)`.

The whole skill is 910B-scoped per the structural survey; this is the clearest 910-specific
semantic claim in it.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; record the part; occupancy before and after; no substitution.
2. Environment arm: run one kernel that deliberately produces infinities (a large `Exp`, a division
   by a zero denominator) twice, with `INF_NAN_MODE_ENABLE=0` and `=1`, changing nothing else —
   same binary, md5-confirmed, same input, same die.
3. Compare the raw device outputs bitwise between the two runs, BEFORE applying any comparison
   rule. This is the step that separates the two possible readings: does the variable change what
   the *hardware produces*, or only what the *checker accepts*? Upstream's text describes a
   comparison rule, but the variable's name suggests a hardware mode, and the two have completely
   different consequences.
4. Then apply `check_inf_nan_consistency` in both modes and record the verdicts.
5. Record the variable's value as read back from the environment inside the run, not as set — a
   variable that does not reach the runtime would make both arms identical for an uninteresting
   reason.

## 5 · Checker — acceptance declared before the run
Two verdicts, and separating them is the substance.
`outputs_differ`: whether the raw device outputs differ bitwise between the two environment
settings. No expectation is declared — this is the open question of §4 step 3, and declaring an
expectation would bias the reading.
`verdicts_differ`: whether `check_inf_nan_consistency` returns different results. The claim is
upheld iff true.
Gate: the readback in §4 step 5 must confirm the variable reached the runtime in both arms. If it
did not, both arms are the same run twice and no verdict is issued.
The positive fixture: inject a deliberately wrong inf into the NPU output and confirm
`check_inf_nan_consistency` in strict mode FINDS it. A checker that passes everything in strict
mode is not strict, and its agreement with loose mode would then be meaningless — this fixture is a
planted positive the instrument must find, not a clean case it must pass.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "Ascend910B及之后" is a generation phrase spanning at
least DAV_2201 and later architectures; this entry claims only the 910B side and no individual
board. It does not establish whether the variable changes hardware behaviour or only comparison
policy (§4 step 3 is built to find out). It does not establish the NaN half of the mode, despite
the variable's name covering both — upstream's quoted text discusses inf only. It does not
establish what the default value is on any installation, which is the practically decisive fact and
which no source in scope states. It says nothing about how the variable interacts with the
overflow behaviour of integer operations (0044).

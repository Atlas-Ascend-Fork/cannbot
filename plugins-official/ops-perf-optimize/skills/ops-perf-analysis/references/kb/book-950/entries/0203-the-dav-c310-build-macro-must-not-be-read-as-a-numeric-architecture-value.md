```
ID:        0203-the-dav-c310-build-macro-must-not-be-read-as-a-numeric-architecture-value
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin states the equivalence and the warning; the installed
           toolkit's directory names are consistent with it but no build was run to confirm which
           macro actually selects which implementation.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/SKILL.md:16 — "**__DAV_C310__** | 构建系统内部宏，等价于 `NpuArch::DAV_3510`
           / `arch35` / `__NPU_ARCH__=3510`，**不可按数值推断**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build in which `__DAV_C310__` is defined while `__NPU_ARCH__ != 3510`, or vice versa,
           on the same target — that breaks the stated equivalence and turns the pair into two
           independent knobs, which is worse than either reading.
```

# 0203 · The `__DAV_C310__` build macro must not be read as a numeric architecture value

## 1 · Claim
Upstream asserts that `__DAV_C310__` is a build-system-internal macro equivalent to
`NpuArch::DAV_3510`, to `arch35`, and to `__NPU_ARCH__ = 3510` — and attaches an explicit
prohibition: **不可按数值推断** ("must not be inferred from the number"). The digits `310` in
`__DAV_C310__` are not `3510`, are not an architecture number, and do not order against any other
`C`-suffixed macro. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent sees `__DAV_C310__` alongside sibling names in the toolkit (`dav_c220`,
`dav_c100`, `dav_m200`, `dav_m300`, `dav_m310`, `dav_c310` all exist as implementation directories
in the installed CANN) and does the natural thing: reads the suffix as a version number and orders
them. It then writes `#if __DAV_C310__ >= ...`, or concludes that `dav_m310` and `dav_c310` are the
same generation because both end in `310`, or that `c310` is older than `c220`'s successor because
310 < 3510. Every one of those is a numeric inference over a name upstream explicitly declares
non-numeric. None of it fails at compile time — a wrong `#if` selects a *different valid*
implementation, so the kernel builds and runs and is simply wrong for the target.

## 3 · Ground / Source
`ops/npu-arch/SKILL.md:10-16`, the row in its table context:

```
| **archXX** | 算子仓目录简写，取 DAV 编号前两位（如 DAV_3510 → arch35） |
| **__DAV_C310__** | 构建系统内部宏，等价于 `NpuArch::DAV_3510` / `arch35` / `__NPU_ARCH__=3510`，不可按数值推断 |
```

This is the only place in the repo that states the equivalence, and the only place that states the
prohibition. `npu-arch-guide.md` does not repeat either — so an agent that reads the guide instead
of the SKILL.md never meets the warning. That asymmetry is itself the reason this is filed as a
`trap` and not as `knowledge`: the rule exists in exactly one artifact, and the artifact a
downstream reader is most likely to open is the other one.

Consistent with (but not proof of) the equivalence, the installed toolkit
(`cann-9.0.0-beta.2`, `Version=9.0.0-beta.2`, `innerversion=V100R001C10SPC001B214`) carries a
`dav_c310` implementation tree — e.g.
`arm64-linux/asc/impl/basic_api/reg_compute/dav_c310/kernel_reg_compute_vec_binary_impl.h` — beside
`dav_c220`, `dav_c100`, `dav_m200`, `dav_m300`, `dav_m310`. The header tree shows the names coexist;
it does not show which macro selects which, and no build was performed. This is a directory listing,
not a second origin for the claim.

## 4 · Procedure
Runnable later; no device is needed for the decisive arm, which makes this cheap and therefore
worth doing first. Compile-only, on the pinned toolkit, for a `950PR` target.

Arm A — emit both macros from the same translation unit:

```cpp
// probe_macros.cpp — device side, compiled for the 950 target
#if defined(__DAV_C310__)
#  pragma message("DAV_C310 defined")
#else
#  pragma message("DAV_C310 NOT defined")
#endif
#if defined(__NPU_ARCH__)
#  define STR2(x) #x
#  define STR(x) STR2(x)
#  pragma message("NPU_ARCH = " STR(__NPU_ARCH__))
#endif
static_assert(!defined_or_3510_mismatch, "");   // see Arm B
```

Arm B — the equivalence as a hard gate. Compile a unit containing:

```cpp
#if defined(__DAV_C310__) && (__NPU_ARCH__ != 3510)
#  error "__DAV_C310__ defined but __NPU_ARCH__ is not 3510 — equivalence broken"
#endif
#if !defined(__DAV_C310__) && (__NPU_ARCH__ == 3510)
#  error "__NPU_ARCH__ is 3510 but __DAV_C310__ is not defined — equivalence broken"
#endif
```

Arm C — the numeric-inference trap, made observable. Compile
`#if __DAV_C310__ > 300` and record whether it compiles at all. If `__DAV_C310__` is defined as
empty or as `1`, the comparison is either a syntax error or silently false, and either outcome
demonstrates that the suffix does not participate in arithmetic.

The procedure refuses to assume the toolkit under test is the one on `PATH`: the operator names
the toolkit root explicitly and the probe prints the resolved `ASCEND_HOME_PATH` and its
`compiler/version.info` alongside the macro values.

## 5 · Checker — acceptance declared before the run
Verdict variable `macro_equivalence_holds`, set by the harness from the three arms, never from the
compiler's exit code alone — a `#error` and a typo both exit non-zero and they mean opposite things,
so the harness matches the emitted diagnostic text.

Pass requires: Arm B compiles clean (neither `#error` fires) AND Arm A printed `NPU_ARCH = 3510`
AND Arm C failed or evaluated false. A clean Arm B with Arm A silent is explicitly RED, not green:
that is the case where neither macro is defined and the gate vacuously passes. Naming that case is
how this checker avoids reading only the lines it expects — the input that makes it fail is
"compile for a target where neither macro is defined", and the expected result of that input is red.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `dav_c310` directory
listing in §3 is a file-system read of the installed toolkit; a directory listing is not a build and
does not establish which macro the build system defines.

## 7 · Scope limits — what this entry does NOT establish
No build was run and no macro value was observed. The entry does not establish that `__DAV_C310__`
is defined at all on this toolkit, nor that the equivalence upstream states is true — only that
upstream states it and forbids the numeric reading. It says nothing about the other `dav_*`
directories' meanings, and in particular nothing about `dav_c220` or `dav_m200`, whose targets
belong to the other book (RULES.md Art. 1). It does not establish that a numeric misreading has ever
occurred in upstream code; §2 describes an available wrong branch, not an observed one. Finally, it
does not cover the reverse risk — that a *correct* macro is applied to a target whose ini differs
anyway — which is 0205's territory.

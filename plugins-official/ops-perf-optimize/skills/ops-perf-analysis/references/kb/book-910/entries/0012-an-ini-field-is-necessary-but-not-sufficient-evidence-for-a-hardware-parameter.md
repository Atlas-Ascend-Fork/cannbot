```
ID:        0012-an-ini-field-is-necessary-but-not-sufficient-evidence-for-a-hardware-parameter
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:5 — "**ini 文件是发现硬件参数的必要不充分条件** — 并非每个 ini 都对应真实量产芯片，部分配置可能来自工程样片、仿真平台或规划中的 SKU"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a platform_config INI is shown to correspond one-to-one with shipping silicon across the whole DAV_2201 family, making the qualification unnecessary. Or the converse and stronger: an INI value is shown to disagree with a measurement on the part it names.
```

# 0012 · An INI field is necessary but not sufficient evidence for a hardware parameter

## 1 · Claim
Upstream asserts that `platform_config/*.ini` is a necessary but not sufficient condition for
discovering a hardware parameter: not every INI corresponds to a real production chip, and some
configurations describe engineering samples, simulation platforms, or planned SKUs. Upstream
further asserts that its own uses of the words "INI 字段" and "实测" both mean nothing more than
a static value read out of an INI file. Not established here.

## 2 · The wrong branch this removes
An agent finds a capacity in an INI, or in a table sourced from one, and treats it as a
measurement — reasonably, since the file lives inside the installed toolkit and is what the
runtime itself reads. It then states the number in measured voice ("910B2 has 192 MB of L2") and
that sentence propagates into a tiling model, a cost estimate, and eventually a recommendation.
Nothing downstream can recover the fact that no silicon was involved.

This is the specific mechanism behind 0007: two upstream tables disagree at 6× about L2, and the
most likely explanation for at least one of them is that an INI describing something other than a
production 910B2 was read as if it described one. The normal checks miss it completely, because
the value is internally consistent, comes from an authoritative-looking place, and there is no
field in the file that says "this is a simulation config".

A second and sharper form: upstream's own vocabulary defines "实测" (measured) to mean "read from
an INI". An agent that greps upstream for measured claims and trusts the word will collect static
configuration values as measurements. The word is a false friend inside this repo.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md:5`, the file's own confidence convention, verbatim
and in full:

"> **数据可信度约定**：本文档中「INI 字段」/「实测」均指从 ini 读取到的静态配置值。**ini 文件是
发现硬件参数的必要不充分条件** — 并非每个 ini 都对应真实量产芯片，部分配置可能来自工程样片、
仿真平台或规划中的 SKU。文档聚焦架构级常量（§1、§2）和关键差异速查（§3），变化参数仅以典型量产
SKU 举例。"

Restated where it bites hardest, line 126:
"> `platform_config/*.ini` 涵盖多种配置（含工程样片、仿真配置），ini 文件是发现硬件参数的必要
不充分条件，因此**不在此处枚举\"参数范围\"**。"

— note what upstream does with the qualification: it declines to publish a parameter *range*
rather than publishing one with a caveat. That is the disciplined move and it is worth imitating.

Same file §4, lines 158-179, carries a second and different provenance class for the parameters no
INI supplies at all: "以下信息无法从当前安装的 INI 直接推导，数据来源于公开资料或工程经验积累"
— thirteen rows, each tagged "公开资料 / 经验值". So upstream distinguishes three tiers: INI-backed,
public-material-or-experience, and (implicitly) unmarked prose. No other skill in the sources
surveyed for this book states a confidence convention at all — this is the only one.

## 4 · Procedure
Proposed, runnable later; not run. The claim is about a class of evidence, so the procedure is a
sampling audit rather than one measurement.

1. Read-only, no card: enumerate every `platform_config/*.ini` in the installed toolkit
   (`ls "$ASCEND_HOME_PATH"/*/data/platform_config/`; use `grep -R`, not `-r`, since these trees
   symlink). Record the full set of SoC names, including any that do not correspond to a product
   this team has heard of — those are the engineering-sample and planned-SKU rows the convention
   warns about, and their existence is the first half of the claim.
2. For each DAV_2201 INI found, record `ub_size`, `l1_size`, `l0_c_size`, `bt_size`, `l2_size`,
   `cube_core_cnt`, `vector_core_cnt`.
3. Device arm, on a named die (occupancy before and after, no substitution): for the part actually
   installed, query the same parameters through `PlatformAscendC` and compare against the INI that
   claims to describe it.
4. A disagreement in step 3 is the strong overturn condition and the most valuable outcome. An
   agreement establishes only that this one part matches its own INI — it does not retire the
   convention, because the convention is about the INIs that describe *other* things.

## 5 · Checker — acceptance declared before the run
Verdict variables: `ini_soc_count` (step 1) and, per parameter, `ini_vs_runtime_delta` (step 3).
The claim's first half is upheld iff `ini_soc_count` exceeds the number of DAV_2201 parts the team
can name as shipping products — that surplus IS the evidence, and it is checkable without a card.
The claim's second half is upheld trivially by any non-zero `ini_vs_runtime_delta`, and is NOT
refuted by all-zero deltas; a zero-delta result is recorded as "did not bite, retained" and the
convention stands, because a single matching part cannot speak for the INIs of parts absent from
the machine.
This asymmetry is declared here, before the run, precisely so that a clean result cannot later be
narrated as a refutation. Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. This entry does not establish that any specific upstream
number is wrong — it establishes that upstream itself declines to warrant the class. It does not
establish which INIs on any given machine are engineering samples; §4 step 1 can only show that
more configurations exist than products, not which is which. It does not extend to upstream skills
other than npu-arch: no other source in scope declares a confidence convention, so for those files
the provenance of a number is simply unknown, which is a weaker position than this entry
describes, not a stronger one.

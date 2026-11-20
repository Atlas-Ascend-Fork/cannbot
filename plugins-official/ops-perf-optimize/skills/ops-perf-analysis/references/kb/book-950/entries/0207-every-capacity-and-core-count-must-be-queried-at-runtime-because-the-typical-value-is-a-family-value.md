```
ID:        0207-every-capacity-and-core-count-must-be-queried-at-runtime-because-the-typical-value-is-a-family-value
LABEL:     procedure
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/npu-arch) states the rule, the interfaces, and a
           worked anti-example; no call was made and no return value was observed.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:74-78 — "表内为**规格典型值**（族系规格），
           具体 SKU 可能裁剪…vNPU 切分后单实例可见值更低。**算子运行时必须通过下方接口获取实际值**，
           硬编码典型值会越界或浪费。"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:116 — "**运行时始终以该接口返回值分块**，
           禁止硬编码。"  # same skill — ONE origin (RULES.md Art. 3).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 SKU on which `GetCoreMemSize(UB)` returns the family-typical 253952 while the
           physically usable UB differs, or on which `GetCoreNumAiv()` returns the ini value rather
           than the vNPU-visible value — either breaks "query at runtime" as the *sufficient* fix.
```

# 0207 · Every capacity and core count must be queried at runtime because the typical value is a family value

## 1 · Claim
Upstream asserts that the buffer capacities and core counts it publishes are 规格典型值 — family
specifications, not per-part guarantees — that individual SKUs may be cut down, and that a vNPU
partition makes the value visible to one instance lower still. Upstream asserts the operative rule:
operator code must obtain the actual value at runtime through `PlatformAscendC` (`GetCoreNumAic`,
`GetCoreNumAiv`, `GetCoreMemSize`) or, on the host direct-invoke path, through
`aclrtGetDeviceInfo`; hardcoding a typical value will either overrun or waste. Not established here.

## 2 · The wrong branch this removes
The wrong branch is not "the agent forgets". It is that hardcoding *works* on the machine where the
kernel is written, and the failure is displaced onto a machine the author does not have. A constant
`248 * 1024` is correct on every full 950 part in this toolkit's ini set (0209) — so the kernel
passes every test the author can run, and breaks on a cut SKU or inside a vNPU slice, where the
symptom is an out-of-bounds UB access whose stack trace points at the allocation, not at the
constant.

The waste direction is quieter still and never produces a bug report: a kernel that hardcodes a
conservative UB budget on a part with more UB simply runs slower forever, and there is no signal at
all. Upstream names both directions in one sentence — 越界或浪费 — which is why the rule is stated as
an absolute rather than a preference.

The upstream card libraries do not follow this rule. The deep-dive found four distinct hardcoded UB
values and five hardcoded core counts across `ascendc-perf-optimize/references/tiling/` alone
(registered as C-006 and C-007 in `harvest/CONTRADICTIONS.md`), none of them chip-scoped. So the
agent's wrong branch here is not hypothetical: it is the majority practice in the material it will
be reading.

## 3 · Ground / Source
`npu-arch-guide.md:74-78`, the section's own warning block, in full:

> > ⚠️ **核心原则**：本节作为 NPU 架构知识在 skills 仓中的上游真源，下游 skill 应消费本节数据，
> > **反向自引用即视为风险**。
> >
> > 表内为**规格典型值**（族系规格），具体 SKU 可能裁剪（如 Ascend910B3 / Ascend910B4 均为 20 核），
> > vNPU 切分后单实例可见值更低。**算子运行时必须通过下方接口获取实际值**，硬编码典型值会越界或浪费。

The kernel/tiling-side interface set, `npu-arch-guide.md:192-216`:

```cpp
#include "utils/tiling/platform/platform_ascendc.h"
auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint32_t aicNum = ascendcPlatform.GetCoreNumAic();   // Cube 核数
uint32_t aivNum = ascendcPlatform.GetCoreNumAiv();   // Vector 核数
uint64_t ubSize; ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
```

with the routing rule at `:212-216`: Vector operators take `GetCoreNumAiv()`, Cube operators take
`GetCoreNumAic()`, fused operators take both and use each for its own split. The host direct-invoke
path, `:239-243`, is `aclrtGetDeviceInfo` with `ACL_DEV_ATTR_VECTOR_CORE_NUM` /
`ACL_DEV_ATTR_CUBE_CORE_NUM` / `ACL_DEV_ATTR_AICORE_CORE_NUM`, called after `aclrtSetDevice`.

Upstream supplies the anti-example itself, `:218-233` — worth keeping verbatim because it is the
exact shape a generated kernel produces:

```cpp
// ❌ 错误：硬编码典型值，跨型号或裁剪 SKU 上会越界或浪费
constexpr uint32_t CORE_NUM = 32;
constexpr uint32_t UB_SIZE  = 248 * 1024;
SetBlockDim(CORE_NUM);
pipe.InitBuffer(queue, 2, UB_SIZE / 2);

// ✅ 正确：运行时获取
uint32_t coreNum = ascendcPlatform.GetCoreNumAiv();
uint64_t ubSize;
ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
SetBlockDim(coreNum);
pipe.InitBuffer(queue, 2, ubSize / 2);
```

The same rule appears in `npu-hardware-params.md:116` scoped specifically to UB ("表内值为 INI
`ub_size` 字段，即 `GetCoreMemSize(CoreMemType::UB, ...)` 返回的用户可用容量。**运行时始终以该接口
返回值分块**，禁止硬编码") and at `:39` scoped to the cross-architecture invariants ("即便以上参数
通常一致，代码中仍应通过 `GetCoreMemSize` 获取，避免硬编码"). Both are the same skill and therefore
the same origin; they are quoted because the rule's *placement* is the interesting part — upstream
restates it at each table rather than once in a preamble, which is the only placement that reaches
a reader who arrives at a single table.

One upstream exemplar shows the rule applied rather than stated:
`ascendc-perf-optimize/references/tiling/sort/topk_host_tiling.md:81` uses
`GetCoreMemSize(CoreMemType::UB)` in host tiling. The deep-dive nominated exactly this line as the
"query-don't-hardcode" exemplar to preserve.

## 4 · Procedure
Runnable later on `950PR`. The claim has two halves and they need different arms; conflating them is
how this gets certified on the wrong evidence.

Arm A — the interface returns something, and it is the ini value. On a full part, call all three
accessors and compare against the resolved ini's `ub_size`, `cube_core_cnt`, `vector_core_cnt`.
Equality here establishes the *plumbing*, not the claim.

Arm B — the interface tracks a *reduced* configuration, which is the actual claim. This needs a part
where the family value and the visible value differ. Two ways in, in order of preference: (i) a vNPU
partition, where the operator creates a slice with fewer cores and reruns Arm A, expecting
`GetCoreNumAiv()` to fall while the ini is unchanged; (ii) failing that, any SKU in the fleet whose
ini core count differs from the family-typical row. The procedure refuses to substitute a different
die for the die under test (a multi-die sweep can make "die N is clear" false for every die at once,
and a per-die substitution silently changes the subject).

Arm C — the failure the rule prevents, made observable. Build the anti-example verbatim with
`UB_SIZE = 248 * 1024` and run it on the reduced configuration from Arm B. Record whether the
overrun is detected, and by what — a fault, a wrong result, or nothing at all. This arm is the
reason the entry is `procedure` and not `knowledge`: if the overrun is silent, the rule is not
merely good practice, it is the only detector.

Device selection: the operator names the device index and the vNPU slice id; the probe prints both
back with the resolved `ASCEND_HOME_PATH` and `compiler/version.info`; occupancy is checked before
the run; no die is substituted for another at any point.

## 5 · Checker — acceptance declared before the run
Verdict variable `runtime_query_tracks_reality`, and it is deliberately not satisfiable by Arm A
alone. Pass requires: Arm A equal on the full part, AND Arm B showing `GetCoreNumAiv()` (or
`GetCoreMemSize(UB)`) strictly less than the family-typical value on the reduced configuration,
AND that reduced value being the one a correctly-written kernel then allocates against.

Arm A passing with Arm B unavailable is reported as `NOT ESTABLISHED — plumbing only`, never as a
pass. That distinction is the whole checker: a run on one full part can only ever show that the API
agrees with the ini, and agreeing with the ini is what a hardcoded constant also does. A checker
that accepted Arm A would go green on exactly the configuration where the hardcoded constant is
also correct — the known blind species, reading only the lines it expects.

Arm C's verdict is separate and has no pass/fail: it records the detection mode, and "no detection"
is the most informative outcome. The process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No accessor was called, no
vNPU slice was created, and the anti-example was not built.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that `GetCoreMemSize` returns the ini value on
any part, that it tracks a vNPU partition, or that a hardcoded overrun faults rather than corrupts —
all three are Arm A/B/C and all three are open. It does not establish that any *particular* upstream
constant is wrong; it establishes that upstream itself declares the published values to be family
values. The boards named are 950PR and 950DT because those are what upstream's 950 rows name; the
vNPU behaviour is asserted generically by upstream and is not board-scoped in the source, so §4 Arm
B would establish it only for the part it ran on. Nothing transfers to the other book (RULES.md Art. 1) —
the `Ascend910B3 / B4 均为 20 核` example inside the quoted warning is upstream's illustration and is
carried here as text, not as a fact. Finally, the entry does not say what a kernel should do when
the queried value is *larger* than expected; upstream's rule covers allocation, not algorithm
selection, and a tiling strategy that is optimal at 248 KB is not thereby optimal at more.

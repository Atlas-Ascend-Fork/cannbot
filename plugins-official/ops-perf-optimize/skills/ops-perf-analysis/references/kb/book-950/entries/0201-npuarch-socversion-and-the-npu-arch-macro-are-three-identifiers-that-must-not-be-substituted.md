```
ID:        0201-npuarch-socversion-and-the-npu-arch-macro-are-three-identifiers-that-must-not-be-substituted
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin (ops/npu-arch, the repo's self-declared
           真源); no runtime query and no compile was performed to confirm any of the three
           accessors returns what upstream says it returns.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/SKILL.md:10-16 — "**NpuArch** | 芯片架构号，定义指令集和微架构，运行时通过
           `GetCurNpuArch()` 获取"; "**SocVersion** | 片上系统版本，软件命名标识，运行时通过
           `GetSocVersion()` 获取"; "**__NPU_ARCH__** | Device 侧编译宏，四位数值，用于条件编译"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:53-57 — "**核心关系：一对多** … 一个 NpuArch
           可以对应多个 SocVersion"; "对 NPU 核内算子开发来说，通常不需要感知具体 SocVersion，
           使用 NpuArch 来区分芯片有利于易用性和可维护性"
           # both files are ops/npu-arch — ONE origin (RULES.md Art. 3), listed twice for locatability.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a device on which `GetCurNpuArch()` and the compiled-in `__NPU_ARCH__` disagree, or on
           which two chips reporting the same `NpuArch` accept different instruction encodings —
           either observation breaks "NpuArch defines the instruction set".
```

# 0201 · NpuArch, SocVersion and `__NPU_ARCH__` are three identifiers that must not be substituted for one another

## 1 · Claim
Upstream asserts that three distinct identifiers name an Ascend target and that they answer three
different questions: `NpuArch` is the architecture number that *defines the instruction set and
microarchitecture* and is read at runtime via `GetCurNpuArch()`; `SocVersion` is a *software naming
identifier* for the system-on-chip read via `GetSocVersion()`; `__NPU_ARCH__` is a *device-side
compile-time macro* carrying a four-digit value, used for conditional compilation. Upstream further
asserts the relation is one-to-many — one `NpuArch` covers several `SocVersion`s — and recommends
that in-core operator code discriminate on `NpuArch`, not on `SocVersion`. Not established here.

## 2 · The wrong branch this removes
Without this entry a harness agent treats "the chip" as one string and scopes a claim by whichever
identifier the source happened to print. Two concrete wrong branches follow. First, it gates a
kernel on `SocVersion` — so a new SKU of the same architecture, which needs no code change at all,
falls off the supported list and silently takes a fallback path. Second, it assumes the runtime
value and the compile macro are the same knob, and writes a host-side `SocVersion` check to protect
a device-side `#if __NPU_ARCH__` branch; the two are evaluated in different phases, so the check
cannot protect the branch. Normal checks do not catch either: both compile, both run, and both
produce numerically correct output on the machine the author happened to have.

## 3 · Ground / Source
`ops/npu-arch/SKILL.md:10-16`, the concept table in full:

```
| 概念 | 说明 |
|-----|------|
| **NpuArch** | 芯片架构号，定义指令集和微架构，运行时通过 `GetCurNpuArch()` 获取 |
| **SocVersion** | 片上系统版本，软件命名标识，运行时通过 `GetSocVersion()` 获取 |
| **__NPU_ARCH__** | Device 侧编译宏，四位数值，用于条件编译 |
| **archXX** | 算子仓目录简写，取 DAV 编号前两位（如 DAV_3510 → arch35） |
| **__DAV_C310__** | 构建系统内部宏，等价于 `NpuArch::DAV_3510` / `arch35` / `__NPU_ARCH__=3510`，不可按数值推断 |
```

`ops/npu-arch/references/npu-arch-guide.md:53-57` states the cardinality and the design advice:

> **核心关系：一对多**
> 一个 NpuArch 可以对应多个 SocVersion。例如 `DAV_2201` 对应 Ascend910B1~B4、Ascend910B2C、Ascend910_93。
> > **注意**：对 NPU 核内算子开发来说，通常不需要感知具体 SocVersion，使用 NpuArch 来区分芯片有利于易用性和可维护性。

The 950 side of the same one-to-many relation is `ops/npu-arch/references/npu-hardware-params.md:20-21`:
`ASCEND950` / `DAV_3510` / `__NPU_ARCH__` 3510 covers **both** `Ascend950DT (Decode)` and
`Ascend950PR (Prefill)`.

The two files are both under `ops/npu-arch/` and are therefore **one origin**, not two (RULES.md Art. 3).
No other upstream skill states the three-identifier distinction; downstream skills consume the
vocabulary without restating it, which is why a downstream misuse is invisible to a downstream
reviewer.

`npu-arch-guide.md:74` claims this section is the repo's upstream truth source and that
"**反向自引用即视为风险**" — a downstream skill citing itself back as authority is declared a defect.
This entry adopts that direction of flow: 0201 is where every other 950 entry's board vocabulary
comes from.

## 4 · Procedure
Runnable later on `950PR`. Two arms, both required; neither touches the other book.

Arm A — runtime identifiers, host side. Build a tiling-side probe against the installed CANN:

```cpp
// probe_ids.cpp — link against the tiling/platform library of the pinned toolkit
#include "utils/tiling/platform/platform_ascendc.h"
#include <cstdio>
int main(int argc, char** argv) {
    auto plat = platform_ascendc::PlatformAscendC(/* platform info from the context */);
    auto arch = plat.GetCurNpuArch();
    auto soc  = plat.GetSocVersion();
    std::printf("npuarch=%d socversion=%d\n", static_cast<int>(arch), static_cast<int>(soc));
    return 0;
}
```

Device selection is explicit and refuses to be inferred: the operator names the device index and
the probe prints it back; the procedure does NOT assume device 0, does NOT assume the machine has
one card, and does NOT accept a die whose occupancy was not checked first (shared machine).

Arm B — compile-time macro. Compile a device stub twice for the same target and emit the macro:

```cpp
// probe_macro.cpp — device side
#ifndef __NPU_ARCH__
#error "__NPU_ARCH__ is not defined for this target"
#endif
static_assert(__NPU_ARCH__ == 3510, "target is not DAV_3510");
```

The static_assert is the point: a target whose macro is not 3510 must fail the build, not warn.

Cross-check: `npuarch` printed by Arm A must equal the `__NPU_ARCH__` that made Arm B compile. The
one-to-many claim is checked by running Arm A on a `950DT` and a `950PR` and requiring the same
`npuarch` with different `socversion`.

## 5 · Checker — acceptance declared before the run
Verdict variable `id_consistent`, computed by the harness, not by the process exit code — the exit
code of the probe is explicitly declared NOT to be the verdict (a probe that segfaults after
printing must not read as a pass).

`id_consistent` is true iff all three hold: (a) Arm A printed a non-error `npuarch` — the value is
not `DAV_RESV` and not `SocVersion::RESERVED_VERSION`; (b) `npuarch == 3510` on both boards;
(c) Arm B compiled with `__NPU_ARCH__ == 3510` and *failed* when the static_assert was flipped to
`!= 3510`.

Clause (c) is the positive fixture: the checker must be shown going red. Without it this checker is
the known blind species — it reads only the lines it expects (a successful print) and can only
confirm cleanliness. The input that makes it fail is stated now: a target where the flipped
static_assert still compiles means the macro is not participating in the branch at all, and the
verdict is red regardless of what Arm A printed.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured: no probe was compiled, no device was contacted, no accessor was called. The
entry establishes only what upstream's text says. It does not establish that `GetCurNpuArch()`
exists in the installed toolkit under that spelling, that its return value matches
`__NPU_ARCH__` on any board, or that two chips sharing a `NpuArch` genuinely accept the same
instruction encodings — the last is the load-bearing half of upstream's claim and is the hardest to
check, because a shared *macro* is not evidence of a shared *ISA*. It says nothing about 950DT
versus 950PR differences beyond the identifier they share. It says nothing about any board in the
other book; the one-to-many example upstream uses is a DAV_2201 example and is quoted here only as
upstream's own framing, never inherited as a fact (RULES.md Art. 1). Whether upstream's advice — scope on
`NpuArch`, not `SocVersion` — is *good* advice for tiling (as opposed to kernel) code is not
addressed; §2's second wrong branch shows the identifiers can also fail to compose across phases,
and that failure mode is not repaired by picking the right one.

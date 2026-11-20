```
ID:        0208-getcurnpuarch-signals-failure-with-dav-resv-and-an-unchecked-return-silently-selects-a-fallback
LABEL:     trap
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin states the sentinel and its trigger conditions; no call
           was made, and no failure was induced to see what a caller then does.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/SKILL.md:32 — "`GetCurNpuArch()` 失败返回 `NpuArch::DAV_RESV`，
           `GetSocVersion()` 失败返回 `SocVersion::RESERVED_VERSION`。"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:61 — "`DAV_RESV` 是 `GetCurNpuArch()` 的错误
           返回值：获取失败、字符串转换失败或值 <= 0 时返回"  # same skill — ONE origin.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a platform-info context on which `GetCurNpuArch()` fails and returns something other
           than `DAV_RESV` — a throw, a zero, or a stale previous value — which would make the
           sentinel check insufficient rather than merely necessary.
```

# 0208 · `GetCurNpuArch()` signals failure with `DAV_RESV` and an unchecked return silently selects a fallback

## 1 · Claim
Upstream asserts that `GetCurNpuArch()` reports failure in band, by returning
`NpuArch::DAV_RESV`, and names three triggers: the query failing, the string conversion failing, or
the converted value being ≤ 0. Upstream asserts the parallel sentinel for `GetSocVersion()`, which
returns `SocVersion::RESERVED_VERSION`. Not established here.

## 2 · The wrong branch this removes
An in-band error code is only an error if someone reads it as one. The normal shape of arch-
dispatching tiling code is a chain — `if (arch == DAV_3510) { ... } else { ...generic... }` — and
`DAV_RESV` takes the `else`. The kernel then runs a generic path on a 950 part, produces correct
results, and is slower for reasons nothing in the profile explains: there is no error, no warning,
and no branch taken that a reviewer would call wrong. The tiling is simply the fallback tiling, and
the only evidence is a comparison against a build where the query succeeded, which nobody makes.

The inverse is worse in a dispatch written the other way round. `if (arch != DAV_2201) { use the 950
path }` sends `DAV_RESV` down the 950 path, and now a failed query selects arch-specific code on an
unknown part. Neither shape is unusual and neither is detectable without an explicit sentinel check
before the dispatch.

The trigger list matters as much as the sentinel. "值 <= 0" means the failure can originate in a
value the platform layer parsed successfully but found nonsensical — so a `DAV_RESV` return does not
imply the device is absent, and treating it as "no device" is a second wrong branch.

## 3 · Ground / Source
`ops/npu-arch/SKILL.md:22-32`, the accessor block with its sentinel sentence:

```cpp
#include "utils/tiling/platform/platform_ascendc.h"
auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
NpuArch npuArch = ascendcPlatform.GetCurNpuArch();         // DAV_2201 / DAV_3510 / ...
platform_ascendc::SocVersion socVer = ascendcPlatform.GetSocVersion();
```

> `GetCurNpuArch()` 失败返回 `NpuArch::DAV_RESV`，`GetSocVersion()` 失败返回 `SocVersion::RESERVED_VERSION`。

`npu-arch-guide.md:59-62` expands the trigger set under the heading 关键细节:

> - `DAV_RESV` 是 `GetCurNpuArch()` 的错误返回值：获取失败、字符串转换失败或值 <= 0 时返回
> - `Ascend910_93` 的运行时映射关系详见 [`npu-hardware-params.md` §0](npu-hardware-params.md#0-产品映射表)

Upstream states the sentinel and never shows a caller checking it. Every `GetCurNpuArch()` call site
in the quoted examples assigns the result and uses it. That is the gap this entry exists to close:
the rule is stated in a prose bullet, and the code an agent will clone does not contain it — a rule
that lives only where it is not read does not transmit.

Upstream names the header where the enumeration is defined,
`npu-arch-guide.md:422-427`: `asc/include/utils/tiling/platform/platform_ascendc.h` for the
`SocVersion` enum and `PlatformAscendC` interface, `include/platform/soc_spec.h` for the full
`NpuArch` enum. Those are the places a §4 procedure reads first.

## 4 · Procedure
Runnable later on `950PR`. The claim is about a failure path, so the procedure must *cause* the
failure, not wait for it.

Arm A — the happy path, as a control. Call both accessors with a well-formed platform-info context
and record the values; expect `3510` and a 950 SoC version. This arm exists only so Arm B's result
is attributable.

Arm B — induce each of the three triggers separately and record the return, one at a time:
(i) query failure — construct `PlatformAscendC` from a null or unpopulated platform info;
(ii) string-conversion failure — supply a SoC string not present in the convert map;
(iii) value ≤ 0 — supply a platform info whose arch field parses to zero or a negative.
Each is a separate run with a single variable changed. The procedure refuses to bundle them: a
single "make it fail somehow" arm cannot distinguish a sentinel that covers one trigger from one
that covers three, and upstream's claim is about all three.

Arm C — the consequence arm, which is what makes this actionable. Take a realistic dispatch —
`if (arch == NpuArch::DAV_3510) fastPath(); else genericPath();` — feed it the `DAV_RESV` produced by
Arm B, and record which path executes and whether anything in the build or the log says so. The
expected result is that `genericPath()` runs silently, and recording that silence is the finding.

Device selection is explicit for Arm A: the operator names the device index, the probe prints it
back with `compiler/version.info`, and occupancy is checked first (shared machine). Arms B and C
need no device — they are host-side and can run before any card is available, which is why they
should run first.

## 5 · Checker — acceptance declared before the run
Verdict variable `sentinel_is_reachable_and_distinct`, evaluated per trigger, never aggregated —
three triggers with one boolean would let two working sentinels hide one that returns something
else.

Per trigger, pass requires the returned value to compare equal to `NpuArch::DAV_RESV` AND to compare
unequal to every named architecture value including `DAV_3510`. The second clause is not redundant:
a sentinel that happens to share a numeric value with a real architecture would pass the first check
and be useless, and that is exactly the failure an in-band error code invites.

The positive fixture is Arm A inverted: feed the *valid* context and require the checker to report
`sentinel_is_reachable_and_distinct = false` — that is, the checker must go red when handed a
success. A checker that greens on both a success and a failure is reading only for the presence of a
value, which is the known blind species. Arm C has no pass condition; it records which branch ran,
and a run in which no branch is identifiable is red for instrumentation, not for the claim.

Process exit codes are not the verdict anywhere: a probe that aborts while inducing trigger (i) exits
non-zero for a reason unrelated to what was returned.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No accessor was called, no
failure was induced, and the enum headers named in §3 were not opened.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that `DAV_RESV` exists in the installed toolkit's
`NpuArch` enum under that spelling, that any of the three triggers actually produces it, or that a
caller's fallback is silent — Arms A, B and C are all open. It does not establish the analogous
behaviour of `GetSocVersion()` beyond quoting the sentence: `RESERVED_VERSION` is named by upstream
and is untested here, and the two accessors may not share a failure model. It says nothing about
what a *correct* caller should do after detecting the sentinel — abort, retry, or refuse to emit
tiling — because upstream states the sentinel and not the policy, and inventing the policy here would
exceed the source. Nothing transfers to the other book (RULES.md Art. 1); the `Ascend910_93` bullet
adjacent to the quoted line is upstream's text and is not carried as a fact. Finally, the entry does
not establish that unchecked returns occur in upstream code — §3 records that upstream's own examples
omit the check, which is an observation about the examples, not a survey of the operator repo.

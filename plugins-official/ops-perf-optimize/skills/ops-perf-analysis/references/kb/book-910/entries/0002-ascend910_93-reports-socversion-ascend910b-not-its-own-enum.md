```
ID:        0002-ascend910_93-reports-socversion-ascend910b-not-its-own-enum
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     910_93
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:25 — "`Ascend910_93` 的 SocVersion 字符串在运行时映射到 `SocVersion::ASCEND910B`（非独立枚举值）……convertMap 中 `\"Ascend910_93\"` 映射到的是 `ASCEND910B`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a runtime print of `GetSocVersion()` on an Ascend910_93 part returns `SocVersion::ASCEND910_93` rather than `SocVersion::ASCEND910B`.
```

# 0002 · `Ascend910_93` reports SocVersion `ASCEND910B`, not its own enum

## 1 · Claim
Upstream asserts that although the enumerator `SocVersion::ASCEND910_93` exists in
`platform_ascendc.h`, the runtime conversion map sends the string `"Ascend910_93"` to
`SocVersion::ASCEND910B`, and that the dedicated enumerator is used only by a few internal
modules. Not established here.

## 2 · The wrong branch this removes
A harness agent writes a runtime dispatch `if (socVer == SocVersion::ASCEND910_93) { /* A3 path */
}`, sees the enumerator exists in the installed header, and ships. The branch is dead: on real A3
hardware the comparison is false and the A2 path runs. This is worse than 0001's compile-time
version because the *symbol resolves* — the header lookup that a careful agent performs to verify
an enum name returns success, so the usual "does this identifier exist" check passes while the
dispatch is still wrong. Combined with 0001 (the arch macro also collapses), an agent has two
plausible discriminators and both fail.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md:25`, verbatim and in full:

"> **运行时映射**：`Ascend910_93` 的 SocVersion 字符串在运行时映射到 `SocVersion::ASCEND910B`
（非独立枚举值）。源码中虽存在 `SocVersion::ASCEND910_93` 枚举值（platform_ascendc.h），但
convertMap 中 `\"Ascend910_93\"` 映射到的是 `ASCEND910B`，该枚举仅在少数内部模块使用。NpuArch
同为 `DAV_2201`。"

Context: this note sits directly under the §0 product mapping table quoted in 0001, as a
qualification of the A3 row.

The same file, line 32 of `ops/npu-arch/SKILL.md`, states the failure returns:
"`GetCurNpuArch()` 失败返回 `NpuArch::DAV_RESV`，`GetSocVersion()` 失败返回
`SocVersion::RESERVED_VERSION`." — so a third outcome (neither ASCEND910B nor ASCEND910_93)
is possible and must be recorded rather than folded into "not A3".

No second origin in this repo; the claim is about installed-toolchain source, which is exactly
where an independent origin would come from (see §4 step 2).

## 4 · Procedure
Proposed, runnable later; not run.

1. Read-only, no device needed for the first half: grep the installed toolchain for the enum and
   the conversion map. `grep -Rn "ASCEND910_93" "$ASCEND_HOME_PATH"/*/include` — note `-R`, since
   `grep -r` does not follow the symlinked directories these installs use. Record the header path,
   the enumerator's value, and whether a `convertMap`-like table is visible in a header at all.
   This half is permitted in the no-card phase (read-only toolkit inspection) and, if the map is
   visible, supplies a genuinely independent second origin — the installed SDK, not this repo.
2. Device half: on a part known to be Ascend910_93, name the die explicitly, check occupancy
   before and after, refuse to substitute another die, and print
   `PlatformAscendC(context->GetPlatformInfo()).GetSocVersion()` as an integer alongside the
   enumerator values of both `ASCEND910B` and `ASCEND910_93`.
3. Record the integer, not a symbolic name — a printed name would be produced by the same mapping
   under test.

## 5 · Checker — acceptance declared before the run
Verdict variable `soc_reported`, the integer returned by `GetSocVersion()`.
PASS (claim upheld) iff `soc_reported == (int)SocVersion::ASCEND910B`.
FAIL/overturn iff `soc_reported == (int)SocVersion::ASCEND910_93`.
INCONCLUSIVE, recorded as such and not as a pass, iff `soc_reported ==
(int)SocVersion::RESERVED_VERSION` or any other value.
The process exit code is not the verdict. The three-way outcome is the point: a two-way checker
here would score the documented failure return as an overturn, which is the "reads only the lines
it expects" species. The comparison is against integers precisely so that the printing path
cannot launder the answer.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no board was touched, and BOARD names the board upstream's sentence is
about, not a board we ran on. This entry does not establish which internal modules use the
dedicated enumerator, nor whether a future CANN release changes the map — the claim is pinned to
no toolkit version at all, because upstream names none. It does not establish anything about
Ascend910B2C, which shares the A2 row and may or may not have its own mapping quirk. It offers no
working A2/A3 discriminator; see 0001 §7 and the standing question it names.

```
ID:        0344-the-reg-api-rename-table-holds-against-the-installed-headers-except-the-one-row-that-gives-a-path
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   corroborated — four of the table's rows were checked against the INSTALLED CANN
           9.0.0-beta.2 headers on this machine, an origin independent of upstream's document, and
           they hold. One row — the include path — is CONTRADICTED by the installed tree, on a
           different toolkit version than the row is scoped to. Nothing was compiled.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/regbase/cann_version_compat_faq.md:154-165
           — the ten-row API compatibility table, rows quoted in §3, including "| 3 | `__local_mem__`
           | 新代码优先 `__ubuf__`；旧模板可暂时保留 | 9.1.0 的 `kernel_reg_compute_common_intf.h`
           已定义 `#define __local_mem__ __ubuf__`，不能将其误判为未定义 |" and "| 10 | include
           `"op_kernel/platform_util.h"` 找不到 | 使用 `#include
           "op_common/op_kernel/platform_util.h"` 并确保 SDK 的 `<arch>-linux/include` 在 `-I` 中"
SOURCE:    same file:123-129 — "| CANN 8.5.0 | `impl/micro_api/` 中直接定义 `AscendC::MicroAPI` |
           `MicroAPI` 是旧版主命名空间 | | CANN 9.0.0 起 | `basic_api/reg_compute/` 中直接定义
           `AscendC::Reg` | `Reg` 是当前主命名空间 |" · "旧 SDK 不存在 `AscendC::Reg`。... 8.5 到
           9.0 除命名空间迁移外还有接口和重载变化，命名空间别名不能证明 API 兼容。"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — see §3 for the five checked locations.
INDEX:     none — nothing measured; see SOURCE. Each checked row is re-derivable by file read;
           the commands are given per row in §3.
OVERTURN:  a CANN 9.1.0 installation in which `<arch>-linux/include/op_common/op_kernel/platform_util.h`
           does not exist either — row 10's advice would then be wrong for its own stated version,
           not merely for the one installed here.
```

# 0344 · The Reg API rename table holds against the installed headers, except the one row that gives a path

## 1 · Claim
Upstream asserts a ten-row table mapping obsolete spellings in its VF templates to their CANN 9.1.0
forms, each with a stated root cause. Five of the rows are checkable by reading the installed
headers, and this entry reports that check. Upstream asserts the namespace history that frames the
table: CANN 8.5.0 defined `AscendC::MicroAPI` directly under `impl/micro_api/`; from CANN 9.0.0
`AscendC::Reg` is the primary namespace, defined under `basic_api/reg_compute/`; the 9.x SDK
declares `namespace MicroAPI = Reg;` conditionally for old code. Upstream asserts the discipline
that goes with it: an old SDK has no `AscendC::Reg`, a project-side reverse alias is admissible only
when the build system has positively identified CANN 8.5 and every API used has been checked
individually, and a namespace alias is not evidence of API compatibility because 8.5 → 9.0 also
changed interfaces and overloads. Not established here beyond the file reads §3 reports; nothing was
compiled.

## 2 · The wrong branch this removes
A rename table's whole function is to stop an agent concluding "this API does not exist" when the
API was renamed. Four of the rows here name that failure explicitly — row 3's
`不能将其误判为未定义`, row 8's `不能写成"无此函数"或无条件硬编码常量`, row 9's
`不得把模板自带 helper 误当成 SDK 能力`, row 7's `小写 ops 是本模板自带工具，不是 SDK 全局能力`.
Each is a different direction of the same error: mistaking a macro for a missing symbol, a real SDK
function for an absent one, a template's private helper for an SDK capability, and a template's
private namespace for a global one.

The consequence of each is the same and is expensive: a hard-coded constant where a query existed
(row 8 is `GetUbBlockSize` / `GetVRegSize`, which `950:0207` and `950:0141` make a governing rule —
capacities are queried, never literal), or a hand-rewritten helper whose boundary semantics differ
from the one that was already there (row 9).

The second wrong branch is the one this entry adds and upstream cannot: **taking the table's paths
as facts rather than as version-scoped observations.** Row 10 gives an include path and an `-I`
directory. On the toolkit installed here those headers exist at a *different* location, and the
directory row 10 names does not exist at all. The rename half of that row is right; the location
half is a property of the release. An agent following it verbatim on this machine adds an `-I` to a
directory that is not there, gets the same "not found" error, and now has evidence that the guidance
is wrong — when what it has is a version mismatch.

That is the reason the FAQ's own evidence hierarchy (`0343` §3) puts the installed headers *above*
this library's knowledge: the table is a map of one release, and the release in front of you is the
authority.

## 3 · Ground / Source
The namespace history, `regbase/cann_version_compat_faq.md:123-129`:

```
| 版本 | 实际定义 | 结论 |
| CANN 8.5.0 | `impl/micro_api/` 中直接定义 `AscendC::MicroAPI` | `MicroAPI` 是旧版主命名空间 |
| CANN 9.0.0 起 | `basic_api/reg_compute/` 中直接定义 `AscendC::Reg` | `Reg` 是当前主命名空间，
  新代码和知识库统一使用它 |
| CANN 9.0.0 / 9.1.0 | `kernel_macros.h` 在支持的目标架构下声明 `namespace MicroAPI = Reg;` |
  新 SDK 为旧源码保留条件性命名空间别名 |
```

with the caution at `:150`:
`8.5 到 9.0 除命名空间迁移外还有接口和重载变化，命名空间别名不能证明 API 兼容。` — an alias makes
old *names* resolve and says nothing about signatures, which is the distinction an agent adding a
reverse alias to "fix" a build is not making.

The rows checked here, `:154-165`, quoted in the header and abbreviated below with the check result:

**Row 3 — `__local_mem__`.** Upstream: 9.1.0's `kernel_reg_compute_common_intf.h` defines
`#define __local_mem__ __ubuf__`, so it must not be judged undefined.
*Checked:* `asc/include/basic_api/reg_compute/kernel_reg_compute_common_intf.h:36` —
`#define __local_mem__ __ubuf__`. **Holds**, in 9.0.0-beta.2 as well as the 9.1.0 upstream names.
Re-derive: `grep -Rn 'define __local_mem__' $ASCEND_HOME_PATH/asc/`.

**Row 4 — `plt_b32(count, POST_UPDATE)` → `UpdateMask<T, RegTrait>(count)`.** Upstream: the public
Reg interface returns a `MaskReg` and `count` is `uint32_t&`.
*Checked:* `asc/include/basic_api/reg_compute/kernel_reg_compute_maskreg_intf.h:31` —
`__simd_callee__ inline MaskReg UpdateMask(uint32_t& scalarValue);`. **Holds**, including the
by-reference `uint32_t` upstream singles out. `950:0255` carries the consequence of that reference —
`UpdateMask` decrements its argument, so a manual decrement double-steps — and is cited, not
restated.

**Row 5 — `DataCopyUnAlign(...)` → `StoreUnAlign<T, PostLiteral::POST_MODE_UPDATE>(...)`.** Upstream:
the 9.1.0 public name is `StoreUnAlign` and `ureg` is `UnalignRegForStore`.
*Checked:* `asc/include/basic_api/reg_compute/kernel_reg_compute_datacopy_intf.h:107,121,128,170` —
four `StoreUnAlign` overloads, all taking `UnalignRegForStore& ureg`. **Holds.**

**Row 8 — `GetUbBlockSize()` / `GetVRegSize()`.** Upstream: both exist in 9.1.0 under `Ops::Base`
via the public `platform_util.h`, so neither may be reported as absent nor replaced by a hard-coded
constant.
*Checked:* both are defined, as `__aicore__ inline constexpr uint32_t`, at
`aarch64-linux/pkg_inc/op_common/op_kernel/platform_util.h:30` and `:38`. **Holds** — the functions
exist.

**Row 10 — the include path.** Upstream: use `#include "op_common/op_kernel/platform_util.h"` and
ensure the SDK's `<arch>-linux/include` is on `-I`; the public header is at
`$ASCEND_HOME_PATH/<arch>-linux/include/op_common/op_kernel/platform_util.h`.
*Checked:* on this machine the header is at
`$ASCEND_HOME_PATH/aarch64-linux/**pkg_inc**/op_common/op_kernel/platform_util.h`, and
`$ASCEND_HOME_PATH/aarch64-linux/include/op_common` **does not exist**. `math_util.h`, which
upstream names at the same location, is likewise under `pkg_inc`. **Contradicted here.** Re-derive:
`find $ASCEND_HOME_PATH -name platform_util.h`.

Row 10 is scoped by upstream to CANN 9.1.0 and this toolkit is 9.0.0-beta.2, so the contradiction is
about a *release layout*, not about upstream being wrong for its own version — and that is precisely
the finding worth carrying: the rename is portable, the path is not. Recorded in
`harvest/standing/950-bp.md`.

Five rows were **not** checked: rows 1 and 2 (`MicroAPI` versus `Reg` and the alias's arch gate,
carried by `950:0244` and `950:0352`), row 6 (`StoreUnAlignPost`), row 7 (`ops::CeilDiv` versus
`Ops::Base::CeilDiv`) and row 9 (`FindNearestPower2`). They are cheap and are owed.

Measured/inferred split: **read, not measured** — the five locations above. **not established** —
that any of these resolves in a build (a declaration is not an instantiation, `0343`); that the
8.5 → 9.0 interface changes upstream mentions are limited to the rows listed; that the table is
complete.

## 4 · Procedure
Proposed, runnable later. Never run in this phase — and note that the decisive arms need a
**compiler**, which phase 1 permits no more than a device.

Arm 1 — finish the sweep, `[no-card]` and **partly done** (§3). Check the remaining five rows against
the installed headers by the same method, recording symbol, header path, signature and toolkit pin
for each. Report every row as `holds`, `contradicted` or `absent`.

Arm 2 — the layout across releases. Repeat the row-10 check on every CANN package available,
recording where `platform_util.h` and `math_util.h` live in each. The output is a small table
mapping release to layout, which is what an agent actually needs when the FAQ's path fails — and
which no document supplies.

Arm 3 — declaration against resolution. For each row that `holds`, compile a minimal translation
unit that uses the symbol under each build contract `0343` enumerates. A symbol declared in a header
that is not included under the current contract is exactly the failure `0343` §3 describes, and this
arm is where the two entries meet.

Arm 4 — the alias direction, tested rather than assumed. Build a unit using `AscendC::MicroAPI::*`
on this 9.0.0 toolkit at `--npu-arch=dav-3510` and at an arch outside the gated set (`950:0352`).
Upstream predicts the alias is declared only for the gated values, so the second must fail. This is
the arm that distinguishes "the alias exists" from "the alias exists here".

Arm 5 — the reverse alias, as a warning rather than a recipe. On a genuine CANN 8.5 installation if
one is available, check whether the individual APIs this shelf's templates use have the same
signatures under `MicroAPI` as under `Reg`. Upstream states an alias does not prove compatibility;
this arm would say how far apart they actually are, and if no 8.5 install exists the arm is reported
as unavailable rather than skipped.

No SDK file is modified — the shelf's P0 red line and this project's read-only rule. Toolchain
provenance is recorded per arm: the invocation, `--npu-arch`, include roots from
`compile_commands.json`, and `compiler/version.info`. Refuses to assume: that a header's presence
implies it is reachable from the current `-I` set; that `pkg_inc` and `include` serve the same
purpose (they may not, and Arm 2 records the layout without theorising about it); that a table row
that holds on 9.0.0-beta.2 holds on 9.1.0 or the reverse.

## 5 · Checker — acceptance declared before the run
Verdict `row_status[i]` for `i = 1…10`, one of `holds` / `contradicted` / `absent` / `unchecked`,
each with the header path and toolkit pin that produced it. Declared before the run: a row is
`holds` only if the symbol is found **and** its signature matches what upstream states; a symbol
found with a different signature is `contradicted`, not `holds`, because the table's purpose is to
let an agent write a call.

Verdict `layout[release]` from Arm 2 — the deliverable, and the thing that would have prevented the
row-10 mismatch from reading as an error.

Verdict `resolves[i][contract]` from Arm 3, per row per build contract.
Verdict `alias_gated` from Arm 4.

The exit code is not the verdict for Arms 1–2 (file reads have no verdict) and **is** part of it for
Arms 3–5, recorded with full unclipped stderr and the first uncut `error:` line (`0345`).

Three guards. First — the input that makes this checker go red — Arm 1 includes a **control symbol
that does not exist**: a plausible but invented name (`Reg::StoreUnAlignPre`, say) which the sweep
**must** report as `absent`. If the sweep reports it as found, its matching is too loose — a
substring hit inside a comment or a different namespace — and every `holds` in the table is void.
A rename-table check whose only possible outcome is "everything is present" is the known blind
species, and an invented name is the cheapest fixture that excludes it.

Second, every `holds` records the *signature*, not merely the name. Row 4's whole content is that
`count` is `uint32_t&` rather than a value; a name-only check would have passed a version where it
was by value, and `950:0255` records that the reference is load-bearing.

Third, no row's status is reported without its toolkit pin beside it. Row 10 is the demonstration:
the same check gives opposite answers on two releases, and a status without a pin is not a fact.

## 6 · Evidence
NOT YET RUN as a build procedure — nothing was compiled. Nothing in this file is a measurement.

Five file reads **were** performed under the phase-1 read-only exception, against CANN
`Version=9.0.0-beta.2` on this machine, and their outputs are in §3: `__local_mem__` defined as
`__ubuf__` at `kernel_reg_compute_common_intf.h:36`; `UpdateMask(uint32_t&)` returning `MaskReg` at
`kernel_reg_compute_maskreg_intf.h:31`; four `StoreUnAlign` overloads taking `UnalignRegForStore&`
at `kernel_reg_compute_datacopy_intf.h:107-170`; `GetUbBlockSize` and `GetVRegSize` as
`__aicore__ inline constexpr uint32_t` at `platform_util.h:30,38`; and that header located under
`aarch64-linux/pkg_inc/op_common/`, with `aarch64-linux/include/op_common` absent.

A file read establishes that a symbol is declared somewhere in a tree. It does not establish that a
build includes that header, that the declaration is instantiable under the current contract
(`0343`), or that anything behaves as its name suggests. Five of the ten rows remain unchecked.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The `corroborated` stratum covers four rows' *declarations* on one toolkit
(`9.0.0-beta.2`), one host-architecture directory (`aarch64-linux`), one machine — and upstream's
table is scoped to 9.1.0, a version not installed here, so the agreement is across versions and the
one disagreement (row 10's path) may be nothing more than a release layout change. Five rows were
not checked at all. No row was shown to resolve in a build, which is the only thing an implementer
actually needs and which `0343` explains cannot be inferred from a header's existence. The
8.5 → 9.0 interface and overload changes upstream warns about are neither enumerated by upstream nor
investigated here, so the reverse-alias caution is carried at upstream's strength and no higher. The
FAQ itself is scoped to `CANN 9.1.0 / bisheng clang 15.0.5 / dav-3510 (Ascend950PR)`. BOARD is
`family-claimed(unverified)`: header layout and symbol naming are properties of a release, not of a
board, and no board was contacted. Nothing transfers to the other book (RULES.md Art. 1) — the Reg
interface is stated by upstream's own gate to be arch35-era (`950:0352`).

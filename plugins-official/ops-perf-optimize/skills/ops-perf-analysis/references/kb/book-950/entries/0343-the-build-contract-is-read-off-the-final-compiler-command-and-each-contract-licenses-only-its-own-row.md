```
ID:        0343-the-build-contract-is-read-off-the-final-compiler-command-and-each-contract-licenses-only-its-own-row
LABEL:     procedure
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/regbase/cann_version_compat_faq.md:45-52
           — the four-row build-contract table quoted in full in §3, with "| `device_only` | 最终
           命令含 `--cce-aicore-only` | 已成功源码中的命名空间/类级 Reg 声明可作为该契约下的证据 |
           不能证明直接 `-xasc` 也能照搬 |" and "`.cpp`、`.asc`、`__VEC_SCOPE__`、`__simd_vf__ +
           asc_vf_call` 是源码形态，不是构建契约。不得把不同成功实现的入口属性、声明位置、宏和 flags
           拼成一种"通用写法"。"
SOURCE:    same file:23 — "逐项读取预检结果的 `vf_translation_units`，比较每个 VF 编译翻译单元及其
           include 闭包与范例目录记录的源构建契约；不同或未知时先做最小编译探针。顶层 `contracts`
           只是工程证据清单，不能借用无关源文件的契约" ; :37-42 — the three-level evidence hierarchy ;
           :71 — "对 `xasc_combined`，优先使用目标工程已验证的**函数作用域 `static constexpr`** 写法"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a namespace-level `AscendC::Reg::CastTrait` declaration that compiles under a genuine
           `xasc_combined` command on a named 950 toolkit — the contract distinction would then not
           govern declaration visibility, and the table's central column would be describing
           something else.
```

# 0343 · The build contract is read off the final compiler command, and each contract licenses only its own row

## 1 · Claim
Upstream asserts that whether a Reg/VF construct is legal in a translation unit is a property of
that unit's **build contract**, that the contract is identified only from the final compiler
command, and that source-level appearances do not identify it: `.cpp`, `.asc`, `__VEC_SCOPE__` and
`__simd_vf__ + asc_vf_call` are source forms, not contracts. Upstream asserts four contracts with
their hard evidence and — this is the load-bearing column — what each does and does not license.
`device_only` is identified by `--cce-aicore-only` in the final command and licenses namespace- or
class-level Reg declarations *as evidence under that contract*, while proving nothing about a direct
`-xasc` build. `xasc_combined` is `-xasc` without `--cce-aicore-only`, means the file may pass
through host processing as well, and requires the visibility of Reg declarations to be reviewed;
`--npu-arch` alone does not license assuming a complete Reg API at file scope. `cce_wrapper` is a
flow showing only `-x cce`, confirms entry into the CCE/TBE wrapper and does not replace the final
backend command. `unknown` — no real command, only CMake or documentation intent — licenses
recording the question and forbids claiming the template compiles, the API is incompatible, or the
compiler has a bug. Upstream asserts a three-level evidence hierarchy: an isomorphic successful
build in the target project (same build system, CANN and SoC, with its actual command) outranks the
installed headers, which outrank this library's templates and RegBase knowledge. Upstream asserts
the operational consequence: with no isomorphic precedent, do a minimal single-dtype single-VF
single-translation-unit compile probe, and never assemble entry attributes, declaration positions,
macros and flags from different successful builds into one "general form". Not established here.

## 2 · The wrong branch this removes
The failing sequence upstream is describing is specific and is the most common way an agent retires
a capability that works.

An agent copies a VF example whose declarations sit at namespace scope, builds under `-xasc`, and
gets `error: no type named 'CastTrait' in namespace 'AscendC::Reg'`. Two readings are available: the
API is unavailable on this toolkit, or the declaration is in a region this contract does not make it
visible in. The first is the natural reading — the error says the type is not there — and it leads
to abandoning the Reg path. The second is upstream's, and the discriminator is a flag on a command
line that the agent never looked at.

The second wrong branch is generalising from a success. A working example under `device_only` proves
its declaration position works *under `device_only`*. Upstream's table encodes that as a right-hand
column — `不能证明直接 -xasc 也能照搬` — and the discipline is unusual: it is a table of what each
piece of evidence *cannot* support, which is the half most tables omit.

The third is the composite. `不得把不同成功实现的入口属性、声明位置、宏和 flags 拼成一种"通用写法"`
describes an agent assembling a template from several working kernels: this one's entry macro, that
one's trait placement, a third's flags. Each fragment is evidenced; the combination is evidenced by
nothing, and it will fail in a way that looks like a toolchain defect.

The fourth is scope of evidence within one project. Upstream states that the preflight report's
top-level `contracts` is a project inventory, not a licence — the contract that matters is the one
belonging to *this* translation unit and its include closure, and borrowing an unrelated file's
`device_only` record to explain the current unit is the same category error one level in.

## 3 · Ground / Source
The table, `regbase/cann_version_compat_faq.md:45-52`:

```
| 构建契约 | 硬证据 | 可以推出什么 | 不能推出什么 |
| `device_only` | 最终命令含 `--cce-aicore-only` | 已成功源码中的命名空间/类级 Reg 声明可作为该契约
  下的证据 | 不能证明直接 `-xasc` 也能照搬 |
| `xasc_combined` | 最终命令含 `-xasc` 且不含 `--cce-aicore-only` | 文件可能经历 host/device 联合
  处理，须审查 Reg 声明的可见域 | 不能仅凭 `--npu-arch` 假设文件顶层已有完整 Reg API |
| `cce_wrapper` | 上层流程只显示 `-x cce` | 只能确认进入 CCE/TBE 包装流程 | 不能代替最终后端命令；
  继续查是否生成 `--cce-aicore-only` |
| `unknown` | 没有真实命令或只有 CMake/文档意图 | 只能记录待确认 | 不能宣称模板可编译、API 不兼容
  或编译器有 bug |

`.cpp`、`.asc`、`__VEC_SCOPE__`、`__simd_vf__ + asc_vf_call` 是源码形态，不是构建契约。不得把不同
成功实现的入口属性、声明位置、宏和 flags 拼成一种"通用写法"。目标工程没有同构成功先例时，先做
单 dtype、单 VF、单翻译单元的最小编译探针。
```

The mechanism, `:54-67`, is what makes the table more than bureaucracy:

```
### 为什么本地范例能在命名空间级写 `CastTrait`，目标工程却报找不到？

这两个事实可以同时成立：

- 包内 `compile_verified_skeleton` 的探针使用 `--cce-aicore-only`，命名空间级
  `AscendC::Reg::CastTrait` 在该 device-only 契约下可见。
- 目标工程若直接使用 `-xasc`，同一翻译单元还会经历 host 解析，Reg 类型的可见条件可能不同；因此
  不能从一种构建契约推出"Trait 必须永远放 VF 内"或"可以永远放文件顶层"。

CANN 9.1.0 `kernel_operator_intf.h` 只在受支持的 `__NPU_ARCH__` 或 `__ASC_NPU_HOST__` 条件下
include reg-compute 接口；`kernel_macros.h` 会创建空的 `AscendC::Reg` 命名空间，但实际类型和
`MicroAPI = Reg` 兼容别名仍受条件控制。
```

`kernel_macros.h` creating an **empty** `AscendC::Reg` namespace is the detail that makes the error
message misleading: the namespace exists, so the diagnostic is "no type named X in namespace Y"
rather than "no namespace Y", and the reader concludes the type was removed rather than that the
interface was never included. `950:0352` carries the four `__NPU_ARCH__` values that gate the
reg-compute include from the other side of the same question and is cited here rather than restated.

The resolution for the common case, `:69-91`, is a concrete rule with a stated reason for each half:

```
CANN 9.1.0 的 `Reg::Cast` 接收 `const CastTrait& trait` 非类型模板参数。对 `xasc_combined`，优先
使用目标工程已验证的**函数作用域 `static constexpr`** 写法：函数作用域避开 host pass 对文件顶层
Reg 类型的可见性问题，`static` 又提供模板引用参数需要的静态存储期。
```

and the diagnostic table beneath it maps three writings to their `xasc_combined` outcomes, each row
ending in the same column this entry is about — `能否据此判定 CastTrait 不可用` — answered `不能`
twice and `以目标真实 flags 的编译结果为准` once.

The evidence hierarchy, `:37-43`:

```
1. **目标工程的同构成功实现**：同一构建系统、CANN 和 SoC 下已生成目标文件或 `.so` 的 VF kernel，
   以及它的实际编译命令。
2. **当前 CANN 安装头文件**：只读核对类型、签名、枚举、宏条件和架构实现。
3. **本库模板和 RegBase 知识**：用于选算法和 API 范式，落地前必须按前两项适配。
```

Note that this ranks an *installed header read* below an isomorphic successful build and above a
document — which is exactly the stratification this book applies to its own sources, arrived at
independently by another team for the same reason.

The per-translation-unit scoping, `:23`:

```
逐项读取预检结果的 `vf_translation_units`，比较每个 VF 编译翻译单元及其 include 闭包与范例目录
记录的源构建契约；不同或未知时先做最小编译探针。顶层 `contracts` 只是工程证据清单，不能借用无关
源文件的契约
```

The FAQ scopes itself at `:5` to `CANN 9.1.0 / bisheng clang 15.0.5 / dav-3510 (Ascend950PR)`, with
`其他版本以实际编译器为准`. The machine here carries 9.0.0-beta.2, a different version, so even the
header-level claims in §3 were not checked against the version upstream describes.

Nothing here is measured or compiled by this book.

## 4 · Procedure
Proposed, runnable later — and note that this entry's arms need a **compiler**, not a device, which
phase 1 permits no more than a device run. Never run in this phase.

Arm 1 — the contract distinction, as a 2×2. One translation unit, one VF calling `Reg::Cast`, built
four ways: `CastTrait` at namespace scope and at function scope with `static constexpr`, each under
`--cce-aicore-only` and under `-xasc`. Record, for each cell, the exit code and the first uncut
`error:` line (`0345`'s protocol). Upstream's table predicts three successes and one failure — the
namespace-scope declaration under `xasc_combined`.

Arm 2 — the non-static control. Function scope without `static`, under `xasc_combined`. Upstream
predicts a *different* error (invalid template argument, not missing type), and the difference is
what shows the two failures have different causes rather than one being noise.

Arm 3 — the identification claim. Take three real translation units from any project on this
machine, extract their final commands from `compile_commands.json`, classify each by the table's
hard-evidence column, and check whether a `-x cce` flow ever resolves to a backend command
containing `--cce-aicore-only` — which is the `cce_wrapper` row's instruction to keep looking.

Arm 4 — the composite prohibition, tested. Assemble a "general form" from the entry attributes,
declaration positions and macros of two builds that each succeed under *different* contracts, and
build it under each. Upstream predicts it fails at least one. This arm has an unusual property: it
can only confirm the prohibition or reveal a genuinely portable form, and both are useful.

Toolchain provenance is recorded rather than assumed: exact `bisheng` invocation, `--npu-arch`,
include roots resolved from `compile_commands.json`, and the toolkit pin from
`compiler/version.info`. Every arm is repeated on every CANN package present, because the FAQ scopes
itself to 9.1.0 and this machine has 9.0.0-beta.2. No SDK file is modified — the shelf's own P0 red
line and this project's read-only rule. No device is needed; Arms 1–4 are marked `[no-card]` in
`harvest/standing/950-bp.md` and have **not** been run.

Refuses to assume: that a build system's stated flags are the final backend command (Arm 3 exists
because they are not); that a success under one contract predicts another (that is the claim); that
"it compiled" means the VF path survived — the preflight's `vf_translation_units` and the resulting
object are both inspected, since a VF silently degraded to high-level API also compiles.

## 5 · Checker — acceptance declared before the run
Verdict `cell[scope][contract]` for Arm 1's four cells, each = (exit code, first uncut error line).
Declared before the run: the table is **supported** iff namespace-scope-under-`xasc_combined` is the
only failure **and** its first error names a missing type in `AscendC::Reg`. A failure in a different
cell, or a failure with a different first error, does not confirm the table — it is a different
phenomenon and is recorded as one.

Verdict `nonstatic_error` from Arm 2, required to differ from `cell`'s failing error.
Verdict `wrapper_resolves` from Arm 3.
Verdict `composite_fails` from Arm 4.

The exit code **is** part of the verdict here — these are build experiments — and it is recorded
together with the full unclipped stderr, so that a zero exit with warnings and a non-zero exit with
no visible error are both distinguishable. What is *not* the verdict is any grep of the log: the
same FAQ forbids judging root cause from a filtered stream (`0345`).

Three guards. First — the input that makes this checker go red — each arm is preceded by a control
build that **must** succeed: the same translation unit with the Reg call removed, under the same
flags. If the control fails, the failure under test is not attributable to the declaration position
at all, and every cell in that arm is void. Without it, a project misconfiguration reproduces
upstream's predicted table exactly and for the wrong reason. Second, every successful build is
checked for the *presence of the VF path* in the produced object, not merely for a zero exit — the
FAQ's own delivery checklist requires it (`性能测试二进制仍包含所宣称的 Reg VF 路径`), because a
silently degraded build is the failure this whole subject exists around. Third, no cell's verdict is
issued from a rerun with a different toolkit than the one recorded beside it; the pin travels with
every row.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement and nothing was compiled. No
command line was classified, no probe was built, and the `kernel_macros.h` / `kernel_operator_intf.h`
behaviour described in §3 is upstream's account of CANN 9.1.0, which is not the version installed
here and was not read.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entire content is one document's account of a toolchain, scoped by that
document to `CANN 9.1.0 / bisheng clang 15.0.5 / dav-3510 (Ascend950PR)` — a version not installed
on this machine — with `其他版本以实际编译器为准`. So even the header-level mechanism (the empty
`AscendC::Reg` namespace, the conditional include of the reg-compute interface) is unverified here;
`950:0352` establishes the arch gate on the installed 9.0.0-beta.2 from the other direction and is
cited, not merged. The four contracts are upstream's taxonomy and no command line was classified by
it. The function-scope `static constexpr` rule is stated as what a target project verified, not as a
language requirement, and its two stated reasons (host-pass visibility, static storage duration for
a reference template parameter) are arguments rather than observations. Nothing establishes what
happens under `cce_wrapper`, whose row instructs continued investigation rather than a conclusion.
`vf_preflight.py`, `run_reg_cast_probe.py` and `catalog.json` are named and were not run or read.
BOARD is `family-claimed(unverified)`: a build contract is a property of a command line, not of a
board, and no board was contacted. Nothing transfers to the other book (RULES.md Art. 1) — the Reg/VF
surface is stated by upstream to be arch35-era.

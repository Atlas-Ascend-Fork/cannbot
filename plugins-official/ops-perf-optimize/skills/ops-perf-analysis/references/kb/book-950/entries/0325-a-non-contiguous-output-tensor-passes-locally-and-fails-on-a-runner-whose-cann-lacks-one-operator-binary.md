```
ID:        0325-a-non-contiguous-output-tensor-passes-locally-and-fails-on-a-runner-whose-cann-lacks-one-operator-binary
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/precision_and_traps.md:59-76 —
           "**症状**：报"精度不达标"，但同时给出 `MERE = 0.000000, MARE = 0.000000` —— 数值其实完全
           正确。" · "AclNN_Inner_Error(EZ9999): Op StridedSlice does not has any binary." ·
           "**机理**：评测框架对输出做 `output.cpu()`，非连续张量要先 `OptimizeContiguous` → 调
           `StridedSlice`，而部分 CANN 包（实测 950PR runner 的 **9.1.0-beta.1**）**没有
           `StridedSlice` 的算子二进制**。开发机上的 9.2.0 有，所以**本地怎么测都测不出来**。" ·
           "**踩过的具体形态**：... 把 int32 workspace 的低 16 位用 `as_strided(sizes, stride×2)`
           直接当输出返回。**本地四项回归全绿、分数还更高（73.54 / 20-20），平台 7/20、41.31。**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950PR runner on CANN 9.1.0-beta.1 that materialises a non-contiguous output through
           `.cpu()` without error — the missing `StridedSlice` binary would then not be the cause,
           and the failure recorded here would have some other origin.
```

# 0325 · A non-contiguous output tensor passes locally and fails on a runner whose CANN lacks one operator binary

## 1 · Claim
Upstream asserts a failure it met and diagnosed. Returning a non-contiguous view as an operator's
output — in the specific case, the low 16 bits of an int32 workspace exposed via
`as_strided(sizes, stride × 2)` to skip an unpack pass — is legal locally and fails on the
evaluation platform. The mechanism upstream asserts: the framework calls `output.cpu()`, a
non-contiguous tensor must first go through `OptimizeContiguous`, which dispatches `StridedSlice`,
and the CANN package on the 950PR runner (upstream names `9.1.0-beta.1`) ships no `StridedSlice`
operator binary, while the development machine's 9.2.0 does. Upstream asserts the symptom is
misleading in a specific way: the report says precision failed while simultaneously printing
`MERE = 0.000000, MARE = 0.000000`, because the numbers were correct and the transfer was not. The
real cause appears only deep in the log as
`AclNN_Inner_Error(EZ9999): Op StridedSlice does not has any binary`. Upstream asserts the outcome:
locally four regression suites green and a higher score (73.54, 20/20); on the platform 7/20 and
41.31. Upstream asserts the rule that follows — always return a contiguous tensor such as
`torch::empty_like(data)` and pay the unpack pass. Not established here.

## 2 · The wrong branch this removes
The optimisation is genuinely attractive: an unpack pass over the whole output is real work, and a
strided view removes it for free. Every local signal says it worked, including the score.

The branch this entry blocks is trusting a green local regression as evidence about the platform,
and it blocks it with a mechanism rather than an exhortation. The difference between the two
environments is not the hardware and not the kernel — it is which operator binaries the CANN package
carries. That is invisible to every check an engineer would naturally write, because it is not a
property of the code under test.

The second wrong branch is the diagnosis. `MERE = 0.000000, MARE = 0.000000` next to "precision
failed" is a contradiction, and the natural reading is that the harness is broken. It is not; it is
reporting two different stages. An agent that stops at the contradiction never reaches the
`EZ9999` line, and an agent that greps the log for "precision" or for its own operator's name will
not find `StridedSlice` in what it retained. This is the same discipline the shelf's build FAQ
states for compilers (`0345`): read the whole unclipped log and take the first real error, not the
one that matches your hypothesis.

The third wrong branch is the general one and it is why this entry is not a scatter fact. Any
optimisation that changes the *shape or layout contract* of an operator's output — a view, an
alias, a reused workspace, an in-place result — moves work out of the kernel and into the framework,
and the framework's cost is environment-dependent in ways the kernel's is not.

## 3 · Ground / Source
`scatter/precision_and_traps.md:59-76`, the whole trap:

```
## 3. 陷阱 1：输出必须是连续张量

**症状**：报"精度不达标"，但同时给出 `MERE = 0.000000, MARE = 0.000000` —— 数值其实完全正确。
日志深处才是真因：

AclNN_Inner_Error(EZ9999): Op StridedSlice does not has any binary.
RuntimeError: copy_d2d_baseformat_opapi ... device error type 0, error code is 561103

**机理**：评测框架对输出做 `output.cpu()`，非连续张量要先 `OptimizeContiguous` → 调
`StridedSlice`，而部分 CANN 包（实测 950PR runner 的 **9.1.0-beta.1**）**没有 `StridedSlice` 的
算子二进制**。开发机上的 9.2.0 有，所以**本地怎么测都测不出来**。

**踩过的具体形态**：为省掉打包键路径的 unpack pass，把 int32 workspace 的低 16 位用
`as_strided(sizes, stride×2)` 直接当输出返回。**本地四项回归全绿、分数还更高（73.54 / 20-20），
平台 7/20、41.31。**

**规避**：输出一律返回 `torch::empty_like(data)` 这类连续张量，unpack 那一趟老实付掉。
```

The regression net this defeated, `:88-101`, is worth carrying because it is the best-designed test
suite anywhere in this shelf and it still missed:

```
| 测试 | 组数 | 拦的是什么 | 需要 NPU |
| CPU 语义模拟器 | 50 | 逐行复现 kernel 的索引算术与遍历顺序，与 torch golden 严格对拍。拦语义错 | 否 |
| 通用路径回归 | 147 | 非 dim 维范围不等的所有组合（陷阱 2） | 是 |
| **输出连续性** | 200 | 断言 `is_contiguous()` **并真的调 `.cpu()`**（陷阱 1） | 是 |
| 完整评测 | 20 | 精度 + 性能总分 | 是 |

> 第三项的关键在**真的调 `.cpu()`**。只断言 `stride` 不够 —— `as_strided` 那次的 stride 检查是能
> 过的，只有真正触发 D2H 拷贝才会踩到缺失的 `StridedSlice` 二进制。
> **回归要复现的是"平台会做的那个动作"，不是"我认为等价的那个检查"。**
```

That last sentence is the entry's transferable content, and it is a statement about test design that
this book's own Art. 5 says the same way from the other side: a check that reads only the lines it
expects is the known blind species. A `stride` assertion is such a check — it reads the property the
author *thinks* matters. `.cpu()` is the platform's own action, and only it reaches the missing
binary. The 200-case suite exists because the first version of it asserted `stride` and passed.

The score pair `73.54 / 20-20` locally against `7/20, 41.31` on the platform is upstream's evidence.
It is a two-environment comparison with more than one variable (CANN 9.2.0 versus 9.1.0-beta.1, and
also two different machines), so it establishes that something environmental caused it; the
`StridedSlice` attribution comes from the log line, not from the score difference.

Measured/inferred split: **measured** — the two score pairs, the `MERE`/`MARE` zeros, the log lines.
**not measured** — that 9.1.0-beta.1 specifically lacks the binary while 9.2.0 has it (upstream says
`实测`, but reports no inventory of either package); that this is the only such missing binary.

One partial read was done here, under the phase-1 read-only exception, and it is reported for what
it is rather than as support. The installed CANN `9.0.0-beta.2` on this machine carries
`strided_slice.py` and eight sibling TBE implementations under
`opp/built-in/op_impl/ai_core/tbe/impl/ops_legacy/`, and its precompiled kernel tree
(`opp/built-in/op_impl/ai_core/tbe/kernel/`) contains directories for `ascend910b` and
`ascend910_93` **and no 950 SoC directory at all**, with no `strided_slice` kernel directory under
either. That is consistent with upstream's mechanism — operator binary availability is a property of
the package and is enumerable — and it is *not* evidence about upstream's runner: this is a
different package version, on a different machine, whose kernel tree ships no 950 entries whatever,
so it cannot distinguish "this operator is missing" from "this whole architecture is missing here".
Recorded so that §4 Arm 1's method is known to work and its result is known not to have been
obtained on a relevant package.

## 4 · Procedure
Proposed, runnable later on a named 950 board with a named CANN pin. Never run in this phase. The
claim is about an environment difference, so the procedure varies the environment and nothing else.

Arm 1 — the binary inventory, which needs no device and is marked `[no-card]`. For each CANN package
available on this machine, enumerate the `StridedSlice` operator binaries under the OPP path
(`$ASCEND_OPP_PATH`), recording package version and result. Upstream's mechanism predicts presence
in 9.2.0 and absence in 9.1.0-beta.1. This is the cheapest half of the whole entry and it has **not**
been run; recorded as owed in `harvest/standing/950-bp.md`.

Arm 2 — the failure, reproduced. On a pinned CANN package that Arm 1 shows lacks the binary, return
a deliberately non-contiguous output from a trivial operator and call `.cpu()` on it. Capture the
full unclipped log. Verdict is whether `EZ9999 ... StridedSlice ... does not has any binary` appears
and whether the numerical comparison simultaneously reports zero error.

Arm 3 — the fix, confirmed. The same operator returning `torch::empty_like(data)` with an explicit
unpack pass, on the same package. Record correctness and the unpack pass's cost as a share of kernel
time — the cost side must travel with the rule, or the rule reads as free.

Arm 4 — the test-design claim, which is the part worth generalising. Run both the `stride`-assertion
check and the `.cpu()` check against Arm 2's non-contiguous build. Upstream asserts the first passes
and the second fails. If both fail, the cheaper check would have been adequate and upstream's
methodological point is weaker than stated; if both pass, Arm 2 did not reproduce.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard the case if the die moved. Refuses to
assume: that a free die stays free; that a die may be substituted; that "the CANN package" is one
thing — the package version, the OPP path, the runtime version and the driver version are each
recorded separately, because upstream's own two-environment comparison confounds at least two of
them; that a log line seen once is the first error (the whole stream is captured with
`set -o pipefail` and `tee`, per `0345`).

## 5 · Checker — acceptance declared before the run
Verdict `binary_present[pkg]` from Arm 1, per package. No pass condition; the inventory is the
deliverable and it is what lets a future agent predict the failure instead of meeting it.

Verdict `repro` = true iff Arm 2 produces the `StridedSlice ... does not has any binary` line.
Declared before the run: a failure *without* that line is `void`, not a reproduction — the
diagnosis, not the failure, is what this entry carries.

Verdict `zero_error_paradox` = true iff Arm 2's numerical comparison reports zero error while the
run is scored as failed. This is the misleading symptom and confirming it is what makes the entry
useful to someone reading a report.

Verdict `stride_check_passes` = true iff Arm 4's `stride` assertion passes on the build that
`.cpu()` fails.

The exit code is not the verdict; upstream's whole point is that the framework reported failure and
the numbers reported success, so a single status is exactly the thing that misleads. Both are
recorded separately.

Three guards. First — the input that makes this checker go red — Arm 2 is run first with a
**contiguous** output on the same package, which **must** succeed. If the contiguous control also
fails, the package is broken in some other way and every verdict is void; the non-contiguous
failure would be unattributable. That control is the positive fixture and it is the cheap one.
Second, Arm 4 is mandatory, not optional: without it the entry's transferable claim (a `stride`
assertion is not a substitute for the platform's action) has no evidence, and it is the claim most
worth transferring. Third, the unpack pass's cost is reported with the rule; a correctness rule
quoted without its cost gets re-litigated by the next person who wants the score back.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `73.54 / 20-20`, `7/20`,
`41.31`, the `MERE`/`MARE` zeros and both log lines are upstream's readouts on its own runners; this
book has enumerated no operator binaries and called no `.cpu()`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled, and Arm 1 — an inventory that needs no device — was not run.
Upstream's two-environment comparison confounds the CANN version with the machine, so the
`StridedSlice` attribution rests on the log line rather than on the score difference; this entry
carries the attribution as upstream's diagnosis, not as an established fact. It does not establish
that 9.1.0-beta.1 lacks the binary in general — upstream reports one runner — nor that 9.2.0 has it
on any machine other than upstream's. It does not establish that `StridedSlice` is the only operator
binary a package may lack, and the general hazard (a framework-side dispatch whose availability
varies by package) is exactly as large as the set of such operators, which nobody here has
enumerated. The unpack pass's cost is never stated by upstream, so the rule's price is unknown.
The scoring figures belong to a specific evaluation harness that is not present in this tree and
cannot be reproduced from it. BOARD is `950PR`, the runner upstream names; nothing is established
for 950DT. Nothing transfers to the other book (RULES.md Art. 1).

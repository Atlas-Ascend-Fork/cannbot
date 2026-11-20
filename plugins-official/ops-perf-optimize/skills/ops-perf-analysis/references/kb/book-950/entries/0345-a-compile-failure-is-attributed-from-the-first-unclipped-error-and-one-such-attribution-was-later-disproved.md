```
ID:        0345-a-compile-failure-is-attributed-from-the-first-unclipped-error-and-one-such-attribution-was-later-disproved
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/regbase/cann_version_compat_faq.md:283-290
           — "**遇到编译错误时禁止臆断为"编译器 bug"或"编译器不支持 X"。**" · "1. **保存完整原始日志
           和真实退出码**：使用 `set -o pipefail` 与 `tee`，禁止通过 `grep/head/tail` 裁剪后再判断
           根因。记录构建命令、环境和 `PIPESTATUS`。 2. **读 stderr 的第一个 `error:` 行**。后续
           error、`Aborted (core dumped)` 和 `SelectionDAG::LegalizeTypes` 等栈帧可能只是连带结果 ...
           3. **保持 SDK 不变并最小化复现** ... 每次只改变一个变量 ... 5. **做同环境反例扫描** ...
           6. 只有同时保存"可重复命令 + 未裁剪 stderr + 最小复现 + 修复/规避复验"后，才能记录为
           兼容性问题或降级依据。"
SOURCE:    same file:292-302 — "### 反例：误判为编译器段错误 / **历史教训**： 实施 agent 拷贝 VF
           模板后遇到 include 路径、内部 mask 写法和配套 TilingData 缺失等多个错误，未逐一定位首个
           真实错误，却记录为"编译器在递归模板实例化时段错误"，并据此放弃整条 VF 路径。 /
           **实际验证**：将被指认的递归模板单独做最小复现后编译**通过**，无 segfault。这只能排除
           "该递归模板必然崩溃"；原始失败仍须按首个未裁剪 `error:` 逐项定位。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a compile failure on a named 950 toolkit whose first unclipped `error:` is demonstrably
           a consequence of a later one — the first-error rule would then not be sound as stated and
           would need a qualifier about diagnostic ordering.
```

# 0345 · A compile failure is attributed from the first unclipped error, and one such attribution was later disproved

## 1 · Claim
Upstream asserts a six-step protocol for attributing a compile failure and forbids the two
conclusions an agent reaches without it — "compiler bug" and "the compiler does not support X".
Save the complete raw log and the true exit code, using `set -o pipefail` and `tee`, recording the
build command, the environment and `PIPESTATUS`, and never judge root cause from a log trimmed by
`grep`, `head` or `tail`. Read the **first** `error:` line in stderr; later errors,
`Aborted (core dumped)` and stack frames such as `SelectionDAG::LegalizeTypes` may be consequences
and cannot on their own establish a cause. Reproduce minimally with the SDK unchanged, using the
real flags, changing one variable at a time. Look up the API read-only from the include root the
actual command resolves, never from a remembered path. Scan the same environment for
counter-examples — a baseline or sibling operator already using the same API or pattern and
producing a compiled `.so` — and where one exists, do not generalise to a version incompatibility.
Only with a repeatable command, an unclipped stderr, a minimal reproduction and a verified
fix-or-workaround may the case be recorded as a compatibility problem or as grounds for degrading.

Upstream asserts a case in which this failed. An implementing agent copied a VF template, met
several errors at once — include paths, an internal mask spelling, a missing companion TilingData —
did not locate the first real one, recorded the failure as a compiler segfault during recursive
template instantiation, and abandoned the whole VF path on that basis. Upstream asserts the
correction: compiled alone as a minimal reproduction, the accused recursive template **built
cleanly, with no segfault**. Upstream asserts the limit of that correction, and this is the part
worth carrying: it only excludes "that template necessarily crashes"; the original failure still
has to be attributed from its own first unclipped `error:`. Not established here.

## 2 · The wrong branch this removes
The wrong branch is a *conclusion*, and it is the most expensive one available: retiring a
capability. "The compiler does not support this" ends the investigation, gets written into a lessons
file, and is then cited by later agents as a prohibition — upstream's own follow-up rule is that a
lesson may not be cited as a ban until a counter-example scan has been run
(`引用 lesson 作为禁令前必须做反例扫描`).

Three mechanisms produce it, and the protocol answers each.

A **trimmed log**. Filtering for the pattern you expect returns the pattern you expect. The step is
worded strongly — `禁止通过 grep/head/tail 裁剪后再判断根因` — and it is the same species this book
records as a check that reads only the lines it expects.

A **later diagnostic read as a cause**. `Aborted (core dumped)` and a `SelectionDAG` frame look like
compiler internals failing, and they are the *loudest* thing in the log. Upstream's ordering rule —
first `error:`, not most alarming line — is what separates a cause from a cascade, and the disclosed
case is exactly that failure: an include-path error early, a crash later, and the crash was recorded
as the cause.

**Several variables at once.** The disclosed case had three independent defects. Fixing none of them
and observing the aggregate produces a symptom attributable to nothing.

The second wrong branch is over-reading the correction, and upstream blocks it in the same
paragraph. The minimal reproduction compiling cleanly does **not** mean the original build should
have worked; it means one hypothesis is dead. `这只能排除"该递归模板必然崩溃"` is a scope statement
about a negative result, and it is the sentence a reader is most likely to skip.

## 3 · Ground / Source
The protocol, `regbase/cann_version_compat_faq.md:281-290`:

```
## 调试方法：如何定位编译错误的真实原因

**遇到编译错误时禁止臆断为"编译器 bug"或"编译器不支持 X"。** 按以下步骤定位：

1. **保存完整原始日志和真实退出码**：使用 `set -o pipefail` 与 `tee`，禁止通过 `grep/head/tail`
   裁剪后再判断根因。记录构建命令、环境和 `PIPESTATUS`。
2. **读 stderr 的第一个 `error:` 行**。后续 error、`Aborted (core dumped)` 和
   `SelectionDAG::LegalizeTypes` 等栈帧可能只是连带结果，不能单独证明根因。
3. **保持 SDK 不变并最小化复现**：把报错代码抽到候选工程或临时隔离目录，用原构建的实际 flags 单独
   编译；每次只改变一个变量，如入口属性、编译模式、`__VEC_SCOPE__`、API 混用或 dtype。
4. **只读查 API 定义**：先从实际编译命令解析 SDK include 根目录，再用 `rg -n '<报错的 API 名>'
   <实际 include 根目录>` 查看真实签名和命名空间；禁止凭记忆拼 SDK 路径。
5. **做同环境反例扫描**：查基线及同仓算子是否已用相同 API/模式并产出编译通过的 `.so`。存在成功
   反例时，不得泛化为版本不兼容，须比较入口属性、真实 flags、include 链和高层 API/Reg API 混用。
6. 只有同时保存"可重复命令 + 未裁剪 stderr + 最小复现 + 修复/规避复验"后，才能记录为兼容性问题
   或降级依据。
```

The disclosed misdiagnosis, `:292-302`:

```
### 反例：误判为编译器段错误

**历史教训**：

实施 agent 拷贝 VF 模板后遇到 include 路径、内部 mask 写法和配套 TilingData 缺失等多个错误，未逐一
定位首个真实错误，却记录为"编译器在递归模板实例化时段错误"，并据此放弃整条 VF 路径。

**实际验证**：将被指认的递归模板单独做最小复现后编译**通过**，无 segfault。这只能排除"该递归模板
必然崩溃"；原始失败仍须按首个未裁剪 `error:` 逐项定位。

**教训**：
- `lessons/build.md` 的 `--cause` 必须直接引用 stderr 原文错误行（如 `error: 'MicroAPI' has not
  been declared`），不得写"编译器段错误"等无 stderr 佐证的概括性描述
- 引用 lesson 作为禁令前必须做反例扫描（grep 同工程是否已有该 API 编译通过的 `.so` 产物），发现
  反例则标记 `disputed`、不得引用为禁令
```

Three things about this passage are worth separating.

It is a **self-report of an error by the team that made it**, with the correction and the correction's
own limit stated. That is the register RULES.md Art. 9 requires (self-reports are
entries of honour), arrived at independently.

It converts the lesson into a **format constraint**: a lessons file's `--cause` field must quote a
verbatim stderr line. That is the difference between a rule that exists as prose and one that exists
where the work happens — a `--cause` that cannot be filled without a real error line cannot be filled
with a guess.

And it adds a **second-order rule**: before citing a lesson as a prohibition, scan for
counter-examples, and mark it `disputed` if one is found. A lessons file with no such rule
accumulates prohibitions monotonically, and each one was written on one bad afternoon.

The three named errors in the disclosed case — include path, internal mask spelling, missing
companion TilingData — are all documented elsewhere in the same FAQ (rows 10, 4 and the
`unknown type name '<TemplateTilingData>'` section respectively), which means the agent had three
independently documented defects and produced one undocumented conclusion.

The delivery checklist the protocol feeds, `:274-279`, closes the loop:
`同环境存在成功反例时，编译失败结论标记为 unconfirmed/disputed，直到最小复现确定差异`, and
`降级版本不得命名或报告为 reg_vf` — a degraded build may not be reported under the name of the
capability it degraded from, which is the reporting half of the same discipline.

Nothing here is measured or compiled by this book. Upstream reports one occurrence.

## 4 · Procedure
Proposed, runnable later. Never run in this phase — these arms need a **compiler**, which phase 1
permits no more than a device. The claim is about a diagnostic protocol, so the procedure tests the
protocol's discriminating power rather than any kernel.

Arm 1 — the first-error rule, with ground truth. Construct four translation units, each with exactly
one known defect: a bad include path, a `plt_b32`-era mask spelling (`0344` row 4), a missing
companion TilingData, and a namespace-level `CastTrait` under `xasc_combined` (`0343`). Build each,
capture the full unclipped stderr with `set -o pipefail` and `tee`, and check whether the first
`error:` line names the planted defect. Four for four is the protocol working on single defects.

Arm 2 — the cascade, which is where the disclosed failure lived. Build one unit carrying **all
three** of the disclosed case's defects simultaneously. Record the full log and ask two questions:
does the first `error:` name one of the three, and does any later frame resemble a compiler internal
failure? Upstream's account predicts both. If the first error is *not* one of the three, the rule
does not hold under this compiler and the OVERTURN fires.

Arm 3 — the trimming failure, demonstrated rather than asserted. Apply three plausible filters to
Arm 2's log — `grep -i error`, `tail -50`, `grep <the API name>` — and record what conclusion each
supports. This arm produces the concrete cost of step 1's prohibition, which is currently a rule
with no example attached.

Arm 4 — the counter-example scan. Take one API this shelf's lessons might ban and scan the machine
for a compiled artefact using it. The scan's *method* is the deliverable: what counts as a
counter-example, how a `.so` is inspected for the symbol, and what is recorded when none is found.

Arm 5 — the disclosed reproduction, repeated. Extract the recursive template alone and build it with
the real flags. Upstream reports it passes. A pass here confirms the correction on this toolkit; a
failure would mean the template does crash on 9.0.0-beta.2 and upstream's correction is
version-specific.

Toolchain provenance recorded per arm: the invocation, `--npu-arch`, include roots from
`compile_commands.json`, `compiler/version.info`, and `PIPESTATUS`. No SDK file is modified. Refuses
to assume: that stderr and stdout interleave deterministically (both are captured, separately and
combined); that an exit code of zero means success (Arm 1 records exit code and error presence
independently, since a build can emit `error:` text and exit zero, and can exit non-zero silently);
that a "minimal" reproduction is minimal because it is short — each removal is a separate build and
the failure must persist across it.

## 5 · Checker — acceptance declared before the run
Verdict `first_error_correct[i]` for Arm 1's four units, true iff the first unclipped `error:` names
the planted defect. Declared before the run: the protocol is **supported** iff all four are true.

Verdict `cascade_first_error` from Arm 2 — which of the three defects, or none.
Verdict `cascade_has_internal_frame` — true iff a compiler-internal-looking frame appears anywhere
in the log. Both are reported together, because the entry's whole subject is that the second is
louder than the first.

Verdict `filter_conclusion[f]` for each filter in Arm 3 — what a reader would conclude from that
view alone.

Verdict `recursive_template_builds` from Arm 5.

The exit code **is** part of the verdict here — these are build experiments — and is recorded
alongside `PIPESTATUS` and the unclipped stream. What is never the verdict is any filtered view of
the log; Arm 3 exists to show why, and its outputs are evidence about the filters, not about the
build.

Three guards. First — the input that makes this checker go red — Arm 1 includes a fifth unit with
**no** defect, which must build cleanly and produce no `error:` line. If the harness reports a first
error for a clean build, its error extraction is matching something that is not an error (a path
containing the word, a warning, a comment) and every verdict in the run is void. That planted
negative is the cheapest fixture available and it guards the one thing every other verdict depends
on: that "the first `error:` line" is being read correctly.

Second, Arm 1's four defects are each independently documented in the same FAQ, so a first-error
verdict that names something else is a finding about the compiler, not about the fixture.

Third, no arm's conclusion is recorded without the four artefacts upstream's step 6 requires — a
repeatable command, an unclipped stderr, a minimal reproduction and a verified fix. An entry in this
book that recorded a compatibility conclusion on less than that would be violating the rule it is
carrying.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement and nothing was compiled. No
log was captured, no defect was planted, and the recursive template upstream exonerates has not been
built here. The one occurrence upstream reports is a self-disclosure about its own past work on an
unnamed toolkit; this book has reproduced neither the failure nor the correction.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The protocol is upstream's and is untested here; its six steps are stated with
one supporting anecdote and no measurement of how often each step changes an outcome. The disclosed
case reports **one** misdiagnosis — that establishes that it happened, not a rate, and not that the
protocol would have prevented it. The correction's own limit is upstream's and is carried verbatim:
the recursive template building alone excludes only that it necessarily crashes, and the original
failure was never attributed in any account available here. The first-error rule assumes diagnostics
are emitted in dependency order, which is a property of a compiler and is asserted by nobody. The
FAQ is scoped to `CANN 9.1.0 / bisheng clang 15.0.5 / dav-3510 (Ascend950PR)`, and this machine
carries 9.0.0-beta.2. `lessons/build.md`, its `--cause` field and the counter-example scan tooling
are named and are not present in this tree. Nothing here establishes what a counter-example scan
should accept as a counter-example. BOARD is `family-claimed(unverified)`: a build protocol is a
property of a toolchain, not of a board, and no board was contacted. Nothing transfers to the other
book (RULES.md Art. 1).

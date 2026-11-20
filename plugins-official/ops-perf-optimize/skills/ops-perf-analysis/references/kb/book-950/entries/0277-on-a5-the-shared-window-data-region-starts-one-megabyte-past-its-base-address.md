```
ID:        0277-on-a5-the-shared-window-data-region-starts-one-megabyte-past-its-base-address
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-mc2-best-practice), stated in two files of
           that skill. Nothing was compiled and no window was read.
BOARD:     family-claimed(unverified)
           # upstream scopes it by compile macro (`__NPU_ARCH__ == 3510`) rather than by board
           # token, and no board was contacted.
SOURCE:    ops/ascendc-mc2-best-practice/references/moe-dispatch-combine/api-rules/mte-address-access.md:225-241
           — "### A5 平台（`__NPU_ARCH__ == 3510`）" … "A5_MTE_STATE_WIN_SIZE = 1024UL * 1024UL /
           状态区位于前 1MB，数据区位于这 1MB 之后" … "- 数据区基址：`windowsIn[rankId] +
           A5_MTE_STATE_WIN_SIZE` / - 因此 A5 平台拿数据区地址时必须额外跳过前 1MB 状态区"
SOURCE:    same file:355 — "1. **A5 数据区偏移 1MB**：A5 平台数据区基址 = `windowsIn[rankId] + 1MB`，
           不加偏移将读写到状态区。"; :365 — "6. **读取本地状态区必须走 GM 可见路径**：不能在 `SyncAll`
           后直接 `GetValue()` 读取共享状态，必须先搬回 UB 再读取。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an A5 MC² kernel that reads correct payload from `windowsIn[rankId]` with no 1 MB offset
           — the state region would then not occupy the head of the window, and every kernel written
           to this rule would be reading 1 MB into its own payload.
```

# 0277 · On A5 the shared window's data region starts one megabyte past its base address

## 1 · Claim
Upstream asserts that on the A5 platform (`__NPU_ARCH__ == 3510`) a rank's shared communication window,
addressed as `windowsIn[rankId]`, contains **both** a state region and a data region, laid out with the
state region occupying the first 1 MB — the constant `A5_MTE_STATE_WIN_SIZE = 1024UL * 1024UL` — and the
data region following it. Upstream asserts the operative consequence: the data-region base address is
`windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE`, and a kernel that omits the offset reads and writes into
the state region. Upstream asserts a second, separate rule for the state region: it must be read through
a GM-visible path — copied back into UB first — and never with a direct `GetValue()` after `SyncAll()`.
Not established here: nothing was compiled and no window was read.

## 2 · The wrong branch this removes
`windowsIn[rankId]` is a base address and reads like one. Nothing in its name or type says the first
megabyte belongs to something else, and the natural code — take the pointer, apply the layout formula,
copy — is wrong by exactly 1 MB.

The failure is unusually bad in two ways. It is a *silent cross-purpose write*: the kernel does not fault,
because the state region is mapped memory belonging to the same window. It writes payload over the
synchronisation state that the collective is using to coordinate. So the symptom is not a wrong tensor —
it is a hang, or a partner rank proceeding on a flag it never set, or an intermittent corruption whose
shape changes with rank count. That is the hardest class of MC² bug to attribute, because it presents as
a communication fault rather than as an addressing error.

And it is **rank-dependent**: every rank does it, so the state regions of all ranks are being overwritten
simultaneously, which makes the failure look like a distributed protocol problem rather than a
per-kernel offset bug.

The second branch is the platform split. Upstream documents A3 and A5 as different layouts — on A3 the
local state region is `localWindowsExp` and the local data region is `localWindowsIn`, two separate
pointers; on A5 both live in one `windowsIn[rankId]` allocation with state first. So a kernel ported from
A3 has *two* things wrong: it looks for a second pointer that does not exist, and if it falls back to the
one it has, it lands on the state region. Upstream states this directly at `:365`, item 5: "本地状态区和
本地数据区不是一回事".

The third branch is the state-region read rule, which is a different mechanism with the same
consequence class. Reading shared state with `GetValue()` after `SyncAll()` looks correct — the barrier
completed, so the value should be visible. Upstream says it must be staged through UB first. An agent
that reasons "SyncAll has fence semantics, therefore the read is safe" has the right premise and the
wrong conclusion, and the failure is again intermittent.

## 3 · Ground / Source
`mte-address-access.md:225-241`, the A5 platform section in full:

> ### A5 平台（`__NPU_ARCH__ == 3510`）
>
> `HcclOpParam = HcclA5OpResParam`，相关常量和字段展开如下：
>
> ```
> HcclA5OpResParam
>     .windowsIn[rankId]              → 每张卡的完整 window 起始地址（包含状态区 + 数据区）
>
> A5_MTE_STATE_WIN_SIZE = 1024UL * 1024UL
>     状态区位于前 1MB，数据区位于这 1MB 之后
> ```
>
> - 每张卡的完整 window 起始地址：`windowsIn[rankId]`
> - 状态区基址：`windowsIn[rankId]`
> - 数据区基址：`windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE`
> - 因此 A5 平台拿数据区地址时必须额外跳过前 1MB 状态区

Note that the state base and the window base are the *same address*. That is what makes the omission
undetectable by inspection: a kernel using `windowsIn[rankId]` as its data base is using a valid,
correctly-typed pointer to the right allocation.

The scoping is by compile macro, `__NPU_ARCH__ == 3510`, not by board name — which is the correct fence
per 0202 (the four-digit macro is exact; the `arch35` abbreviation is not) and is why this entry's BOARD
is `family-claimed(unverified)` rather than a 950 token: upstream names the architecture, not the part.

The summary list at `:355-365` restates it first among seven pitfalls and adds the neighbouring rules:

> 1. **A5 数据区偏移 1MB**：A5 平台数据区基址 = `windowsIn[rankId] + 1MB`，不加偏移将读写到状态区。
> 2. **A3 远端访问通过链表**：A3 远端 rank 地址通过 `remoteRes[rankId].nextDevicePtr` 间接获取，
>    不是数组直接索引。
> …
> 5. **本地状态区和本地数据区不是一回事**：A3 平台本卡状态区是 `localWindowsExp`，本卡数据区是
>    `localWindowsIn`；A5 平台两者共享同一块 `windowsIn[rankId]` 基址，但状态区在前、数据区在后。
> 6. **读取本地状态区必须走 GM 可见路径**：不能在 `SyncAll` 后直接 `GetValue()` 读取共享状态，
>    必须先搬回 UB 再读取。
> 7. **先拿 window 基址，再套 layout 公式**：`winContext` 不会直接给你某个 slot 的最终地址，
>    它只提供 window 基址；真正的 slot 地址还要结合 `window-memory-layout.md` 里的布局公式计算。

Item 7 places this entry in the chain: the 1 MB offset gets you to the data region's base, and the slot
address inside it still requires the layout formulas in `window-memory-layout.md` — which this harvest
did not mine. So this entry covers one term of an address computation, not the computation.

Two warnings from the same file bound how much of this is stable. `:20` records that the sample's
`HcclA5OpResParam` is a **精简定义** covering only the fields the sample touches, that the real SDK
structure carries more intermediate fields, and that field offsets after `winExpSize` therefore differ —
"sample 中的定义仅适用于 mock/test 场景（自建 context），**不适用于解析真实 HCCL 返回的 context**".
And `:22` states the principle that survives the struct churn: "这里最重要的不是'工程里用了什么结构体
名字'，而是'当前平台下 `mc2Context` 的字段布局是确定的，kernel 解析时必须与 HCCL 返回的结构保持一致'".

That matters for this entry's durability: the *constant* (1 MB) and the *layout* (state first) are the
claim; the struct name and field offsets around them are explicitly declared unreliable in the sample.

`:62` records the debugging affordance worth keeping: the host can copy `mc2Context` back and print
`rankId`, `rankDim`, `winSize`, `windowsIn[]` to confirm the real window structure on the platform — not
a required step, but the one that would have caught this.

## 4 · Procedure
Runnable later on a named 950 board with at least 2 cards. The claim is an address-layout fact, so the
procedure reads the window rather than timing anything.

Arm A — the layout, read from the host, no kernel needed. Following `:62`, copy `mc2Context` back to the
host and print `rankId`, `rankDim`, `winSize` and `windowsIn[]`. Then, with a known payload written by a
partner rank at the documented data base, dump the first 2 MB of `windowsIn[rankId]` from the host and
locate where the payload actually begins. The offset of the first payload byte is the readout — the whole
claim in one number, and it needs no kernel-side reasoning.

Arm B — the omission, made observable. Build one MC² dispatch kernel twice: once with the data base at
`windowsIn[rankId] + A5_MTE_STATE_WIN_SIZE`, once at `windowsIn[rankId]`. Run both on the same card group
in the same session with identical input. Record for the second: does it hang, does it produce wrong
output, does the partner rank's state region contain payload bytes. §2 predicts a hang or an intermittent
corruption rather than a clean wrong answer, and distinguishing those is the finding — a clean wrong
answer would be much easier to diagnose than upstream's framing implies.

Arm C — the constant, not merely the offset. Sweep the assumed state-region size over 512 KB, 1 MB and
2 MB and locate the boundary at which correct payload begins, against the same known-payload setup as
Arm A. Upstream states 1 MB; a boundary at another value would mean the constant is
platform- or version-dependent rather than fixed, which changes whether it may be written as a literal at
all.

Arm D — the state-read rule, which is a separate mechanism sharing the failure class. After `SyncAll()`,
read a shared state word two ways — direct `GetValue()` and staged through UB — and compare, repeating 50
times at each of several rank counts. Upstream says the direct read is invalid; a non-deterministic
mismatch is the predicted signature, so a single comparison would miss it.

Device selection is explicit and stricter here because this is multi-card: the operator names every card
in the group, the harness prints them back with `compiler/version.info` and each resolved SoC string,
occupancy is checked on all of them before the run (shared machine, ≤4 dies), and no card is substituted
for another between arms. Arm B's no-offset build must run with a declared watchdog timeout and release
the cards on timeout — a hang is a predicted outcome and an un-timed arm would hold the group.

## 5 · Checker — acceptance declared before the run
Verdict variable `data_offset_bytes`, from Arm A: the offset at which partner-written payload actually
begins in `windowsIn[rankId]`. Pass iff it equals 1048576. Process exit code is not the verdict.

Named alternatives, declared now so none can be reinterpreted afterwards. An offset of 0 overturns this
entry — the state region does not occupy the head, and every kernel written to this rule is reading 1 MB
into its own payload, which is the mirror-image bug and worse than the one the entry warns about. Any
other non-zero value corrects the constant in place and is logged, and it moves the claim from "1 MB" to
"a platform-dependent offset that must be read from the context rather than written as a literal".

`omission_signature` (Arm B) — reported, not gated: hang, wrong output, or correct output, plus whether
the partner's state region contains payload bytes. Correct output from the no-offset build is a real
possible outcome — if the state region is smaller than 1 MB in practice and the payload happens to fit in
the gap — and it would mean the constant is a conservative reservation rather than a boundary.

`constant_is_fixed` (Arm C) — pass iff the boundary sits at 1 MB across all three sweep points, i.e. the
sweep confirms rather than merely fails to contradict.

`direct_state_read_is_unsafe` (Arm D) — true iff **any** of the repetitions shows a mismatch between the
direct and staged reads. One mismatch sets it true. A clean set does **not** establish that the direct
read is safe; it is reported as `not provoked`, because upstream's claim is about visibility semantics and
a passing observation cannot refute an invalid-but-usually-working access.

The positive fixture, declared before the run: Arm A must be run a second time with the partner rank
writing a *different, known* payload at a *different, known* offset inside the data region. The reported
`data_offset_bytes` must move by exactly that amount. If it does not move, the dump is locating something
other than the payload — a zero boundary, a struct field — and every offset it produced is void. A second
fixture for Arm B: the *offset* build must produce correct output on every run; if it does not, the
harness's MC² setup is broken independently of the offset and the no-offset result attributes nothing.
Without both, the checker reads only "payload was found somewhere", which is the known blind species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no window
was dumped, no `mc2Context` was copied back, and no card was contacted. The constant, the layout and the
consequence in §3 are upstream's assertions; no SDK header was read to confirm that
`A5_MTE_STATE_WIN_SIZE` exists under that spelling, and that check is a file read that remains open.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the 1 MB constant, the state-before-data
layout, or the consequence of omitting the offset — Arms A, B and C are open, and §5 declares in advance
that a no-offset build producing correct output would reframe the constant as a conservative reservation
rather than a boundary. There is **no second origin**: both quoted passages are one upstream skill, and
no installed header or SDK definition was consulted. It establishes **one term** of an address
computation, not the computation: upstream's item 7 says the slot address still requires the layout
formulas in `window-memory-layout.md`, which this harvest did not mine, so a kernel built from this entry
alone would reach the data region's base and no further. It does not establish anything about the
surrounding structure: upstream explicitly warns that the sample's `HcclA5OpResParam` is a reduced
definition, that the real SDK struct carries additional fields, and that offsets after `winExpSize`
therefore differ — so field access around this constant is declared unreliable by the source itself. It
says nothing about A3, whose layout uses two separate pointers and belongs to the other book's
architecture family (RULES.md Art. 1); the A3 rows quoted in §3 are upstream's contrast text only. It says
nothing about remote-rank addressing, which upstream states works differently again. The state-read rule
in Arm D is a distinct mechanism carried here because it shares the failure class, and it is equally
unverified. BOARD is `family-claimed(unverified)`: upstream scopes by `__NPU_ARCH__ == 3510` rather than
by part, and no card was contacted — a result on one 950 group would establish that group only.

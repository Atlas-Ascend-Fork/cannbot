# CARD · ascendc-mc2-best-practice 001 — the window accessors are sample compat helpers, not a vendor API

**BOOK: 950 — held as a card. Every MC² window address in `950:0389`–`950:0393` is computed from three
accessors that upstream states plainly are project sample code, not an HCCL kernel API. That provenance
changes what the entries can promise and it belongs on the record where a merge will see it.**

## The statement (verbatim, re-verified 2026-08-24)
`ascendc-mc2-best-practice/references/moe-dispatch-combine/api-rules/mte-address-access.md:277-279`:

> 本地工程里通常会提供一层 compat helper，例如：
>
> - 读取当前 rank / rank 数 / 单 rank window 大小
> - 读取本卡状态区基址
> - 读取指定 rank 的数据区基址
> - 读取指定 rank 的状态区基址
>
> 这些 helper 本质上是工程代码对 `winContext` 的一层适配，**不代表 HCCL 会直接提供同名 kernel API**。

and `:283`, naming the three:

> sample 的 `GetStatusDataSpaceGm`、`GetBaseWindAddrByRankId`、`GetBaseWindStateAddrByRankId` 属于这一层。
> 这里对应的是"数据区基址"和"状态区基址"分开封装，而不是在主流程里反复手写平台分支。

## Why this is a card
It is not a machine claim and it is not falsifiable: "these names are a project convention" has no
observable that could contradict it. But it qualifies four entries in this block and one in the previous
one, and dropping it would leave those entries reading as if they described a vendor interface.

**What it qualifies.** `950:0389` claims that the window layout formulas start from an accessor that has
already applied `950:0277`'s 1 MB skip. That claim's whole force is a *contract* — layer 2's stated job is
to return the data-region base, and on A5 the data-region base is defined as `windowsIn[rankId] + 1MB`. If
the accessor is sample code, the contract is a sample's contract, and a consuming team whose tree spells the
helper differently, or places the offset in layer 3, has a different answer. That is why `950:0389`'s Arm A
compares the accessor's **return value against the raw `windowsIn[rankId]` field** rather than trusting the
name — and this card is the reason it is written that way.

`950:0390`, `950:0391`, `950:0392` and `950:0393` all compute addresses and buffer sizes from those returns.
`950:0277` names `windowsIn[rankId]` and `A5_MTE_STATE_WIN_SIZE` directly and is the one item in the group
that touches the HCCL structure rather than the helper layer.

## The other provenance warnings in the same file, which point the same way
`:20` — the sample's `HcclA5OpResParam` is a **精简定义** covering only the fields the sample touches; the
real SDK structure carries more intermediate fields, so field offsets after `winExpSize` differ, and the
sample definition "仅适用于 mock/test 场景（自建 context），**不适用于解析真实 HCCL 返回的 context**".

`:22` — what survives the churn: "这里最重要的不是'工程里用了什么结构体名字'，而是'当前平台下 `mc2Context`
的字段布局是确定的，kernel 解析时必须与 HCCL 返回的结构保持一致'".

`:257` — the division of labour the whole group rests on: "`winContext` 只提供每张卡 window 的基址；真正的
数据区布局、状态区布局、slot 偏移，仍要由 layout 公式决定".

Together those say: the *layout formulas* are the durable part, the *struct definitions and helper names*
are not. That is a useful and unusually honest self-assessment, and it means `950:0390`–`950:0393`'s constants
(32-byte alignment, 12-byte triple, 32-byte state slot) are on firmer ground than `950:0389`'s composition
claim, which depends on a helper.

## The debugging affordance worth preserving
`:62` records that the host can copy `mc2Context` back and print `rankId`, `rankDim`, `winSize` and
`windowsIn[]` to confirm the real window structure on the platform. That single step is the recovery path
for every provenance problem above — it reads the real context rather than the sample's model of it — and it
is what `950:0389` Arm A, `950:0390` Arm E and `950:0391` Arm A all build on. It is stated once, in passing,
in a 374-line file.

## What is NOT recorded here
The four-layer decomposition (`:265-335`: context parsing, window base acquisition, business address
assembly, communication actions) is quoted in `950:0389` §3 as the source of the composition argument and is
not re-stated as a claim; it is an architecture description of the sample.

The A3 platform half — `localWindowsIn` / `localWindowsExp` as separate fields, remote ranks reached through
`remoteRes[rankId].nextDevicePtr` — is read and **not claimed anywhere**. A3 is `910_93`-era vocabulary by
`form/CONVENTIONS.md`'s map (Atlas A3 = DAV_2201 = the other book's family), so it is not this book's
material, and `950:0389` §7 says so explicitly.

## Guessed level
L0 (launch & host) for the helper layer; L3 for what it returns.

## Evidence class
bare, and unusually self-aware: the file states its own unreliability three times (`:20`, `:22`, `:279`)
and names the recovery step (`:62`). That is better evidence culture than most of the corpus and it is worth
noting as such rather than only as a limitation.

## OVERTURN sketch
Not applicable — this is a provenance record, not a claim. The measurement it *enables* is
`950:0389`'s Arm A / `Q-950rem-11`: print the accessor's return and the raw field and subtract. One printf
settles whether this particular sample's helper applies the 1 MB skip, and it settles it **for that tree
only**, which is the whole point of this card.

## Disposition
Card kept and **flagged for the delivered skill**. Any recommendation the replacement skill makes about MC² window
addressing must either name the helper layer as a project convention, or state the address in terms of
`windowsIn[rankId]` and the layout formulas directly. Stating it in terms of `GetBaseWindAddrByRankId`
without that qualification would hand the consuming team an interface upstream explicitly says HCCL does
not provide.

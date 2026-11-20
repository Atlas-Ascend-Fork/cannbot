# CARD · ascendc-tiling-design 004 — the FA family is a contract of must-answer questions, and its unfalsifiable half is carded here

**BOOK: 950 — the residue of the a later harvest pass `950-fin` harvest. Every quote below was re-verified against
its file at drafting time.** The FA family's falsifiable claims became `950:0451`–`950:0468`; what is
carded here is the part with no §4 — obligations a design must satisfy, checkable only by reading a
design document, with no observation that could show them wrong.

Why carded rather than entered: the harvest plan procedure) is the
load-bearing section: it must be runnable-later as written, on a named board, and must make the
OVERTURN observable. An entry whose §4 you cannot write is not ready — leave it a card."* Each item
below fails that test in the same way: violating it produces a worse *design document*, not a
different *measurement*.

All paths relative to `ops/ascendc-tiling-design/references/flashattention/`.

---

## The shape of the thing: a phase gate with a dependency chain

`design.md:10-24` is a nine-row must-produce table with a hard gate — `任一条目未产出 → 阻塞,不得进入
实现。` — followed at `:26-42` by an explicit top-down dependency chain with, upstream says, no forward
dependencies:

```
§2 宏观决策(架构 + 并行策略)
    ↓
§3 多核切分(在 §2.5 已选并行策略下)
    ↓
§4 内存划分(在 §2.1-§2.4 架构下)
    ↓
§5 编译宏(在 §4 内存划分下,判定依据 = TBuf 变化)
    ↓
§6 Host Tiling 决策(把 §2-§5 所有决策汇总成 Tiling 函数产出)
    ↓
§7 流水线编排(基于 §2.4 + §3 + §4 的节拍 / 同步 / barrier 一体)
    ↓
§8 开发起点(进入实现的最后准备)
```

**This chain is itself the family's most transferable idea and it is not an entry**, because nothing
observable follows from getting the order wrong — you would simply redo work. Worth stating for the
the delivered skill builder: it is a routing path a consuming agent can walk, and `plans/` Amendment §6 says
the delivered skill's routing files should chain entries into exactly such paths. `950:0466` records the one
place the chain is load-bearing (build targets derive from memory division, not from the feature list)
and that one has a §4.

---

## Item 1 — the six "list everything" produce-clauses

`design.md §4.1 Q1` (`:214-230`): every UB buffer with a name, a single-slot capacity formula and a
`depth`, under the constraint that formulas may contain only runtime-queried hardware constants,
tiling-decided base blocks and dtype widths — `**禁止**直接写数字` (`:208`, `:221`).
`§4.4 Q1` (`:348-356`): every GM workspace segment by responsibility class (five classes).
`§4.2 Q1`/`Q3`, `§4.3 Q1`/`Q2`: per-port L1 declarations and L0 capacity checks.

Falsifiable fragments already entered: the A1/B1 port assignment (`950:0457`), the `∝ m × D`
elimination (`950:0456`), the single-DataCopy-per-slot rule (`950:0458`), the runtime-`Sk` sizing
(`950:0459`). What remains is the *enumeration obligation* itself, which has no failure mode a run
could see.

**One fragment here is worth a later pass and was not entered for budget:** `:258` —
`sum 广播是否走 `BinaryRepeatParams(src1RepStride=1)` 在 Div 内自动消费,而非分配中间 buffer?` — the
only item on the elimination checklist with a concrete API-level remedy, and the one an agent would
not think of because a broadcast is normally materialised. It is measurable (buffer count, time) and
`950:0456` §4 arm 4 proposes it, so it is half-covered.

## Item 2 — §6's Host Tiling roster and decision dimensions

`design.md:440-451`: six field responsibility classes the returned `TilingData` must cover — base
block sizes, derived sizes, task dispatch parameters, workspace segment sizes, **hardware capacity
write-back**, and composite-API host tiling data. `:453-470`: the decision dimensions, including
prefill/decode streaming (`Sq = 1` favours filling the GQA group merge with `m` base block 1; large
`Sq` fills the task's `m` ceiling and the merge degenerates) and the chunk-rows formula already at
`950:0456`.

**The interesting row is `硬件容量回写`** (`:448`): `UB / L1_A / L1_B / L0 容量等,供 kernel 端容量校验,
避免 kernel 内再次查询`. Host queries the platform once and passes the capacities down in `TilingData`
so the kernel does not re-query. That is a real technique with a real cost model (tiling-data bytes
against kernel-side query latency) and it sits one shelf away from `950:0337`, which records the
opposite move — the cube side of a mixed A5 kernel *skipping* its TilingData copy by reading a shared
subset from `__ssbuf__`. **Two techniques in tension about how much tiling data should cross to the
device, in one repository, neither citing the other.** A later pass could make this an entry: §4 would
measure launch overhead and kernel-side query cost against tiling-data size. Not done here for budget.

## Item 3 — §6.4's dimension-opening order

`design.md:472-493`. Partly entered: the conjunction claim is `950:0462` and the mandatory large-`D`
gate (`不允许"只测小 D 就交付大 D"`) is quoted there. What is carded is the *order* itself —
`MVP → 非对齐/GQA/bf16 → causal → 多核 → 三级流水 → D 维度扩展` — which is a development discipline
with no measurable content, plus the asymmetry that the mandatory extreme-value gate is stated for `D`
alone and not for `mPad`, `s2N` or `Sk`, with no reason given.

## Item 4 — §8.1's baseline-first rule

`design.md:611-619`: before writing a custom kernel, compile and run at least one asc-devkit reference
example of the same kernel type, to confirm `__mix__(N, M)` + `TPipe` works under the current CANN
version. Three examples named, one of them A5-specific (`:617`, the `mode=4` sync base). **This is
good practice and it is a procedure, not a claim** — there is no observation that would show the rule
wrong. It is folded into `950:0451` §4 as a step of that entry's procedure rather than entered on its
own.

## Item 5 — §7.3's cache-slot naming rule

`design.md:541-548`: numeric suffixes forbidden (`info0`/`info1`/`info2`), semantic naming mandatory,
the format left open (`命名格式开放`) with only the recoverability property required — a reader must be
able to read the stage and the round off the name. Quoted inside `950:0465` because it is what makes
that entry's out-of-beat emission order auditable; not entered alone.

## Item 6 — `subfamilies.md`'s organisational contracts

`§2.1` ConstInfo single-source (`:41`, all subfamilies' fields in one struct, unconsumed fields keep
defaults); `§2.5` service-class organisation (Cube and Vector lines as separate service headers, MLA
must name its own, `禁止`复用默认 FA / GQA service 头`); `§5.1` subfamily-mixing ban (`:326`,
`不能"主要是 GQA 但在某些路径上走 MLA latent absorption"`). All three are code-organisation rules
whose violation produces maintenance cost, not a measurement. The mixing ban's *mechanical* reason —
the split-KV-reduce task descriptor is incompatible with the default `RunInfo` (`design.md:145`) — is
entered at `950:0454`.

## Item 7 — the sparse subfamily, which is a declared placeholder

`subfamilies.md:174-189`. Four extension points listed (ConstInfo sparse-pattern fields; the `s2` loop
possibly skipping KV chunks; workspace possibly needing a precomputed sparse index; whether Cube is
used at all, depending on whether the pattern is block-sparse or token-level). Then `蒸馏纪律`:
`本子族**仅占位**。落地第一个稀疏 FA 算子时再细化扩展契约——跨算子可复用前不固化具体规则。`

**Recording the absence as an absence is this project's rule, and this absence has a stated
discipline attached**, which is unusual: upstream says *why* it will not fix the contract yet (nothing
is reusable across operators until a second one exists). The same discipline appears at `:258-260` for
the quantised subfamily (`等第 2、第 3 个量化 FA 落地后,如果在 5 扩展点上出现稳定共性,可考虑把骨架
升级为完整契约`). Two declared placeholders with a stated promotion condition — worth an entry in a
later pass as a *boundary* about how this repository handles unfinished contracts, and it needs only
these two quotes.

---

## Evidence class
Methodology and obligations throughout. No measurement in the FA family except `design.md:80`'s
`典型 ≤ 5%` (`Q-950fin-04`), and the `实测教训` at `subfamilies.md:127` which reports the shape of a
result without the result (`950:0462`). Board tokens: `A5` at four sites (see
`harvest/standing/950-fin.md` E-1), none of them attached to a measurement.

## OVERTURN sketch (for the deferral)
Any of items 1-7 turning out to have an observable consequence — a design that satisfies the letter of
an obligation and measurably fails, or a case where the dependency chain's order changes a
measurement rather than only the work. Item 2's hardware-capacity write-back is the most likely
candidate and is the one this card recommends first.

## Disposition
Carded, not entered, with the reason above per Stage 2's own test. Two items are flagged as
promotable by a later pass with named §4 sketches: the `sum` broadcast remedy (item 1) and the
capacity write-back versus `__ssbuf__` forwarding tension (item 2, against `950:0337`). Mining freezes
after wave 1.9 (Amendment 4), so both are phase-2+ work. Recorded in `harvest/standing/950-fin.md`
under deliberate skips.

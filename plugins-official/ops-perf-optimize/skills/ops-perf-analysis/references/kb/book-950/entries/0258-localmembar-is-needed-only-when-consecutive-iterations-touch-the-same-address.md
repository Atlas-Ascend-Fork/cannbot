```
ID:        0258-localmembar-is-needed-only-when-consecutive-iterations-touch-the-same-address
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), stated in two files
           of that repo. Nothing was compiled and no ordering was observed.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:81-93
           — "`LocalMemBar<VEC_STORE, VEC_LOAD>()` 保证之前所有 VEC_STORE 写入对后续 VEC_LOAD 可见。
           仅作用于 Vector 单元内部。" with the five-row 场景/是否需要 table and
           "**常见错误**：在标准 elewise 循环末尾加 `LocalMemBar` 是多余的——每次迭代目标地址都不同。"
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:265-273
           — "### 2.4 VF LocalMemBar / LocalMemBar 是 VF 函数（`__simd_vf__`）内部的同步指令，用于 Reg
           矢量计算中 UB 读写流水线间的保序。/ template <MemType src, MemType dst>
           __simd_callee__ inline void LocalMemBar();"   # same repo — ONE origin (RULES.md Art. 3).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an in-place reduce on a 950 board that produces correct, bit-stable output across 50
           runs with the `LocalMemBar` removed — the "needed" rows would then be unnecessary; or a
           standard elewise loop that produces wrong output without one, breaking the "not needed" rows.
```

# 0258 · `LocalMemBar` is needed only when consecutive iterations touch the same address

## 1 · Claim
Upstream asserts that `LocalMemBar<VEC_STORE, VEC_LOAD>()` is a VF-internal ordering primitive — a
`__simd_callee__` template taking source and destination `MemType` parameters — that makes prior
`VEC_STORE` writes visible to subsequent `VEC_LOAD` reads, and that it acts **only** inside the Vector
unit. Upstream asserts a five-case rule for when it is required: not needed when consecutive iterations
read and write different addresses (`off = i * VL`), not needed for a load-modify-store of the same
address within one iteration, not needed across different buffers (src→dst elementwise); **needed** when
consecutive iterations read and write the same address (in-place reduce), and needed when an inner loop
writes an address that the next outer iteration reads. Upstream names the common error: appending a
`LocalMemBar` at the end of a standard elementwise loop is redundant, because each iteration's target
address differs. Not established here: nothing was compiled and no ordering was observed.

## 2 · The wrong branch this removes
Both directions cost, and the table is the only thing in this scope that separates them.

Omitting a required barrier — the in-place reduce case — is a read-before-write race inside the Vector
pipeline. It will not fail deterministically: it fails at some shapes, under some occupancies, on some
runs. The regbase pitfall material names exactly this diagnostic trap: "Treating non-determinism as
harmless noise … identical input produces different mismatches … synchronization or branch-selection
problems are masquerading as precision drift" (`common_traps.md` §8). An author who does not know the
rule will widen dtypes looking for a precision bug that is not there.

Adding an unnecessary one — upstream's 常见错误 — is a pipeline ordering constraint taken once per
iteration on the hottest loop in the kernel. Nothing is wrong; the loop is simply slower forever, and
there is no signal. This is the direction an agent takes by default, because a barrier "just to be safe"
is the reflex when the rule is unknown.

The discriminating fact is small and easy to state: what matters is not whether an iteration reads and
writes, but whether **consecutive** iterations touch the **same address**. A load-modify-store of one
address inside a single iteration does not need it; the same pattern across two iterations does. That
single distinction is the whole table.

There is a second confusion this entry has to hold off, and it is live. `LocalMemBar` is not
`PipeBarrier<PIPE_V>`. They are different primitives at different scopes — one is `__simd_callee__` and
acts inside a VF between Reg operations, the other is a kernel-side pipe barrier between instructions —
and B2 (0259) is an open four-way disagreement about the second. An agent that resolves B2 by "the
hardware guarantees VF ordering, so I need no barriers" and carries that conclusion inside the VF body
has crossed from one primitive to the other. Upstream's own arch35 guarantee is stated for 连续 Vector
计算 and 连续 VF (0259 §3) — between VFs, not within one — and this table is what governs within.

## 3 · Ground / Source
`vf-programming-rules.md:81-93`, the section in full — the interface sentence, the table, and the named
error, because the error is what makes the table stick:

> ## 6 LocalMemBar 使用规则
>
> `LocalMemBar<VEC_STORE, VEC_LOAD>()` 保证之前所有 VEC_STORE 写入对后续 VEC_LOAD 可见。仅作用于
> Vector 单元内部。
>
> | 场景 | 是否需要 |
> |------|---------|
> | 每次迭代读写**不同地址**（`off = i * VL`） | **不需要** |
> | 同一迭代内 load-modify-store 同一地址 | **不需要** |
> | 跨不同 buffer（src→dst elewise） | **不需要** |
> | 连续迭代读写**同一地址**（in-place reduce） | **需要** |
> | 内层循环写，外层下次循环读同一地址 | **需要** |
>
> **常见错误**：在标准 elewise 循环末尾加 `LocalMemBar` 是多余的——每次迭代目标地址都不同。

Three of five rows are 不需要, and upstream spends its emphasis on the negative — a table written by
someone who had seen the over-application, not the omission. That asymmetry is a signal about which
error is more common in practice and is worth carrying into the delivered skill.

`sync-and-consistency.md:265-273` gives the interface and places it in the synchronisation taxonomy:

> ### 2.4 VF LocalMemBar
>
> LocalMemBar 是 VF 函数（`__simd_vf__`）内部的同步指令，用于 Reg 矢量计算中 UB 读写流水线间的保序。
>
> **接口**：
>
> ```cpp
> template <MemType src, MemType dst>
> __simd_callee__ inline void LocalMemBar();
> ```

`__simd_callee__` is the marker that matters: it is VF-safe, so it is callable from inside a VF body,
which is where it belongs. The same file's `§2.1` taxonomy at `:44-50` places it against the other two
mechanisms — SetFlag/WaitFlag for cross-pipe dependencies, PipeBarrier for same-pipe — and
`LocalMemBar` for UB read/write ordering *within* Reg computation. Three primitives, three scopes, and
this is the innermost.

The whitelist lists it in the VF-safe "Mask and copy helpers" family
(`regbase_api_whitelist.md:82`) alongside `MaskReg`, `CreateMask`, `UpdateMask`, `Pack`, `UnPack` and
`Move`, confirming it is a VF-callable surface rather than a kernel-side API (0250).

One independent corroboration of the *necessity* direction exists in a different skill and is worth
recording because it is the only case in this scope where omitting it is reported to have a named
consequence: `ascendc-perf-optimize`'s vec-05 card (eliminate UB staging) states that a retained
round-trip needs `LocalMemBar<VEC_STORE, VEC_LOAD>` or `maxAbsErr` goes to infinity. Same repo, so one
origin — but it is a second author reaching for the same primitive in the same shape, and an infinite
absolute error is a loud failure rather than a drift, which cuts slightly against §2's
non-deterministic framing.

What upstream does not supply: the full `MemType` enumeration, what other `<src, dst>` pairs mean, or
what the cost of one barrier is. The table is written entirely for the `VEC_STORE, VEC_LOAD`
specialisation, and whether other pairs have their own rules is unstated.

## 4 · Procedure
Runnable later on `950PR`. The claim is a five-row partition, so the procedure must exercise the
"needed" rows and the "not needed" rows — testing only one side would confirm nothing about the table.

Base kernel. One `__simd_vf__` whose access pattern is a compile-time parameter, so that the five rows
are five instantiations of one source and the barrier is the only textual difference between each row's
two builds. Build md5s are recorded and confirmed to differ between the with- and without-barrier
variants, or the run is void — a toggle that did not take produces a perfect null result.

Arm A — the two "needed" rows. Row 4: an in-place reduce where iteration `i` reads and writes the same
UB address as iteration `i−1`. Row 5: an inner loop writing an address that the next outer iteration
reads. For each, build with and without the barrier, run on the same die in the same session, and
compare output buffers byte for byte against a host reference. Repeat each 50 times at each of five
shapes chosen to vary pipeline occupancy (n ∈ {64, 512, 4096, 10752, 65536}) — a race that does not
appear at one occupancy commonly appears at another, and a single comparison would miss it.

Arm B — the three "not needed" rows. Row 1: `off = i * VL`, different address each iteration. Row 2:
load-modify-store of one address within a single iteration. Row 3: src→dst across two buffers. Same
protocol. Upstream predicts bit-identical output with and without the barrier at every shape and
repetition.

Arm C — the cost of the redundant barrier, which is what makes upstream's 常见错误 actionable rather
than merely correct. For row 1 — the standard elementwise loop upstream names — collect `aiv_time` for
both builds, minimum over 50 repetitions, and report Δ absolutely and as a fraction. This prices the
reflex.

Arm D — the scope boundary, which guards §2's second confusion. Confirm that `LocalMemBar` does **not**
substitute for the kernel-side `PipeBarrier<PIPE_V>` question of 0259: build the row-4 kernel with the
`LocalMemBar` present and the post-VF `PipeBarrier` absent, and vice versa, and record whether the two
failures (if any) are distinguishable. This arm is why the two entries must not share a run.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Both builds of one row run on one named die in one
session — a with/without comparison across dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `barrier_required[row]`, one per row, five of them, **never aggregated**. A five-row
partition collapsed into one boolean is exactly the shape that lets three confirming "not needed" rows
outvote one broken "needed" row, and the "needed" rows are where the correctness risk is.

Per row, `barrier_required[row]` is true iff the no-barrier build differs from the with-barrier build in
**any** byte, at any shape, in any of the 50 repetitions. One differing byte anywhere sets it true;
process exit code is not the verdict.

Pass is declared now as: `barrier_required` true for rows 4 and 5, false for rows 1, 2 and 3 — the
table exactly. Two failure modes are named now so neither can be reinterpreted afterwards. A "needed"
row coming back false means either the barrier is unnecessary there or the harness cannot provoke the
race — and Arm A's shape sweep and repetition count exist so those can be told apart by whether *any*
configuration bit. A "not needed" row coming back true is the more serious outcome: it means upstream's
negative rows are wrong and the common error is not an error.

`redundant_barrier_cost` (Arm C) — Δ`aiv_time` with run variance. No pass threshold; a Δ smaller than
the observed variance is reported as "below variance", never as zero.

The positive fixture, declared before the run: a variant row 4′ in which the in-place dependence is made
maximally tight (every iteration reads the address the previous one wrote, with no independent work
between). Its no-barrier build **must** produce differing bytes. If it does not, the harness cannot
detect an ordering violation at all, and every `barrier_required = false` it reported — including all
three "not needed" rows — is void. This is the guard against the known blind species: a bit-comparator
never shown to go red is a comparator that confirms cleanliness and nothing else. Upstream's own vec-05
card supplies a second candidate fixture with a louder signature (`maxAbsErr = inf`), and using it as a
cross-check costs one extra build.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
barrier was toggled, and no output was compared. The interface signature in §3 is upstream's
transcription; no installed header was read to confirm that `LocalMemBar` or the `MemType` enumeration
exist under those spellings, and that check is a file read that remains open.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish any of the five rows, the interface signature,
or the visibility guarantee — Arms A and B are open, and Arm A's positive fixture is what would make a
null result interpretable at all. There is **no second origin**: both quoted files are one repo, and no
installed header was consulted, unlike 0244 and 0246 where the toolkit answered. It covers only the
`<VEC_STORE, VEC_LOAD>` specialisation: upstream's table is written for that pair alone, the full
`MemType` enumeration is not given, and nothing here says what other `<src, dst>` combinations mean or
whether they have different rules. It does not price the barrier — Arm C is open — so the cost of the
common error is asserted in §2 and unmeasured. It says nothing about `PipeBarrier<PIPE_V>` after a VF,
which is a different primitive at a different scope and is the open four-way disagreement of 0259; Arm D
exists precisely to keep them apart, and an agent that merges them will resolve one question with the
other's evidence. It says nothing about cross-core or cross-pipe ordering, which are SetFlag/WaitFlag's
territory (0262). BOARD is `family-claimed(unverified)` — the files name no board token this book
recognises, the material is arch35-generic regbase, and none was contacted. Finally, the vec-05
corroboration noted in §3 is the same repo and therefore not independent, and its reported failure mode
(`maxAbsErr = inf`) is louder than the non-deterministic drift §2 describes — so even the failure
*shape* of an omitted barrier is not settled here.

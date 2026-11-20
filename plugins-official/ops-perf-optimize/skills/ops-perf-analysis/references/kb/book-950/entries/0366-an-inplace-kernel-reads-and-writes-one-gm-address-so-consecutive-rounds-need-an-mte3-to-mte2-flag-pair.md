```
ID:        0366-an-inplace-kernel-reads-and-writes-one-gm-address-so-consecutive-rounds-need-an-mte3-to-mte2-flag-pair
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Upstream names the
           hazard and the repair and gives no symptom, no shape at which it appears, and no evidence
           that it has been observed. Nothing was compiled and no pipeline was raced.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/inplace_operator_patterns.md:113-121
           — "inplace 算子的 `<name>` 与 `<name>_out` 运行时指向**同一块 GM 地址**：" … "2. **避免
           alias 冲突**：计算链中不要出现「同一时刻既读 `<name>` 做 source、又写 `<name>_out` 做
           destination」的指令——两者地址相同会产生 read-after-write hazard。中间结果须暂存 UB buffer，
           计算完成后再写回 GM。" … "4. **同步时序**：由于输入输出同地址，CopyIn 读取 `<name>` 与 CopyOut
           写回 `<name>_out` 指向同一块 GM 内存。若 CopyOut（MTE3）与下一轮 CopyIn（MTE2）之间未正确同步，
           MTE2 可能在 MTE3 写回完成前读到旧数据。须在流水线轮次之间插入
           `SetFlag<HardEvent::MTE3_MTE2>` / `WaitFlag<HardEvent::MTE3_MTE2>` 同步对，确保上一轮写回完成
           后再读取下一轮数据。"
SOURCE:    same file:115 — "1. **CopyOut 直接写回**：计算结果写回 `<name>_out` 的 GM 地址即可（原地写回），
           无需为输出单独分配 buffer。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an inplace 950 kernel whose per-round pipeline reads stale data with the `MTE3_MTE2` pair
           present — the pair would then not be the right repair; or, in the other direction, a
           multi-round inplace kernel that is bit-correct over ≥1000 runs at a shape with real MTE
           overlap and *no* pair, which would make the hazard theoretical for that shape class and
           would demand a stated condition upstream does not give.
```

# 0366 · An inplace kernel reads and writes one GM address, so consecutive rounds need an MTE3-to-MTE2 flag pair

## 1 · Claim
Upstream asserts that in an inplace operator the kernel's `<name>` and `<name>_out` parameters point at
the same block of GM at run time. Upstream asserts the direct consequence for the compute chain: no
instruction may read `<name>` as source while writing `<name>_out` as destination at the same moment,
because the addresses are identical and that is a read-after-write hazard; intermediates must be staged
in a UB buffer and written back after the computation completes. Upstream asserts a second, distinct
consequence for the pipeline: because `CopyIn` reads and `CopyOut` writes the same GM, an unsynchronised
`CopyOut` (MTE3) followed by the next round's `CopyIn` (MTE2) can let MTE2 read stale data before MTE3's
write-back has completed, and a `SetFlag<HardEvent::MTE3_MTE2>` / `WaitFlag<HardEvent::MTE3_MTE2>` pair
must be inserted between pipeline rounds. Upstream asserts that the result is written directly back to
`<name>_out`'s GM address with no separately allocated output buffer. Not established here: nothing was
compiled, no pipeline was raced, and upstream gives **no symptom and no shape** at which the hazard
appears.

## 2 · The wrong branch this removes
This is the entry where 0364's silent mechanism becomes a data race, and the reason it is dangerous is
that the ordinary version of the same kernel is correct.

An out-of-place operator's `CopyIn(i+1)` reads the input buffer while `CopyOut(i)` writes the output
buffer. Those are different allocations, so the two MTE engines can overlap freely — and overlapping them
is the *point* of the tile loop. Every regbase kernel shape in this book's material (0355 §3's
`CopyIn → Compute → CopyOut` loop) is built on that freedom. Make the operator inplace by the `OpDef`
rename (0364), change nothing in the kernel, and the two buffers become one. The loop that was correct is
now a race, and nothing about the kernel source changed.

That is the branch: **inplace is declared at the host layer and its hazard appears at the kernel layer**,
and an agent that makes an operator inplace by editing the `OpDef` has introduced a synchronisation
requirement into a file it did not open. There is no diagnostic, because at the C++ level `var` and
`var_out` are two `GM_ADDR` values and the compiler has no reason to think they alias.

The failure's shape is the second reason it is hard. Reading stale data is not reading garbage — it is
reading the *previous* value of that tile, which for an accumulate-style operator (`InplaceIndexAdd`,
`InplaceApplyAdaMax`) means an update is silently dropped. The output is a plausible tensor. It is wrong
by exactly one round's contribution, at whichever tiles the race happened to catch, and it changes
between runs. `common_traps.md:145-159` names that presentation directly: "identical input produces
different mismatches … synchronization or branch-selection problems are masquerading as precision drift".
An agent that meets it will widen precision (`common_traps.md:161-175`, "Blindly widening everything to
`fp32`"), see the failure rate drop because the timing changed, and record a precision fix.

Upstream's two numbered items are **different hazards with different repairs** and are easy to conflate.
Item 2 is intra-round: an instruction reading and writing the aliased address at once; the repair is a UB
staging buffer, i.e. a dataflow change. Item 4 is inter-round: MTE3 and MTE2 racing across the loop
boundary; the repair is an event pair, i.e. a synchronisation change. Fixing one does not fix the other,
and an agent that adds the flag pair because it read "alias conflict" has not addressed the case where
its VF writes the same tile it is reading.

The cost direction is worth stating too, because it cuts against 0359: an `MTE3_MTE2` pair per round
serialises write-back against the next load, which is precisely the overlap the double-buffered loop
exists to obtain. 0359 records upstream warning against importing flag pairs into simple operators; this
entry is the named case where a light-looking operator *requires* one. The two are not in conflict —
0359's condition is "the design truly overlaps movement and compute", and an inplace loop does — but an
agent holding only 0359 would remove this pair as over-engineering.

## 3 · Ground / Source
The aliasing statement and the two hazards, `inplace_operator_patterns.md:113-121`:

> inplace 算子的 `<name>` 与 `<name>_out` 运行时指向**同一块 GM 地址**：
>
> 1. **CopyOut 直接写回**：计算结果写回 `<name>_out` 的 GM 地址即可（原地写回），无需为输出单独分配
>    buffer。
>
> 2. **避免 alias 冲突**：计算链中不要出现「同一时刻既读 `<name>` 做 source、又写 `<name>_out` 做
>    destination」的指令——两者地址相同会产生 read-after-write hazard。中间结果须暂存 UB buffer，计算完成后
>    再写回 GM。
>
> 3. **多输出 inplace**：一个算子可有多组 inplace 关系（如 `InplaceApplyAdaMax` 的 `var`/`m`/`v` 三个输入
>    均原地更新），每组独立遵循同名 + `_out` 后缀规则。
>
> 4. **同步时序**：由于输入输出同地址，CopyIn 读取 `<name>` 与 CopyOut 写回 `<name>_out` 指向同一块 GM
>    内存。若 CopyOut（MTE3）与下一轮 CopyIn（MTE2）之间未正确同步，MTE2 可能在 MTE3 写回完成前读到旧数据。
>    须在流水线轮次之间插入 `SetFlag<HardEvent::MTE3_MTE2>` / `WaitFlag<HardEvent::MTE3_MTE2>` 同步对，
>    确保上一轮写回完成后再读取下一轮数据。同步策略选择详见 `regbase_sync_patterns.md`.

Item 1 and item 4 sit three lines apart and pull in opposite directions: item 1 says the write-back needs
no extra buffer and reads as a simplification; item 4 says the resulting aliasing needs a synchronisation
pair and reads as a complication. Both are true and the file does not connect them, so an agent that
stops after item 1 — which is the natural stopping point, because item 1 answers the question it came
with — has the simplification and not the constraint.

Item 4 is the only place in the inplace card that names a `HardEvent`, and the direction is specific:
`MTE3_MTE2`, write-then-read, not the `MTE2_V`/`V_MTE2` pair `regbase_sync_patterns.md:74-78` shows for
the ordinary overlap case (0359 §3). That is the correct direction for this hazard and it is a *third*
direction beyond the two the sync-patterns file catalogues, so an agent working only from the sync file's
representative pattern would not find it.

Note what item 4 does **not** say: at what shape, at what tile count, or with what probability the stale
read occurs; whether a single-round kernel is safe; whether double buffering changes the answer; and
whether the pair is needed when the tiles of consecutive rounds do not overlap in address. That last one
matters most — in a straightforward tile loop, round *i* writes tile *i* and round *i+1* reads tile
*i+1*, which are **different addresses inside the same allocation**. Upstream's stated mechanism ("同一块
GM 内存") is about the allocation, not the tile. Whether the hazard is real for disjoint tiles is exactly
what §4 Arm C exists to determine, and no source in scope says.

The multi-output case, item 3, is 0367-adjacent but distinct: three independent inplace pairs mean three
independent aliases, so a kernel that gets the flag pair right for `var` and omits it for `m` and `v` has
two thirds of a race.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
Runnable later on `950PR`. A race needs repetition and a provoking shape, and the negative control is the
whole experiment.

Arm A — provoke it. Build one inplace accumulate operator (`out[i] += f(in[i])` with the two `GM_ADDR`
aliased) whose tile loop has real MTE overlap: many rounds, tiles large enough that MTE3 has not
completed when the next MTE2 issues. Build twice — with and without the `MTE3_MTE2` pair — and run each
1000 times at three tile counts, comparing every run against a host reference. Record failing runs and,
for each failure, which tiles differ and by how much. §2 predicts failures concentrated at tile
boundaries and equal to one round's contribution.

Arm B — the tile-disjointness question §3 raises. Repeat Arm A with the loop arranged so consecutive
rounds touch strictly disjoint address ranges, and separately so they touch overlapping ranges.
If the disjoint arrangement never fails without the pair, upstream's rule is over-broad and the real
condition is address overlap, not allocation identity — which would let generated kernels drop the pair
in the common case. If it fails anyway, the hazard is at the allocation or cache level and the rule as
written is right.

Arm C — the intra-round hazard, which is a different repair. Build a variant whose VF reads `var` and
writes `var_out` for the same element without UB staging, and compare against the staged version. This
tests item 2 rather than item 4, and it must be a separate build: fixing the pipeline race would
otherwise be credited with fixing this.

Arm D — the cost. For the shapes where Arm A shows no failure with the pair, record the duration with and
without it. The pair serialises write-back against the next load, so the number is the price of the
repair, and 0359's over-application warning has no way to weigh it without this.

Arm E — multi-output, item 3. Build a three-alias operator, put the pair on one alias only, and run
Arm A's protocol. Predicted: the two unguarded aliases fail. This is the arm that would show whether the
requirement is per-alias or per-kernel.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all builds of one comparison run on one named die in one session. A missing `WaitFlag` can
deadlock, so a watchdog timeout and die release are declared before the run.

## 5 · Checker — acceptance declared before the run
`unguarded_failure_rate` (Arm A) — failing runs out of 1000, per tile count, for the no-pair build.
Reported per tile count, never averaged: a race that appears only at the largest tile count is still a
race, and averaging over three counts is how it becomes a 0.3% footnote.

`guarded_failure_rate` (Arm A) — the same for the pair build. Pass iff 0/1000 at every tile count. Any
non-zero overturns the repair.

`disjoint_tiles_safe` (Arm B) — true iff the disjoint arrangement is 0/1000 without the pair. Reported,
not gated. This is the arm that could narrow upstream's rule, and both answers are useful: a false result
means the rule is right as written and a generated kernel must always carry the pair.

`intra_round_hazard` (Arm C) — true iff the unstaged variant differs from the staged one. Reported
separately from every Arm A verdict, because it is a different hazard with a different repair and one
merged "inplace is unsafe" verdict would erase which repair was needed.

`pair_cost` (Arm D) — duration ratio, guarded over unguarded, per tile count. Reported. Declared now so
0359's over-application warning and this entry's requirement can be weighed against each other rather
than argued.

The positive fixture, declared before the run: **Arm A's no-pair build must fail at least once**. If it
does not, the shape has no MTE overlap in it and every "0 failures" result in the arm — including the
guarded build's green — is a statement about the probe, not about the flag pair. A synchronisation
experiment whose unsynchronised arm passes has measured nothing, and this is the exact species this book
keeps recording, so it is declared first. A second fixture: the host reference comparison must be shown
sensitive by injecting a one-tile error and confirming it is caught; a comparison that reads only the
first tile would report clean runs regardless.

Process exit codes are not the verdict for any arm: every arm expects wrong values from processes that
exit zero, and a watchdog kill is informative rather than a failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no flag set
or waited, no run repeated, no tile compared, no die contacted. The quoted passages are re-verified file
reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the stale read occurs, that the
`MTE3_MTE2` pair prevents it, or that the intra-round alias conflict produces wrong results — Arms A
through E are all open, and upstream states the hazard with **no symptom, no shape, and no probability**.

It does not establish the hazard's real condition. Upstream's mechanism is stated at allocation
granularity ("同一块 GM 内存") while a normal tile loop has consecutive rounds touching *different
addresses* inside that allocation. Whether the hazard needs address overlap or merely allocation identity
is Arm B, and it is the difference between a pair on every inplace kernel and a pair on a narrow subset.
This entry does not choose; §3 records that no source in scope does either.

It does not establish anything about double buffering, which changes the overlap structure entirely
(0042) and which upstream's item 4 does not mention. A ping-pong inplace loop may have a different answer
and nothing here transfers to it.

It does not establish whether the requirement is per-alias or per-kernel (Arm E), nor whether `HardEvent`
IDs are available to satisfy it — 0262 records that event IDs are pooled per type with eight slots and
that `FetchEventID` can repeat, so a three-alias operator asking for three pairs is drawing on a resource
whose limit is unverified.

It does not establish the pair's cost, which is the number 0359's over-application warning would need to
be weighed against this entry's requirement.

BOARD is `family-claimed(unverified)`: the card names no board token this book recognises, the hazard is
stated in terms of MTE engines rather than a part, and no board was contacted.

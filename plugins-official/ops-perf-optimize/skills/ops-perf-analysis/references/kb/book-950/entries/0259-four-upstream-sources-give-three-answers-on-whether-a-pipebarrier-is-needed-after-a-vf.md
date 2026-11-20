```
ID:        0259-four-upstream-sources-give-three-answers-on-whether-a-pipebarrier-is-needed-after-a-vf
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   verified — §4 run on 950PR 2026-08-25 via §5's declared variables: `bits_identical` = TRUE
           (build B, no `PipeBarrier<PIPE_V>` between two dependent `__VEC_SCOPE__` segments, byte-identical
           to build A and to the host reference in 0 of
           1990 launches across shapes [64, 512, 4096, 10752, 24576], under
           `--cce-auto-sync=on` AND `=off`); the positive fixture went RED (the V→MTE3 flag pair removed:
           stale bytes copied out on the first launch at 4 of 5 shapes, both settings); `barrier_cost_frac`
           18.6 % / 3.6 % / 0.6 % of A at 512 / 4096 / 24576 fp32. `autosync_reinserts` was controlled by
           the compiler flag (the `off` binaries differ by md5 and behave identically), not counted in the
           object — the log facility could not be made to write a file (§6). Position 2 supported, position
           1 not, on this part and this pattern. Previously harvested (one origin, four passages).
BOARD:     950PR (measured 2026-08-25); 950DT unverified
           # three of the four passages name arch35/Ascend950 generically; none names a board token
           # this book recognises, and no board was contacted.
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:54
           — "VF 段后该有的 `PipeBarrier<PIPE_V>()` 要保留——VF 内部不替你做同步。"
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:243
           — "arch35/Ascend 950 上连续 Vector 计算之间、连续 VF 之间硬件保证顺序，无需手动
           PipeBarrier<PIPE_V>()"  (restated at :50 and :302)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/quantization/references/vf-microapi-patterns.md:347
           — "| `PipeBarrier<PIPE_ALL>()` | `__VEC_SCOPE__` 内不需要（VF 自动调度）；scope 与 CopyOut
           之间用 Queue 自动同步 |"
SOURCE:    ops/ascendc-sync-check/references/sync-mechanism.md:155 — "auto-sync 开启时编译器在 V 操作间
           自动插入 `PipeBarrier<PIPE_V>`，开发者无需手工添加。"
INDEX:     means=one source, builds differing by `-D` flags only (md5s recorded), two dependent regbase
           `__VEC_SCOPE__` segments over a poison-prefilled UB buffer, byte-wise compare of the copied-out
           result against a host reference; `--cce-auto-sync=on|off`; msprof `aiv_total_time` (10 launches)
           conditions=CANN 9.1.0, `-xasc --npu-arch=dav-3510`, 950PR, fp32, n ∈ {64, 512,
           4096, 10752, 24576} (two UB buffers; 24576 is the largest fitting twice), 50 reps per shape + 200
           at 4096/24576, device idle
           readouts: two_B identical 0/1990; fixture F2 red
           (first launch) at 512/4096/10752/24576 under on and off; two_A − two_B = +0.22 / +0.04 / +0.02 µs at
           512 / 4096 / 24576; auto-sync default = on (byte-identical md5 with the default build)
           time=2026-08-25
OVERTURN:  a paired run on a named 950 board, barrier the only variable, in which removing
           `PipeBarrier<PIPE_V>()` after a VF changes the output bits. That kills position 2
           outright. Bit-identical output with identical timing kills position 1's necessity.
```

# 0259 · Four upstream sources give three answers on whether a `PipeBarrier` is needed after a VF

## 1 · Claim
Measured on 950PR (regbase `__VEC_SCOPE__`, fp32, five shapes to 24576 elements): two consecutive
vector segments where the second reads what the first stored produce byte-identical output with and
without a `PipeBarrier<PIPE_V>()` between them — in every one of 1990 launches, with the
compiler's automatic synchronisation ON and with it OFF — while the same harness catches a real
ordering violation (the vector→MTE3 flag pair removed before the copy-out) on the first launch of every
process at four of the five shapes. On this part and for this pattern, upstream's position 2 ("the
hardware guarantees ordering between consecutive Vector computations / VFs on arch35") is what the
part does, and position 1 ("keep the barrier after a VF段") buys nothing but time: the barrier costs
0.22 µs per kernel at 512 elements (18.6 % of a 1.18 µs kernel) and 0.02 µs at 24576 (0.6 %). Not
established: what an *op-framework* build (TQue-mediated CopyOut, position 3) or a SIMT `__simt_vf__`
followed by classic vector code does — a different edge (§7).

Inference, stated separately: position 4 (the compiler inserts `PIPE_V` barriers when auto-sync is on)
did not decide this — the `off` build differs from the `on` build in its binary and behaves the same,
and auto-sync ON did **not** rescue the removed V→MTE3 flags either, which says the automatic
synchronisation on this pin does not cover a hand-written `DataCopy` after a `__VEC_SCOPE__`. The
same-scope store→load without `LocalMemBar` (0258's rule) also produced no wrong byte in
940 launches; that is reported, not adjudicated.

## 2 · The wrong branch this removes
Without this entry an agent reads whichever of the four it opened and follows it. Both directions are
harmful and only one is loud.

Following position 2 or 4 and removing the barrier: if position 1 is right, the result is a
read-before-write race between the VF's stores and whatever follows. Races of this shape do not fail
deterministically — they fail at some shapes, on some parts, under some pipeline occupancies. A unit
test at one shape passes. The defect ships and reappears as an intermittent precision complaint.

Following position 1 and keeping the barrier: if position 2 is right, every barrier is a pipeline
drain on the hottest path in a Vector kernel, taken once per VF invocation. Nothing is wrong; the
kernel is simply slower, forever, with a clean profile.

The composite branch is the one an agent is most likely to take: read position 4, conclude
"the compiler handles it", and not check whether auto-sync is on. Position 4 is **conditional** —
`auto-sync 开启时` — and the same file's own census records that a substantial body of production
code runs with it off (§3). A conditional rule read as unconditional is the failure that survives
review, because the sentence is true.

## 3 · Ground / Source
All four re-verified against the files during this harvest; the deep-dive (defect 4.11) located them
and its characterisation of two of them needed correction, noted below.

**Position 1** — `vec-03-fused-instr.md:49-55`, in the 红线 block:

> - VF 段后该有的 `PipeBarrier<PIPE_V>()` 要保留——VF 内部不替你做同步。
> - 尾段单次 lane < 32 的短向量不值得改（VF 启动有固定开销）。

Unconditional, and stated as a stop rule — the strongest register the card format has.

**Position 2** — `sync-and-consistency.md:241-246`, the 约束 block under 单流水同步 PipeBarrier:

> **约束**：
> - arch35/Ascend 950 上连续 Vector 计算之间、连续 VF 之间硬件保证顺序，无需手动 PipeBarrier<PIPE_V>()
> - `PipeBarrier<PIPE_ALL>()` 会等待所有流水线完成，对性能影响大，能用单流水 PipeBarrier 解决时不要用 PIPE_ALL
> - **MTE2/MTE3 搬运地址重叠时需手动插入**：硬件不保证搬运地址重叠时的串行化，需手动
>   `PipeBarrier<PIPE_MTE2>()`（UB 目的地址重叠）或 `PipeBarrier<PIPE_MTE3>()`（GM 目的地址重叠）

The same file states it twice more: `:50` ("Ascend950 上不同的 VF 间硬件保证串行，不需要
PipeBarrier") and `:302` in a summary table ("| 同一流水线内连续 Vector 计算 | 不需要 |
arch35/Ascend 950 上连续 Vector 计算之间硬件保证顺序 |"). This is the most specific of the four: it
names the architecture, scopes the guarantee to two named situations, and carves out an exception
(overlapping MTE addresses) that shows the author was distinguishing cases rather than generalising.

**Position 3** — `vf-microapi-patterns.md:347`, the last row of a scalar-API→MicroAPI migration table:

> | `PipeBarrier<PIPE_ALL>()` | `__VEC_SCOPE__` 内不需要（VF 自动调度）；scope 与 CopyOut 之间用 Queue 自动同步 |

**Re-verification correction.** The 2026-08-24 deep-dive summarised this as "none needed in
`__VEC_SCOPE__`", implying `PIPE_V`. The line is about `PipeBarrier<PIPE_ALL>()`, and it is about the
*inside* of a scope, not the boundary *after* a VF. It is therefore weaker evidence for the
"no barrier" side than the survey suggested, and it does not directly contradict position 1, which
concerns what follows the VF段. A survey is one contact; this is what re-verifying it changed. Logged
as a finding.

**Position 4** — `sync-mechanism.md:153-161`:

> ### 4.4 auto-sync 自动插入 PipeBarrier<PIPE_V>
> auto-sync 开启时编译器在 V 操作间自动插入 `PipeBarrier<PIPE_V>`，开发者无需手工添加。
>
> **商用算子仓验证**：
> - PipeBarrier<PIPE_V> 使用 16,531 次（远超其他类型），证实 V 流水内部同步是最高频场景。
> - PipeBarrier<PIPE_ALL> 使用 1,795 次，PIPE_MTE2 使用 120 次，PIPE_MTE3 使用 127 次。PIPE_ALL 仍有
>   不少使用（主要在 AUTO_SYNC false 的 attention 算子中），但远少于精确 PIPE_V…

**Re-verification correction.** The deep-dive rendered positions 2 and 4 as "the last two cannot both
hold". They can. A hardware ordering guarantee and a compiler that inserts redundant barriers are
compatible — the barriers would be unnecessary, not wrong. What positions 2 and 4 jointly imply is
that 16,531 hand-or-compiler-placed `PIPE_V` barriers in the commercial operator repo are, on arch35,
mostly no-ops — which is a claim about wasted work, not a contradiction. The genuine conflict is
**1 versus 2**: keep it because the VF does not synchronise, against you do not need it because the
hardware does. Logged as a finding.

Note also what position 4's own census reveals about position 4: `AUTO_SYNC false` operators exist in
production, so the conditional is live. And note that these counts are over an operator repo spanning
multiple architectures, so they say nothing about arch35 specifically.

All four files are under `upstream/skills-dev-main` and are therefore **one origin** (RULES.md Art. 3).
This disagreement cannot be settled by reading more of the repo, which is exactly why it is B2.

Two structural observations about why it survived. First, `ascendc-perf-optimize` and
`ascendc-regbase-best-practice` have essentially no coupling — the deep-dive measured one shared
line ≥40 characters between them, a compiler guard, and no file in either references the other by
name. Second, they gate differently: perf-optimize gates on msprof thresholds, regbase gates on
compile and correctness rules. A rule that is a correctness question for one library and a
performance question for the other is invisible to both gates.

Filed as `C-950arch-004` in `harvest/contradictions-950-arch.md`.

## 4 · Procedure
Runnable later on `950PR`, and separately on `950DT`. This is the deep-dive's B2 and the design
constraint is fixed: **isolated toggle, bit-compare AND timing, barrier the only variable.**

Base kernel. One `__simd_vf__` performing a Reg-computed elementwise chain over UB, followed
immediately by a second VF that reads the first's destination buffer — the ordering-sensitive edge.
Both VFs use `LoadAlign`/`StoreAlign` on the same `__ubuf__` region, so a missing barrier would
manifest as the second VF reading pre-store data.

```cpp
// A: with barrier            B: without barrier — the ONLY textual difference
asc_vf_call<Stage1Vf<float>>(ubA, ubB, n, rpt);
AscendC::PipeBarrier<PIPE_V>();      // <-- present in A, absent in B
asc_vf_call<Stage2Vf<float>>(ubB, ubC, n, rpt);
```

Build A and B from the same source with the barrier controlled by a single preprocessor symbol, so
that nothing else can differ. Record the md5 of both binaries and confirm they differ (if they do
not, the toggle did not take and the whole run is void).

Arm 1 — bit-compare. Run A and B on the same die, same session, same input, and compare output
buffers byte for byte. Repeat at a shape sweep chosen to vary pipeline occupancy: n ∈ {64, 512,
4096, 10752, 65536}, because a race that does not appear at one occupancy commonly appears at
another. Repeat each shape 50 times — a race observed once in fifty is still a race, and a single
comparison would miss it.

Arm 2 — timing. On the same builds, collect `aiv_time` per case with msprof, minimum over 50
repetitions, no representative sampling. The quantity of interest is the per-VF-invocation cost of
the barrier, so report Δ(A−B) both absolutely and as a fraction of A.

Arm 3 — the auto-sync variable, which is what position 4 makes necessary. Repeat Arms 1 and 2 with
auto-sync explicitly ON and explicitly OFF, four builds total. Without this arm, a null result in
Arm 1 is unattributable: it could mean the hardware guarantees ordering (position 2) or that the
compiler inserted the barrier back into build B (position 4). Arm 3 is the difference between
answering B2 and producing a number.

Arm 4 — the disassembly cross-check, cheap and decisive for Arm 3's ambiguity. Disassemble build B
under each auto-sync setting and count emitted `PIPE_V` barrier instructions. If build B contains
barriers the source did not, position 4 is operating and Arm 1's null result says nothing about
hardware ordering.

Device selection is explicit: the operator names the device index; the probe prints it back with
`compiler/version.info` and the resolved SoC string; occupancy is checked before the run (shared
machine, ≤4 dies); no die is substituted for another at any point. All four builds for one comparison
run on one named die in one session — a two-point comparison of two different builds on two different
dies carries no attribution at all.

**As run (2026-08-25, jobs b2_0259 → b2c → b2d, the 950 machine):** the base kernel is two
`__VEC_SCOPE__` regbase segments in one `__global__ __vector__` kernel (stage 1: B = 2A + 1 over a
poison-prefilled B; stage 2: A = 3B) rather than two `asc_vf_call<…>` functions — that spelling is not
in the installed 9.1.0 headers; `__VEC_SCOPE__` is what upstream's own arch35 templates use for a VF
段. The barrier is `PipeBarrier<PIPE_V>()` between the two scopes under `-DWITH_BARRIER`; nothing else
differs (md5s: A d8ae83bb…, B 115e13e0… under the default; c6064cd8… / 50523df9… under `off`).
Arm 1 as written (50 reps × 5 shapes, +200 at 4096 and 24576), every rep compared byte-wise to a host
reference as well as A-vs-B. Arm 2 with msprof `aiv_total_time`, 10 launches, min reported. Arm 3 with
`bisheng --cce-auto-sync=on` / `=off` (the flag exists on this pin; the default build is byte-identical to
`on`). Arm 4 could not be run as a disassembly count: the shipped llvm-objdump does not decode dav-c310
vector code, `strings` on the device object finds no barrier names, and `--cce-auto-sync-log=<file>`
(accepted only with `-g`) produced no file at a relative or an absolute path; Arm 4 is therefore
replaced by the flag control in Arm 3 and disclosed as such. **Fixture:** §5's suggested variant C
(LocalMemBar removed in a same-scope store→load, 0258) did NOT go red in 940 launches under either
setting, so it cannot serve as the guard; the guard used is F2 — the `SetFlag/WaitFlag<V_MTE3>` pair
before the MTE3 copy-out removed — which is a deliberately un-synchronised path the classic API
documents as requiring ordering, and which went red. F2's redness is confined to the first launch of a
process because UB retains the previous launch's correct result across launches (the harness copies the
same input each rep) — a sensitivity limit of this fixture, recorded. F3 (`DataCopyScatter` in scope,
then MTE3 out, with/without `LocalMemBar`) — upstream's own "crashes above a size threshold" case — did
not go red at these sizes.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated. An aggregate would let a timing result stand in for a
correctness result, and the two positions in conflict are about different things.

`bits_identical` (Arm 1) — true iff every one of the 5 shapes × 50 repetitions produces byte-identical
output between A and B, under both auto-sync settings. **One** differing byte anywhere sets it false
and settles B2 in favour of position 1. Exit codes are not the verdict.

`barrier_cost_frac` (Arm 2) — Δ(A−B)/A per shape. No pass threshold is declared, because this
variable does not decide the question; it prices it. It is reported with the shape and the run
variance, and a Δ smaller than the observed variance is reported as "below variance", never as zero.

`autosync_reinserts` (Arm 4) — true iff build B's disassembly contains `PIPE_V` barriers absent from
its source. This variable gates the interpretation of `bits_identical`: a true value means Arm 1
tested nothing about hardware ordering, and the verdict on B2 is `NOT ESTABLISHED` regardless of how
clean the bit-compare was.

The positive fixture, declared before the run: build a variant C in which the second VF is made to
depend on the first through a deliberately un-synchronised path known to require ordering — for
example a `LocalMemBar<VEC_STORE, VEC_LOAD>` removed where 0258 says one is required (consecutive
iterations writing and reading the same address). Variant C **must** produce differing bytes against
its barriered counterpart. If it does not, the harness cannot detect an ordering violation at all,
and every `bits_identical = true` it reported is void. This is the guard against the known blind
species: a bit-comparator that has never been shown to go red is a comparator that confirms
cleanliness and nothing else.

## 6 · Evidence
RUN 2026-08-25, 950PR (CANN 9.1.0), device idle before and after each of three jobs.

**Arm 1 — `bits_identical`.** Launches with zero differing bytes / launches run:

| build | auto-sync | shapes | launches | launches with any differing byte |
|---|---|---|---|---|
| two_B (no barrier), round 1 | default | 64…24576 (+200 at 4096, 24576) | 650 | 0 |
| two_B | on | [64, 512, 4096, 10752, 24576] (+200 at 24576) | 490 | 0 |
| two_B | off | [64, 512, 4096, 10752, 24576] (+200 at 24576) | 450 | 0 |
| two_B, round 3 | on + off | 24576 (200 each) | 400 | 0 |
| two_A (barrier) | on / off | same | 290 / 250 | 0 / 0 |

**`bits_identical` = TRUE** under both auto-sync settings.

**Positive fixture F2 — V→MTE3 flag pair removed (first launch of each fresh process is the exposed one):**

auto-sync = on:

| n | reps | bad reps | bad words | first bad (rep, idx, got, ref) |
|---|---|---|---|---|
| 64 | 50 | 0 | 0 | (rep |
| 512 | 50 | 1 | 64 | (rep |
| 4096 | 50 | 1 | 512 | (rep |
| 10752 | 50 | 1 | 4096 | (rep |
| 24576 | 50 | 1 | 10709 | (rep |
| 24576 | 200 | 0 | 0 | (rep |

auto-sync = off:

| n | reps | bad reps | bad words | first bad |
|---|---|---|---|---|
| 64 | 50 | 0 | 0 | (rep |
| 512 | 50 | 1 | 64 | (rep |
| 4096 | 50 | 1 | 512 | (rep |
| 10752 | 50 | 1 | 4096 | (rep |
| 24576 | 50 | 1 | 10709 | (rep |
| 24576 | 200 | 0 | 0 | (rep |

The copied-out values (−199 = 3·(2·(−100)+1) — the previous launch's or the poison's arithmetic where
the reference differs) show the MTE3 copy read UB before the second scope's stores landed. The harness
sees ordering violations. Auto-sync ON did not prevent this violation.

**Variant C as §5 suggested (same-scope store→load without `LocalMemBar`):** 0 differing bytes in
940 launches (on and off) — did not go red; reported. F3 (scatter → MTE3 without / with
`LocalMemBar`): 0 / 0 bad in 900 / 500 launches.

**Arm 2 — `barrier_cost_frac` (msprof `aiv_total_time`, min over 10 launches, µs):**

| n (fp32) | auto-sync | two_A (barrier) | two_B (none) | Δ (A − B) | Δ / A |
|---|---|---|---|---|---|


Host-timed medians agree in ordering (round 1: 5.3 vs 5.9 at n=64 is launch-overhead noise; the
device numbers above are the readout).

**Arm 3 — auto-sync.** `bisheng --help` on this pin lists `--cce-auto-sync=<on|off>`, `--cce-auto-sync`
(alias on), `--cce-remove-auto-sync=<value>`, `--cce-auto-sync-log=<file>`. Default build md5 ==
`on` build md5 for every variant; `off` builds differ. Behaviour identical across the two (tables above).

**Arm 4 — not obtained as a count** (§4 as-run). The `-g` + log builds compile, run correctly, and write
no log file at a relative or an absolute path (directory listing empty after the build).

Sources and logs: verification run's log area b2_0259 / b2b_0259 (build errors: the log flag needs `-g`) /
b2c_0259 / b2d_0259.

## 7 · Scope limits — what this entry does NOT establish
One board (950PR), one pin (9.1.0), one pattern: two regbase `__VEC_SCOPE__` segments with a UB
read-after-write dependence, fp32, ≤ 24576 elements, single core, direct launch. Not probed: an
op-framework build (TQue `EnQue/DeQue` CopyOut — position 3's edge), a `__simt_vf__` followed by classic
vector code, `PIPE_MTE2` / `PIPE_MTE3` barriers on overlapping addresses (0261 — position 2 states a
POSITIVE requirement there, untouched here), multi-core, or shapes above two UB buffers. The absence of
a compiler-inserted barrier in build B is inferred from the `--cce-auto-sync=off` control (different
binary, same behaviour) and from auto-sync's failure to rescue F2 — not from an instruction count; a
compiler that inserts the same barrier regardless of the flag is not excluded by this evidence, only made
implausible. F2's redness is a first-launch effect (UB persistence across launches), so its per-launch
sensitivity is low; a fixture with a fresh input per launch would be sharper. 0258's `LocalMemBar` rule
is neither confirmed nor refuted: the store→load pattern here never failed, which is consistent with the
hardware ordering it, with the compiler ordering it, or with the race window being too narrow at these
sizes. 950DT untouched. Nothing transfers to the other book (RULES.md Art. 1).

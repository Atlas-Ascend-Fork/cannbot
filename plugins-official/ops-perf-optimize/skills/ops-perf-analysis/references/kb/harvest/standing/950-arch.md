# Standing questions — domain `950-arch`

Per-agent file for the 950-arch harvest block (`book-950/entries/0201-0299`), for merge into
`book-950/STANDING_QUESTIONS.md` by the controller in wave 2. Each question is a named measurement
owed, answerable only on a card, cross-linked to the entries it gates.

Nothing below has been run; harvest touches no device (RULES.md Art. 6).

---

## Q-950arch-01 · B1 is RESOLVED as far as headers can resolve it — what remains is a compile
`950:0246` establishes from the installed CANN 9.0.0-beta.2 headers that `MulAddDst` and `MulDstAdd`
are two distinct `AscendC::Reg::*` templates with different dtype sets and different lowerings
(`vmula` / `vmadd`). A header declaration is a second *origin*, not a run. Owed: compile a VF calling
each name for a 3510 target and confirm both resolve; instantiate each at `int32_t` and confirm the
dtype partition is enforced by the `static_assert`s rather than merely written in them.
Gates: `950:0246`, `950:0247`, `950:0248`, and every the delivered skill statement that names an FMA API.

## Q-950arch-02 · which operand of `MulDstAdd` is the destination (B1's second half)
`950:0247` rests on one upstream card plus vendor implementation *comments*. Owed: the crafted
evaluation with `dst=3, src0=5, src1=7` — 22.0 under vec-03's reading, 38.0 under the
instruction-cost JSON's. One run decides it and simultaneously settles `C-950arch-003`.
Gates: `950:0247`, `950:0248`.

## Q-950arch-03 · B2 — is a `PipeBarrier<PIPE_V>` needed after a VF on 950
`950:0259` lays out four upstream passages and three positions, all one origin. Owed: the isolated
toggle — bit-compare AND timing, barrier the only variable, auto-sync ON and OFF as a fourth build
pair, disassembly cross-check to confirm the compiler did not reinsert the barrier into the
no-barrier build. Without the auto-sync arm a null result is unattributable.
Gates: `950:0259`, `950:0260`, `950:0261`, and every generated VF epilogue.

## Q-950arch-04 · B3 — is 950 UB 248 KB, and how much of it is usable
`950:0209` finds `ub_size=253952` in all 32 installed DAV_3510 inis and in agreement with npu-arch;
192 KB and 256 KB appear in four other upstream documents. Owed: `GetCoreMemSize(UB)` on a full part,
**and** the allocation boundary, which is the only thing that distinguishes physical from usable and
would surface a reservation like `topk_host_tiling.md:209`'s "240 KiB usable of 248 KiB physical".
Gates: `950:0209`, `950:0238`, `950:0239`, C-003, C-004, C-006, and every reduction budget.

## Q-950arch-05 · what does `GetRuntimeUBSize()` return in each SIMT regime
Upstream states 216 KB mixed / 248 KB non-mixed; three upstream files derive 216 from a 256 KB base
that no installed 950 ini reports. The arithmetic coincidence `256−8−32 = 248−32 = 216` makes this
undecidable on paper. Owed: call the accessor in a mixed and a non-mixed SIMT kernel, and separately
bisect the allocation boundary in each — a reported size and an allocatable size differ by the 8 KB
compiler reservation, which is the whole question.
Gates: `950:0238`, `950:0237`, `950:0239`.

## Q-950arch-06 · what is a DCache reservation worth
Upstream states a 32 KB minimum and a 128 KB maximum, and its own recommended snippet reserves the
maximum without saying why. No source in scope prices the choice. Owed: the value curve (discrete
gather, residual swept 32/64/96/128 KB) **and** the cost curve (a kernel whose tiling actually
consumes UB), on one die in one session. Either curve alone is half the trade.
Gates: `950:0237`, `950:0239`.

## Q-950arch-07 · does the DCache compile check cover a runtime-computed residual
`950:0237` records upstream's claim that a build check fires when DCache falls below 32 KB. A
compile-time check cannot see a `SetLocalMemorySize` value computed on the host from shape. Owed: the
two-arm build — constant residual and runtime residual — and a record of what happens at launch for
the second. If the guard is compile-time-only, the delivered skill must say so.
Gates: `950:0237`, `950:0239`.

## Q-950arch-08 · is `arch35` used as a build selector anywhere, and what does it select
`950:0202` and `950:0205` establish that `arch35` names two `NpuArch` values in this install. What is
*not* established is whether any build system actually routes on the two-digit form rather than on
`__NPU_ARCH__ == 3510`. Owed: build one kernel behind each selector for a 950 target and compare
what is chosen. The risk is entirely in the answer to this question.
Gates: `950:0202`, `950:0203`, `950:0205`.

## Q-950arch-09 · does the per-dtype `[DtypeMKN]` table describe the Cube array
`950:0220` and `950:0221` read the ini section as array shapes, following upstream's own derivation.
Owed: throughput ratios fp8/fp16, int8/fp16, int4/fp16, fp32/fp16, int32/int8 on one die in one
session, plus the `baseK` plateau sweep that makes the ratios attributable to array width rather than
to anything else that scales with precision. HiF8, MXFP8, MXFP4 and HF32 have **no ini row at all**
and rest on one upstream assertion each.
Gates: `950:0214`, `950:0220`, `950:0221`, `950:0222`, and every Cube roofline.

## Q-950arch-10 · is the vector register 256 bytes or 256 bits
`950:0219` and `C-950arch-008`. The ini field carries no unit; three upstream sources say bytes and
one JSON suffix says bits. Owed: `GetVecLen()`, plus the poisoned-store lane count at two dtypes
(fp32 → 64 and half → 128 under bytes; 8 and 16 under bits), plus the overrun count beyond the
expected extent. The two dtypes must move together by a factor of two.
Gates: `950:0219`, `950:0273`, `950:0252`, and every VF loop bound.

## Q-950arch-11 · the warp width of 32 and the four warp schedulers
`950:0234`. Neither has an accessor and neither has an ini field; upstream marks the scheduler count
as a public-or-experience value and marks the warp width as nothing at all. Owed: the thread-count
staircase (steps at 33/65/97 under a 32-lane warp) with the divergence control that must flatten it,
and the warp-occupancy staircase with a second workload body — a knee at 4 that moves when the body
changes was never measuring schedulers.
Gates: `950:0234`, `950:0235`, `950:0240`.

## Q-950arch-12 · the register band edges and the SIMT register file
`950:0236`. The four bands multiply to ≈128 KB, which is upstream's own unverified register-file
figure, so the table is self-consistent and unsupported. Owed: the spill staircase at three live-
variable counts, gated on a disassembly showing stack traffic at the same points — a timing knee
without spill instructions is measuring something else.
Gates: `950:0236`, `950:0232`.

## Q-950arch-13 · establish-from-scratch items this harvest partially relocated
The 2026-08-24 deep-dive listed six figures with no upstream authority. Two moved:
**256 B vector-register width** now has an ini field (`vector_reg_width`, `950:0219`), and
**32 B block granularity** has a *neighbouring* field (`ubblock_size=32`) that is a UB block size and
**not** a DataCopy granularity — the two were deliberately not equated. Still unrelocated and owed
first-time establishment: 256 B repeat granularity, cache-line 128 / 256 B, DCache size,
`repeatTimes ≤ 255`. The installed ini additionally supplies `ubbank_size=4096`, `ubbank_num=16`,
`ubsubbank_num=64`, `ubburst_in_one_block=32`, `ubbank_group_num=8`, none of which any upstream
document in scope mentions and none of which is claimed by an entry.

## Q-950arch-14 · `predicate_reg_width=32` does not obviously fit a 128-lane mask
Recorded in `950:0219` §3 and deliberately left unclaimed. 128 b16 lanes would need 128 mask bits;
the field says 32. Either `MaskReg` is per-32-bit-group, or the field means something else, or one
of the two numbers is wrong. Owed: a `CreateMask`/`UpdateMask` probe at b16 and b32 recording how
many lanes one `MaskReg` can actually gate. No entry rests on this; it is logged so the next
harvester does not quietly assume one of the three readings.

## Q-950arch-15 · is `GetVecLen()` usable in a `constexpr` initialiser
`950:0253` records that the canonical VF loop template hardcodes `constexpr uint32_t kRepF32 =
256 / sizeof(float)` while `950:0252` (from another skill) forbids exactly that. **Which defect this is
depends on one file read**: if `GetVecLen()` is `__simd_callee__` rather than `constexpr`, the
substitution is ill-formed and the literal is forced, not careless — the entry then moves from `trap` to
`boundary` and 0252's rule is unimplementable as literally stated. Owed: locate `GetVecLen()`'s
declaration in `include/ascendc/basic_api/interface/reg_compute/` (`grep -R`, not `-r`) and compile the
substitution. Cheapest open item in this block.
Gates: `950:0252`, `950:0253`, `950:0219`.

## Q-950arch-16 · does `MicroAPI` RESOLVE to `Reg`, not merely share its names
`950:0244` located `namespace MicroAPI = Reg;` at `kernel_macros.h:136` in the installed CANN
9.0.0-beta.2, exactly where upstream said it would be — but a declaration read is not a compile. Owed:
the `static_assert(&Reg::X == &MicroAPI::X)` form, plus a symbol-by-symbol sweep of
`reg_compute/` under both spellings. Two namespaces carrying the same names is not an alias, and the
whole 950 card library is written in the `MicroAPI` spelling while the whitelist governs `Reg::*`.
Gates: `950:0244`, `950:0245`, `950:0250`.

## Q-950arch-17 · how much of the `reg_compute/` surface does the whitelist omit
`950:0245` records that the whitelist's absence rule is the correct procedure and that it worked twice
during this harvest (B1's `MulDstAdd`, the `MicroAPI` alias). What is unmeasured is how often it will be
needed: enumerate every symbol in `include/ascendc/basic_api/interface/reg_compute/` and diff against the
whitelist's VF-safe tables. A large difference means the escape hatch is the primary path rather than an
exception, which changes how the delivered skill should present the tables. File read; no device.
Gates: `950:0245`, `950:0246`, `950:0250`.

## Q-950arch-18 · are the twelve VF hard constraints enforced, and what happens when they are not
`950:0254`. Upstream calls them 硬约束 and names no mechanism for any of the twelve. Owed: one violation
per build, thirteen builds plus a control, recording for each whether it compiles, whether the diagnostic
names the constraint, and — the payload — whether it produces correct output. Constraints 3 (`uint16_t`
induction), 4 (no arrays) and 6 (no runtime `if/else`) have plausible silent-degradation shapes
(scalarisation, spill) that a compile-only check would miss. Compile-only plus disassembly; no device
needed for the decisive arms.
Gates: `950:0254`, `950:0253`.

## Q-950arch-19 · the `LocalMemBar` five-row partition, and keeping it apart from B2
`950:0258`. Three rows say "not needed" and two say "needed"; the over-application error is the one
upstream emphasises, so both directions must be exercised. **Do not share a run with Q-950arch-03**:
`LocalMemBar` is a VF-internal `__simd_callee__` primitive and `PipeBarrier<PIPE_V>` is a kernel-side pipe
barrier, and resolving one with the other's evidence is a live hazard — upstream's arch35 ordering
guarantee is stated for *between* VFs, not *within* one.
Gates: `950:0258`, `950:0259`.

## Q-950arch-20 · is the 950 Vector roofline actually a lower bound
`950:0264`. The model is `max(mte2, vector, mte3)` plus four calibrated corrections, and three of the
four only matter in the small-shape / few-tile / uneven-split regimes where operators actually get
written. Owed: the theory-versus-measurement sweep across nine operators and seven shapes, **with each
correction ablated in turn** — an unablated model that fits says nothing about which of its five terms did
the work. A measured latency below `theoretical` anywhere kills it.
Gates: `950:0264`, `950:0266`, `950:0267`, `950:0270`.

## Q-950arch-21 · re-derive the 56-row instruction cost table, per row
`950:0266`. Upstream ships the calibration instrument and its committed board data, so this is a
re-derivation rather than an invention. Two things a per-instruction sweep cannot reach and that need
their own arms: the **issue-slot contention** claim (a `1slot` reduction and a `1slot` Pack must degrade an
`Add` stream the same way — one mixed kernel being slow is an anecdote), and the **transcendental
overlap** claim, which is the one modelling assumption in the Vector time model that is not a
per-instruction number. Also owed: `uncovered_apis` — `Reg::*` symbols with no row at all.
Gates: `950:0266`, `950:0267`, `950:0264`.

## Q-950arch-22 · can `check_calibration.py` fail
`950:0272`. The calibration discipline ("绝不为让某个算子通过而调常量") is the strongest evidence-culture
statement in this scope, and its enforcement is unverified. Owed: run the shipped gate, then perturb one
constant in a scratch copy and require the gate to fail **naming that constant**. A gate observed only in
its passing state has not been shown to be a gate — and the audit arm has its own version of the same
trap: a history audit that finds zero unaccompanied constant edits counts only if it was first shown to
detect upstream's own documented 112-MB change-and-revert.
Gates: `950:0272`, `950:0266`, `950:0270`.

## Q-950arch-23 · does SIMT direct GM access actually beat a staged SIMD gather, and where
`950:0243`. Upstream gives two qualitative lists (Gather/Scatter/hash/sort vs dense matmul/long sequential)
and **no crossover point**. The capability and the benefit are separate claims: Arm A establishes that a
`__gm__` dereference in a `__simt_vf__` compiles and is correct; Arm C establishes where it wins. Owed
with the sweep: index locality contiguous → shuffled, and the DCache residual arm (32/64/128 KB), which
is the only thing that would tell a tiling routine what to reserve for a gather-shaped operator.
Gates: `950:0243`, `950:0237`, `950:0239`, `950:0270`.

## Q-950arch-24 · the MC² constraint rows and the A5 window offset
`950:0274` and `950:0277`. Two multi-card items, both needing ≥2 cards and both with predicted **hang**
outcomes, so a declared watchdog timeout and card release are mandatory — an un-timed arm holds the group
on a shared machine. For 0274: one violation per run across the five `headMSize` rows, recording where
each fails (host derivation / allocation / run time) or that it does not. For 0277: dump the first 2 MB of
`windowsIn[rankId]` against a known partner-written payload and read off the offset — the whole claim is
one number, and an offset of 0 would mean every kernel written to the rule is reading 1 MB into its own
payload. Capture protocol for both: ≥10 iterations, first 5 discarded, mean of last 5, **max across
ranks** (a mean would hide the straggler that sets the latency).
Gates: `950:0274`, `950:0277`.

## Q-950arch-25 · every published throughput figure is arithmetic — measure one and the pedigree tiers become visible
`950:0222` (Cube), `950:0223` (Vector), `950:0224` (bandwidth). These three have **different evidential
status and are printed in one table**: Cube TFLOPS is arithmetic over four ini fields (corroborated
inputs, no measurement); the Vector base is ini-derived but its ×2 dual-issue factor is a
public-or-experience value upstream itself qualifies ("并非所有 Vector 指令均支持双发"); bandwidth has no
ini field at all and is the weakest number in the hardware table. Owed, in priority order: the paired
`2slot`-vs-`1slot` instruction-mix ratio (`950:0223` Arm B — a single-arm throughput number attributes
nothing to dual issue), then single-core Cube MACs/cycle with the `baseK`-halving control, then sustained
streaming above L2. Note that upstream's own table marks the Vector rows `[¹]` and the Cube rows not,
which reads as a confidence claim the derivation does not support.
Gates: `950:0222`, `950:0223`, `950:0224`, `950:0214`, `950:0220`, `950:0221`, `950:0264`, `950:0270`.

## Q-950arch-26 · the three CV path changes, and the one that breaks ported kernels
`950:0225` (L0C→UB, UB→L1 added), `950:0226` (L1→GM, GM→L0A/L0B **deleted**), `950:0227` (SSBuffer).
The deletion is the item to run first: upstream states it in a trailing blockquote after three numbered
additions, and a port that relied on those paths fails in an unknown way. Owed for `950:0226`: attempt
both deleted paths and record which of three outcomes occurs — refused at build, refused at run, or
**silently substituted with the two-hop route**, which is the branch with no detector and which doubles
MTE traffic invisibly. For `950:0227`: search the headers for an SSBuffer API at all; `not-exposed` is a
live outcome and would make the tabulated 256 KB unaddressable. For `950:0225`: the GM-byte delta, not the
duration, is the attributable measurement.
Gates: `950:0225`, `950:0226`, `950:0227`, `950:0211`, `950:0212`, `950:0264`.

## Q-950arch-27 · does BufferID actually retire the SetFlag/WaitFlag pairing requirement
`950:0228`. `npu-arch` says BufferID 消除原 set/wait 强制配对需求; the regbase sync guidance a 950
implementer actually follows says **SetFlag/WaitFlag 必须成对出现** and is explicitly scoped to Ascend950
(`950:0262`). One repo, two layers, no reconciliation written anywhere. **Safe posture until measured:
keep the pairs** — that branch has a known failure mode and the other has an unknown one. Owed: search
the headers for a BufferID API (file read, cheapest step, decides whether the question is even live),
then the three-variant paired/unpaired kernel with a declared watchdog — a missing wait can deadlock and
an un-timed arm holds a die on the shared machine. Also owed: whether the seven queues upstream lists
reconcile with the four Vector-core pipes the regbase material names.
Gates: `950:0228`, `950:0262`, `950:0259`, `950:0264`.

## Q-950arch-28 · the SIMT execution-model claims that have no magnitude
`950:0235` (branch divergence serialises), `950:0240` (per-core share must be warp-aligned),
`950:0241` (VF declaration contract). All three state a rule and **no cost**: upstream never says what
divergence costs, what misalignment costs, or what violating the declaration contract produces. Each needs
a staircase with a control that isolates the named cause — for divergence, warp-uniform branching must
stay flat while intra-warp branching rises; for alignment, multiples of 32 must sit on one curve and
non-multiples off it. All three rest on the warp quantum being 32 (`Q-950arch-11`), which is itself
unverified with no ini backing — so run that first or the staircases attribute nothing. `950:0241` is
compile-only and is the cheapest of the three.
Gates: `950:0235`, `950:0240`, `950:0241`, `950:0234`, `950:0232`, `950:0243`.

## Q-950arch-29 · is the kernel-side / VF-side API partition enforced, per name
`950:0250`. Thirteen names appear in **both** whitelist tables — `Add`, `Sub`, `Mul`, `Max`, `Min`, `And`,
`Or`, `Xor`, `Adds`, `Muls`, `Compare`, `Select`, `Move` — differing only in a `Yes`/`No` column and a
header root. Owed: per name, compile the kernel-side form inside a `__simd_vf__` and record whether it is
rejected **and whether the diagnostic names the reason**; a name that compiles is a hole the toolchain is
not closing. Also owed (file read, no device): diff both declarations of each dual-listed name on the four
axes — namespace, parameter style, mask/control contract, and precision contract (`Reg::Div`'s 1-ULP
dagger, `950:0249`, is a fourth axis upstream's three do not name). That diff is the table a consuming
agent needs and no upstream document supplies.
Gates: `950:0250`, `950:0244`, `950:0245`, `950:0249`, `950:0258`.

## Q-950arch-30 · the b16 load consumes half a register, which collides with the lane-count rule
`950:0257`. `LoadAlign<T, DIST_UNPACK_B16>` 只加载 VL/2 字节 (64 half = 128B) — so a b16→f32 widening
path steps **64 elements per iteration, not 128**. A naive application of `950:0252`'s rule
(`GetVecLen()/sizeof(T)` = 128 for half) gives twice the correct stride and skips half the data. **No
source states this collision**; it is derived in `950:0257` §2 from a code comment. Owed: poison the
source past the expected extent and count consumed bytes (128, not 256), then run the loop both ways
against a host reference. Also owed: the alignment *symptom* — upstream states the 32-byte requirement and
never says what a misaligned `LoadAlign` does, and fault / shifted / truncated / garbage need different
repairs.
Gates: `950:0257`, `950:0252`, `950:0219`, `950:0253`.

## Q-950arch-31 · α is one data point, and the roofline applies it everywhere
`950:0271`. The read/write HBM contention constant α ≈ 0.3 rests on **one** reported measurement: 32 MB
each way, 1:1 ratio, one part, one date (copy 18.28 µs vs max(read,write) 14.19 µs → α = 0.288). The
roofline applies it at every size and every ratio. Owed: sweep transfer size 4→256 MB and recompute α at
each point (if it drifts, the correction is a curve and the scalar is a fit at one size); sweep the
read:write ratio 1:1→8:1 (the `max + α×min` form predicts the penalty vanishes as the ratio grows).
Also owed: whether `gm_rw_contention` and `l2_aware` **double-count** — upstream says the `l2_aware` curve
已含读写争用 and never says the two knobs are exclusive. Fixture: a pure-read and a pure-write arm must
show no contention penalty, or the harness is attributing something else to α.
Gates: `950:0271`, `950:0270`, `950:0264`, `950:0218`.

## Q-950arch-32 · L2 is the one buffer that is shared, and every figure for it is sole-tenant
`950:0218`. UB, L1, L0A/B, L0C and BT are invariant across all 32 installed 950 ini files; **L2 and the
core counts are the two that move** — L2 spans 16, 32, 96, 112 and 128 MB. Upstream publishes two of the
five. Worse, L2 is cross-core shared, so every residency figure in this block (`950:0270`'s knee included)
is implicitly a sole-tenant figure and neither origin says so. Owed: the knee sweep **per SKU**, plus the
co-tenant arm — run the sweep again with another kernel streaming on the same die and require the knee to
move down. If it does not move, the sweep was never measuring L2 residency. This matters directly for the
shared machine these runs happen on.
Gates: `950:0218`, `950:0270`, `950:0264`, `950:0217`.

---

## Method notes owed to the controller (not measurements)

**The form checker is line-oriented and a wrapped phrase evades it.** `tools/check_entries.sh:58`
requires the literal string `upstream asserts` in a harvested entry. Entry `950:0221` failed the
check with the phrase present but split as `Upstream\nasserts` across a line break; it passed after
the line was rewrapped, with no change of meaning. Same species for any other single-line predicate
in that checker (`INDEX: *none`, `NOT YET RUN`, the `## N ·` headings). Not repairable from this
block — `tools/` is outside its write partition — so it is reported rather than fixed. A checker that
can be satisfied or evaded by line wrapping is checking the wrapping.

**Two deep-dive claims failed re-verification** and are corrected inside `950:0259` §3 rather than
here: the `vf-microapi-patterns.md:347` position is about `PipeBarrier<PIPE_ALL>` *inside* a
`__VEC_SCOPE__`, not `PIPE_V` after a VF; and positions 2 and 4 of the four ("hardware guarantees
order" and "the compiler inserts barriers") are compatible, not mutually exclusive as the survey
stated. The survey located the material correctly and characterised two of the four passages more
sharply than the files support.

**A third re-verification correction, logged against my own entry rather than a survey.** The 2026-08-24
deep-dive listed "256 B vector-register width (hence VL_FP32=64)" among six figures with **no upstream
authority**, to be established from scratch. That is now partly wrong in two directions and both are
recorded in `950:0219`: the installed CANN 9.0.0-beta.2 ini carries a named `[AICoreSpec]` field
`vector_reg_width=256`, so the figure has a second origin; and three upstream files state VL = 256 B in
prose, so it had upstream authority the survey did not find. What the survey got right is that nothing
had *measured* it. The neighbouring `ubblock_size=32` was deliberately **not** equated with the
deep-dive's "32 B DataCopy block granularity" item — a UB block size and a copy granularity are different
quantities, and equating them would be the inference this book exists to refuse.

**One checker-satisfying rewrite, self-reported.** Entry `950:0221` failed `check_entries.sh` with the
required phrase present but wrapped as `Upstream\nasserts`. The fix was a line rewrap with no change of
meaning. Recorded because the *fix satisfying the marker* is not the same as the entry having been
wrong — and a checker a rewrap can satisfy is a checker that can be satisfied without the property.

> 2026-08-24 correction to Q-950arch-11 (from the 950-remainder miner, applied by the controller):
> "neither has an accessor" is half wrong — `GetWarpSize()` is declared at
> `kernel_simt_common_intf.h:28`, and `warpSize` defaults four shuffle primitives. Still true: no
> ini field, never measured. 950:0234 §4 corrected in place with a dated note.

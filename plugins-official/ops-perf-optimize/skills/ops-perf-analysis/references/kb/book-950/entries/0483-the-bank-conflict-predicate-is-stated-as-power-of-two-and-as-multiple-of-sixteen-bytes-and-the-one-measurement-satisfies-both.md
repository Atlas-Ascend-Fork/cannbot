```
ID:        0483-the-bank-conflict-predicate-is-stated-as-power-of-two-and-as-multiple-of-sixteen-bytes-and-the-one-measurement-satisfies-both
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo). 2026-08-25: the §5 guard-2 fixture RAN on
           950PR and went RED on its counter half (time 5.5× reproduced, conflict counter ≈0) — no
           verdict issued; see §4 as-run note 2, §6, and 950:0489 for the adjudication
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/cum_lane_parallel_scan.md:82-88
           — "段长 `S` 同时就是 lane 间的 UB 地址步长。**步长取 2 的幂时 VLC 条 lane 的 gather 全撞在
           同一批 bank 上**，实测 `R=4096` bf16（S=32）比错位版本慢 5.5 倍（160 µs → 887 µs）。 /
           规则：`S * sizeof(C)` 是 16 的整数倍时取奇数错开（`S |= 1`）； / 否则保持原样。步长本来就
           细碎的情况（如 `S=4`、fp16 → 8 B）不必错位， / 因为错位会把补齐区从 `R` 撑到 `VLC·S`，
           白算一截——`R=511` 时错位反而慢 15%。" ; :90-95 — "int64_t SegLen(int64_t r, int64_t lanes,
           int64_t cBytes) / { / int64_t s = CeilDiv(r, lanes); / return (s * cBytes % 16 == 0) ?
           (s | 1) : s; / }"
SOURCE:    same shelf, templates/usage_guide.md:121-122 — "**段长必须防 bank 冲突**：gather 的 stride
           是 `S * sizeof(C)`，一旦是 16B 的倍数， / 所有 lane 落到同一 bank，实测 case3 慢 **5.5 倍**。
           把 `S` 强制取奇数即可绕开。" ; guide.md:187 — "**取 2 的幂会撞 bank，实测慢 5.5 倍**" ;
           guide.md:270 — "段长即 lane 间步长，**取 2 的幂撞 bank 慢 5.5 倍**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a lane-parallel gather on a named 950 board at a segment stride that is a multiple of 16
           bytes but NOT a power of two — 48 bytes, say — measured against an odd-length neighbour.
           A conflict there supports the 16-byte predicate and kills the power-of-two one; no conflict
           supports the power-of-two predicate and shows the shipped `SegLen` perturbs strides that do
           not need it. Either way one of the two published rules is wrong, and the single existing
           measurement cannot say which.
```

# 0483 · The bank-conflict predicate is stated as power-of-two and as multiple-of-sixteen-bytes, and the one measurement satisfies both

## 1 · Claim
Upstream asserts, for the lane-parallel scan's virtual transpose, that the segment length `S` is also
the inter-lane UB address stride of its gather, and that a bad stride puts every lane on the same bank
group. Upstream states the bad-stride condition **two incompatible ways**. In the template that
implements it, and twice in the family index, the condition is that the stride is a **power of two**.
In the same template's remedy rule, in its shipped code, and in the integration guide, the condition is
that `S * sizeof(C)` is a **multiple of 16 bytes**, remedied by forcing `S` odd. Upstream asserts one
measurement: `R = 4096`, bf16, `S = 32`, 160 µs against 887 µs, a factor of 5.5. Upstream asserts a
counter-example to the remedy: at `R = 511` the odd-length perturbation is 15% *slower*, because the
padding region grows from `R` to `VLC·S`. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent implements whichever predicate it read, and the two disagree on a large
set of strides. Every power of two above 16 bytes is a multiple of 16, so the power-of-two rule is
*strictly narrower*: strides of 48, 80 and 112 bytes are multiples of 16 and are not powers of two.
An agent that implements the power-of-two rule leaves those unperturbed; an agent that implements the
16-byte rule perturbs them. One of the two does unnecessary work, and this book cannot say which.

The normal checks do not catch it because both implementations are correct — bank conflicts cost time,
not accuracy — and because the *remedy* is cheap enough that over-applying it looks free. It is not
free, and upstream says so in the same paragraph: forcing `S` odd grows the padded region from `R` to
`VLC·S`, and at `R = 511` that costs 15%. So the over-application has a measured price and the
under-application has a measured price, and they are measured at different shapes.

**This book already carries the 16-byte form** at `0133`, harvested from the analysis shelf, together
with the 5.5× figure. What is new here is that the same shelf-set states the predicate the other way
three times, and that the counter-example exists. `0133` should be read with this entry beside it; the
16-byte form is cited only to the three sites that state it.

## 3 · Ground / Source
The template's diagnosis and its remedy, `templates/cum_lane_parallel_scan.md:82-88`:

```
段长 `S` 同时就是 lane 间的 UB 地址步长。**步长取 2 的幂时 VLC 条 lane 的
gather 全撞在同一批 bank 上**，实测 `R=4096` bf16（S=32）比错位版本慢 5.5 倍
（160 µs → 887 µs）。

规则：`S * sizeof(C)` 是 16 的整数倍时取奇数错开（`S |= 1`）；
否则保持原样。步长本来就细碎的情况（如 `S=4`、fp16 → 8 B）不必错位，
因为错位会把补齐区从 `R` 撑到 `VLC·S`，白算一截——`R=511` 时错位反而慢 15%。
```

**The diagnosis and the rule are in consecutive paragraphs and they are different predicates.** The
first sentence says the *cause* is a power-of-two stride. The second says the *test* is a 16-byte
multiple. Nothing between them explains the gap.

The shipped code takes the second, `:90-95`:

```cpp
int64_t SegLen(int64_t r, int64_t lanes, int64_t cBytes)
{
    int64_t s = CeilDiv(r, lanes);
    return (s * cBytes % 16 == 0) ? (s | 1) : s;
}
```

So the implementation is the 16-byte rule, and the two family-index statements are the power-of-two
rule: `guide.md:187` — `**取 2 的幂会撞 bank，实测慢 5.5 倍**` — and `guide.md:270` — `段长即 lane
间步长，**取 2 的幂撞 bank 慢 5.5 倍**`. The integration guide takes the 16-byte rule,
`templates/usage_guide.md:121-122`: `gather 的 stride 是 S * sizeof(C)，一旦是 16B 的倍数，所有 lane
落到同一 bank，实测 case3 慢 5.5 倍。把 S 强制取奇数即可绕开。` Three sites for each form, and the
same 5.5× figure attached to both. Registered as `C-950fin-025`.

**The single measurement adjudicates neither.** `R = 4096`, bf16, `S = 32`. Under the native 16-bit
comparison path `sizeof(C) = 2` and the stride is 64 bytes; under the fp32 promotion this same shelf
mandates for the lane-parallel path (`usage_guide.md:75`, `走 lane 并行扫描时必须反过来（一律升
fp32）`) `sizeof(C) = 4` and the stride is 128 bytes. **Both values are powers of two and both are
multiples of 16.** So the one case that was measured satisfies both predicates, and no measurement in
the shelf separates them. A stride of 48 or 80 bytes would; none is reported.

The counter-example the book does not yet carry, `:88`: `R=511 时错位反而慢 15%`, with its mechanism —
the odd `S` grows the padded region from `R` to `VLC·S`, and every step of phases one and three runs
over the padded length. So the remedy's cost scales with `VLC·S − R`, which is largest when `R` is
just above a multiple of `VLC`. Upstream gives one point (`R = 511`) and no curve.

Two further quantities the predicate rests on are undefined in this shelf: `VLC`, the lane count of a
vector register, and `C`, the comparison type. `0138` records `VLC` and `VREG` as never defined or
given units, and `C` is set by a selection rule that the shelf's own trajectory table later reverses
(`0486`). So `S * sizeof(C) % 16` depends on a type chosen by a rule that changed.

Finally, the bank geometry itself. This book carries, from the architecture block and the installed
`platform_config` ini, that DAV_3510's UB has 16 banks of 16 KB in 8 groups of two (`0314`), and that
on DAV_3510 two reads of one bank group do **not** conflict — the one rule that differs from the other
architecture (`0315`). Neither predicate in this shelf mentions bank groups. Whether `% 16` or
power-of-two is the right test on a geometry where paired banks do not conflict is exactly the question
`0315` makes live, and no document in this shelf touches it. Recorded as `Q-950fin-29`.

One repository, one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first, beside every point.

**Arm 1 — the separating strides, which is the whole entry.** A lane-parallel gather at fixed `R` and
`VLC`, sweeping `S * sizeof(C)` over: powers of two (32, 64, 128, 256), multiples of 16 that are not
powers of two (48, 80, 112, 144), odd multiples of `sizeof(C)`, and a control not a multiple of 16.
Report `aiv_time` **and** `ResourceConflictRatio`'s `bank_cflt` at each — the shelf's own排查 method
(`usage_guide.md:87`) and this book's `0317`, which records that a bank conflict is confirmed by the
conflict counter and never inferred from vector time. The 48/80/112 group is where the two predicates
disagree and it is the only group that matters.

**Arm 2 — the counter-example's curve.** Sweep `R` across `VLC·S` boundaries — `R ∈ {480, 500, 511,
512, 520, 600}` at fixed `VLC` — with `S` forced odd and left alone, reporting the padded length
`VLC·S` and the time for each. Upstream gives one point (15% at `R = 511`); this arm gives the curve
and the `R` at which the remedy stops paying, which is the number `SegLen` would need to be correct.

**Arm 3 — the bank geometry.** Repeat arm 1 with the stride chosen to put pairs of lanes on the two
banks of one group, per `0314`'s geometry, and confirm against `0315` that the pair does not conflict.
If it does not, the correct predicate is about bank *groups* rather than banks, and both published
forms are approximations of it (`Q-950fin-29`).

**Arm 4 — the comparison type, retained because it may not bite.** Repeat arm 1 at `sizeof(C) ∈ {2,
4}` with the same `S`. Since the predicate is on the byte stride, the two must agree when the byte
strides match. If they do not, the predicate is not purely a function of the byte stride and both
published forms are underspecified.

Refuses to assume: that a free die stays free, or that a die may be substituted; that slow means
conflicted (`0317` — every point carries the conflict counter, and a slowdown without an elevated
counter is a different defect); that `VLC` is a known constant (`0138` — it is queried or derived and
echoed); that the two predicates differ only on the strides §3 names (arm 1 sweeps a range); that
padding cost and conflict cost can be separated by timing alone (arm 2 reports the padded length
explicitly).

**As-run note (2026-08-24/25, before any arm produced a verdict):** the lane-parallel UB
gather this §4 requires was BLOCKED on direct launch on the bound pin — a `__simt_vf__`
function runs (GM access green) but every UB access from inside a VF fails with 507035
regardless of allocation route (four tried); upstream's own docs couple UB-in-VF to the
op-framework tiling grant (`SetLocalMemorySize`). **UNBLOCKED 2026-08-25 by mechanism**: the
direct-launch equivalent exists — launch attr `ACL_RT_LAUNCH_KERNEL_ATTR_DYN_UBUF_SIZE` via
`aclrtGetFuncBySymbol` + `aclrtLaunchKernelWithHostArgs` (no attr → 507035 replicated; 4 KB →
507035, value consumed; 64 KB → the full TPipe+VF gather runs, 512/512 sums exact at S=16 R=64
and S=32 R=128). Arms 1–4 now run on direct launch; the timed/bank-conflict geometry readouts
remain the open work. Meanwhile the neighbouring
classic-vector instrument (0314 Arm A) measured NO bank conflicts for strided single-
instruction READS at any stride — consistent with 0315's read-tolerance claim and with this
entry's premise that the phenomenon lives in per-lane concurrent access. Full readouts in
harvest/RUNS_20260824.md.

**As-run note 2 (2026-08-25, the fixture ran; recorded before any arm was classified):** §5
guard 2 was executed first, with upstream's own primitive (`Reg::DataCopyGather`, VLC lanes,
element-index register, the template's exact form) rather than the SIMT vehicle, at both
element widths. The TIME half of the fixture reproduced: S = 32 against S = 33 gave 5.34× at
half (64 B stride, 1275.8 vs 239.0 µs `aiv_total_time`) and 5.96× at float (128 B, 1275.6 vs
213.9 µs). The COUNTER half did not: `aiv_vec_bank_cflt_ratio` stayed below 0.1 % on every
row (0.00062 slow, 0.00033 fast). §5 defines `conflicted(stride_bytes)` on that counter and
forbids deciding by time, so **guard 2 is RED on its counter half and this checker issues no
verdict for any stride** — the 48/80/112 results carry no information *about the counter's
phenomenon*. They carry time information, and that is deliberately not adjudicated here:
950:0489 was drafted with its own §5 (time tiers, counter reported beside, both predicates
named both ways) and is promoted only by a sweep run after its §5 existed. This entry's
question — which predicate upstream should have written — is therefore answered by 0489,
not by this file; this file stays at its stratum with the fixture readouts in §6.

## 5 · Checker — acceptance declared before the run
Verdict `conflicted(stride_bytes)` from arm 1, decided by `bank_cflt` exceeding the control's by a
declared margin — stated now as 5 percentage points — and **not** by time. Declared before the run:
the 16-byte predicate is supported iff every multiple of 16 conflicts including 48, 80 and 112; the
power-of-two predicate is supported iff only powers of two conflict. Both cannot be supported, and
"neither" is a third declared outcome meaning the true predicate is something else (`Q-950fin-29`).

Verdict `remedy_crossover` from arm 2: the largest `R` at which forcing `S` odd is slower than leaving
it, with its floor.

Verdict `pair_conflicts` from arm 3, boolean.

The exit code is not the verdict: every configuration here is correct and differs only in time.
Guards: (1) no stride is classified without its conflict counter — classifying by time alone is the
inference `0317` exists to forbid, and this checker fails red if any point lacks the counter; (2)
**the input that makes this checker go red**: the shelf's own measured case, `R = 4096` bf16 `S = 32`,
which must reproduce a conflict and roughly the 5.5× penalty — if it does not, the harness is not
producing the phenomenon and the 48/80/112 results carry no information; (3) no point is reported
without its `S`, `sizeof(C)`, the derived byte stride, the echoed `VLC`, the padded length `VLC·S`,
the conflict counter's name, the floor and the CANN pin.

## 6 · Evidence
§4's arms were NOT YET RUN to a verdict, and none can be under this §5: on 2026-08-25 the §5 guard-2
fixture ran on 950PR (CANN 9.1.0, `Reg::DataCopyGather`, 32 gathers × 1024 iterations, exact per-lane
sums) and the checker went RED on its own guard — the 5.5× time penalty reproduced (5.34× half at
64 B, 5.96× float at 128 B) while the pre-declared conflict counter `aiv_vec_bank_cflt_ratio` read
< 0.1 % at both the slow and the fast stride. No verdict variable was issued; the stride sweep's
adjudication lives in 950:0489. Nothing in §1 is a measurement. The diagnosis, the remedy rule,
the shipped `SegLen`, the two family-index statements, the integration guide's statement, the single
measured case and the counter-example are file reads performed at drafting time, each re-verified
against its file. The arithmetic in §3 — that `S = 32` at `sizeof(C)` of 2 or 4 gives 64 or 128 bytes,
both powers of two and both multiples of 16 — is a calculation over upstream's own case parameters,
not a measurement, and it is what shows the single measurement adjudicates neither predicate. The bank
geometry cited from `0314` and `0315` belongs to those entries and is not re-established here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish which predicate is right — Art. 7
forbids choosing by plausibility, and §4 arm 1's 48/80/112 group is the procedure that would settle
it. It does not establish the 5.5× penalty, the 15% counter-example cost, or that either was measured
on a 950 board; the scan shelf names no board. It does not establish that the phenomenon is a bank
conflict at all rather than some other stride-dependent slowdown — the shelf's own排查 note records
using `ResourceConflictRatio` for a *different* question (`usage_guide.md:87`, ruling bank conflict
*out* at 0.1%) and never reports the counter for this one. It does not re-establish the 16-byte form
already carried at `0133`, which is cited; it adds the second form and the counter-example, neither of
which `0133` has. It does not resolve whether the right predicate is about banks or bank groups
(`Q-950fin-29`), which `0314` and `0315` make a live question. It does not define `VLC` (`0138`) or
fix the comparison type, which `0486` records as having been reversed. No board token appears in any
of the six cited sites, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where
our run would happen. Nothing here is established for any 910-family board.

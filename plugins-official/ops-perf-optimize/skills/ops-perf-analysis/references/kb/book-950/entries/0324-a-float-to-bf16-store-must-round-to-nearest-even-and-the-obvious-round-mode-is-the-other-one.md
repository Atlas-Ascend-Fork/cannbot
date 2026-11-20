```
ID:        0324-a-float-to-bf16-store-must-round-to-nearest-even-and-the-obvious-round-mode-is-the-other-one
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/precision_and_traps.md:41-57 —
           "if constexpr (AscendC::IsSameType<DST, bfloat16_t>::value) { // f32 -> bf16 必须
           round-to-nearest-even，与 torch 对齐。// CAST_ROUND 是 round-half-away-from-zero，会在
           tie 上差 1 ULP。 AscendC::Cast(outLocal, inLocal, AscendC::RoundMode::CAST_RINT, n); }
           else { AscendC::Cast(outLocal, inLocal, AscendC::RoundMode::CAST_NONE, n); }" ·
           "`CAST_ROUND` 看起来是"正常的四舍五入"，但它是 **round-half-away-from-zero**；torch 用的
           是 **round-to-nearest-even**。差别只在 tie 上的 1 ULP —— 足以让 bf16 的 add 在通用路径和
           纤维路径**双双挂精度**。" · "> 一般规律：**任何 f32 → 窄浮点的落地都先确认舍入模式与参照
           实现一致**，这类 bug 表现为"只差一点点"，极容易被误判成"精度阈值该放宽"。阈值不是用来
           放宽的。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured f32 → bf16 cast on a named 950 board where `RoundMode::CAST_ROUND` and
           `RoundMode::CAST_RINT` produce bit-identical output across a tie-heavy input set — the
           two modes would then not differ on this architecture and the rule would be vacuous.
```

# 0324 · An f32 → bf16 store must round to nearest even, and the obvious round mode is the other one

## 1 · Claim
Upstream asserts that `RoundMode::CAST_ROUND` implements round-half-away-from-zero while the
reference implementation (torch) uses round-to-nearest-even, that the two differ only on exact ties
and only by one ULP, and that this is nevertheless enough to fail a bf16 accumulation's precision
gate on both the generic and the fiber-exclusive scatter paths. Upstream asserts the fix:
`f32 → bf16` uses `RoundMode::CAST_RINT`, and only the bf16 branch does — the fp16 branch keeps
`CAST_NONE`. Upstream asserts the general form of the rule: any narrowing float store confirms its
rounding mode against the reference implementation first, because the failure presents as
"只差一点点" and is easily misread as a threshold that should be relaxed. Upstream states, flatly,
`阈值不是用来放宽的`. Not established here.

## 2 · The wrong branch this removes
`CAST_ROUND` is the name that means "round" and the enumerator an agent reaches for. It is the wrong
one, and the error it produces is the most misdiagnosable kind: correct to within one ULP, on a
subset of inputs, with no structural signature. Every other explanation is more attractive — an
accumulation order effect, a tolerance set too tight for bf16, an unlucky input distribution — and
each of those has a plausible-sounding remedy that makes the symptom go away without fixing
anything.

The remedy an agent will actually reach for is widening the tolerance, and this shelf says why not
in one sentence. A tolerance widened to admit a rounding-mode mismatch admits everything else of
that size too, permanently, for every later change.

The second wrong branch is symmetric over-application: using `CAST_RINT` for the fp16 path as well.
Upstream's own code branches on the destination type and leaves fp16 at `CAST_NONE`, so the rule is
bf16-specific as stated, and this entry does not extend it. Why the two narrow types differ is not
explained anywhere in the source, and §7 records that as a gap rather than filling it.

The third is scope creep in the other direction — reading this as a scatter fact. It is a cast fact.
It appears in a scatter document because that is where the precision gate bit, and upstream
generalises it explicitly in the same paragraph.

## 3 · Ground / Source
`scatter/precision_and_traps.md:41-57`, the whole section:

```
## 2. bf16 的舍入模式必须是 RINT

if constexpr (AscendC::IsSameType<DST, bfloat16_t>::value) {
    // f32 -> bf16 必须 round-to-nearest-even，与 torch 对齐。
    // CAST_ROUND 是 round-half-away-from-zero，会在 tie 上差 1 ULP。
    AscendC::Cast(outLocal, inLocal, AscendC::RoundMode::CAST_RINT, n);
} else {
    AscendC::Cast(outLocal, inLocal, AscendC::RoundMode::CAST_NONE, n);
}

`CAST_ROUND` 看起来是"正常的四舍五入"，但它是 **round-half-away-from-zero**；torch 用的是
**round-to-nearest-even**。差别只在 tie 上的 1 ULP —— 足以让 bf16 的 add 在通用路径和纤维路径
**双双挂精度**。

> 一般规律：**任何 f32 → 窄浮点的落地都先确认舍入模式与参照实现一致**，这类 bug 表现为"只差一点点"，
> 极容易被误判成"精度阈值该放宽"。阈值不是用来放宽的。
```

The claim has three separable parts and they are not equally supported. That `CAST_ROUND` is
round-half-away-from-zero is a statement about an SDK enumerator's semantics, sourced to nothing —
no header is cited. That torch uses round-to-nearest-even is a statement about the reference
implementation. That the difference cost this family its bf16 precision gate on two paths is a
report of an observed failure. Only the third is upstream's own evidence, and it is a disclosure
rather than a measurement: no error figure, no input set, no gate threshold is given.

The `else` branch keeping `CAST_NONE` for fp16 is the part with no stated reason at all. `CAST_NONE`
is not obviously "the same as torch" for fp16; upstream simply does not discuss it.

The neighbouring section of the same file (`0323`) supplies the reason a bf16 accumulation reaches a
cast at all: accumulate-type reduces must run through an fp32 accumulator, so there is exactly one
narrowing store at the end of the chain, and its rounding mode is therefore the whole rounding
budget of the operation. The two entries are a pair: `0323` says accumulate in fp32 and round once,
`0324` says which way that one rounding goes.

Nothing here is measured by this book, and the `1 ULP` is stated, not observed.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the enumerator semantics, isolated from any operator. A kernel that casts a crafted f32
vector to bf16 under each `RoundMode` the SDK declares, where the input is constructed to be
*entirely* ties: values whose bf16 mantissa remainder is exactly one half ULP, in both signs, with
both even and odd retained mantissas. Compare each output against a host reference computed under
round-to-nearest-even and under round-half-away-from-zero. This identifies every mode by behaviour
rather than by name, which is the only way an agent can trust the mapping later.

Arm 2 — the enumerator inventory, which needs no device and is marked `[no-card]`. `grep -Rn` (not
`-r`) for `RoundMode` over the installed toolkit's include roots, recording every enumerator, its
header path and the toolkit pin. Upstream cites no header for its semantic claim, and this is what
would supply one — or show that the headers do not state semantics either, which is itself the
finding.

Arm 3 — the operator-level consequence, reproduced. One bf16 scatter-add case built with
`CAST_RINT` and with `CAST_ROUND`, both compared against an fp64 host reference, reporting maximum
relative error and the *count* of differing elements. Upstream's claim predicts a small number of
elements differing by one ULP, not a broad degradation, and the count is what distinguishes a
rounding-mode mismatch from any other precision fault.

Arm 4 — the fp16 half, which upstream leaves unexplained. The same three-way comparison for
`f32 → fp16` under `CAST_NONE`, `CAST_ROUND` and `CAST_RINT`, against torch's fp16 behaviour. If
`CAST_NONE` is not the torch-matching mode for fp16, upstream's `else` branch is a latent defect and
the entry is corrected in place.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard the case if the die moved. No timing is
involved, so no variance floor is needed; the arms are exact-comparison arms. Refuses to assume:
that enumerator names describe behaviour (Arm 1 exists because they may not); that the host
reference rounds as intended — the reference's own mode is asserted by construction and checked
against a hand-computed table of ten tie values before any kernel output is compared to it; that
torch's behaviour is knowable from documentation alone (it is measured on the same tie set).

## 5 · Checker — acceptance declared before the run
Verdict `mode_map` = the mapping from each `RoundMode` enumerator to observed behaviour on the tie
set, from Arm 1. Declared before the run: upstream is **supported** iff `CAST_ROUND` maps to
half-away-from-zero and `CAST_RINT` maps to nearest-even. Either being different overturns the
entry's mechanism while leaving its advice possibly still correct, and the entry is corrected in
place to name the mode that does match.

Verdict `ulp_diff_count` = the number of elements differing between Arm 3's two builds, and
`max_ulp` = the maximum difference in ULP. Declared: a rounding-mode mismatch predicts
`max_ulp == 1` with `ulp_diff_count` small relative to the tie density of the input. `max_ulp > 1`
means something other than rounding mode differs between the builds and Arm 3 is void.

Verdict `fp16_mode` from Arm 4.

The exit code is not the verdict. Three guards. First — the input that makes this checker go red —
Arm 1's tie set is itself the positive fixture: it **must** produce a difference between at least
two of the enumerators. A cast comparison run on ordinary random data would show all modes agreeing
almost everywhere and would "confirm" any hypothesis; if the crafted tie set shows no difference
between any pair of modes, the input is not hitting ties, the tie construction is wrong, and every
verdict in the run is void. This is the whole methodological content of the arm: the fixture is a
positive the instrument must find, not a clean line it hopes to read.

Second, Arm 3 reports the differing-element count, never only the maximum error. A single max
figure cannot distinguish "one element off by one ULP" from "every element off by one ULP", and the
two have different causes.

Third, no verdict is rendered against a tolerance. This entry's subject is a failure that a widened
tolerance hides, so the comparisons are exact and any "within tolerance" phrasing in the report is a
defect in the report.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No cast was performed, no
ULP was counted, and no `RoundMode` enumerator was located in any header — Arm 2 is answerable in
this phase and has not been run.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The semantics attributed to `CAST_ROUND` and `CAST_RINT` are
upstream's assertion with no header cited and no measurement behind them; §4 Arm 1 is the only thing
here that would establish them, and Arm 2 has not been run even though it costs nothing. The `1 ULP`
figure and the claim that the difference is confined to ties are stated, not observed. Upstream
supplies no error figure, no input set, no gate threshold and no case identity for the failure it
reports, so "双双挂精度" records that something failed, not by how much. The fp16 branch's use of
`CAST_NONE` is unexplained by upstream and unexamined here; if it is wrong, this entry's code
excerpt propagates the defect. Nothing establishes torch's behaviour — it is taken from upstream's
sentence. The rule is stated for `f32 → bf16` and is not established for any other narrowing pair,
nor for the bf16 → f32 direction. BOARD is `950PR`, from the scatter family's provenance note; the
trap file itself names no board, and nothing here is established for 950DT. Nothing transfers to the
other book (RULES.md Art. 1).

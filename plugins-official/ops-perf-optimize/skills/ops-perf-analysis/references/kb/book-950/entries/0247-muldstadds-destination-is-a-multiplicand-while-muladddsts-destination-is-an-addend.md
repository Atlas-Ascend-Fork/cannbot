```
ID:        0247-muldstadds-destination-is-a-multiplicand-while-muladddsts-destination-is-an-addend
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared predicate: MulDstAdd(3,5,7)=22 AND
           MulAddDst(3,5,7)=38, exact, with the declared reference-arm fixture reporting "1 0",
           the operand-swap arm (26≠22), and the int32 arm (38 exact; MulDstAdd refuses int dtypes
           with the SupportType diagnostic). §6 has the readouts. Previously harvested (comments
           beside code, deliberately not corroborated).
BOARD:     950PR (measured 2026-08-25); family elsewhere unverified
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:51
           — "`MulDstAdd(dst, src1, src2, mask)` 语义 = `dst = dst*src1 + src2`（dst 既是源又是目标）。
           **替换前比对 ground truth 的参数顺序**：weight 走 src1、bias 走 src2；写反得到 `x*b+w`，
           静默编译通过但精度错。"
SOURCE:    ops/ascendc-perf-optimize/.../vec-03-fused-instr.md:36 — "MulDstAdd(xR, wR, bR, m);
           // x = x*w + b（in-place）"   # same repo as the line above — ONE origin (RULES.md Art. 3).
INDEX:     MulDstAdd(3,5,7)=22 / (2,3,5)=11 · MulAddDst(3,5,7)=38 / (2,3,5)=17 · swap arm
           MulDstAdd(3,7,5)=26 · int32 MulAddDst=38 exact · reference fixture "1 0".
           Run 2026-08-25, Ascend950PR.
OVERTURN:  a run in which `MulDstAdd(d, a, b, m)` with distinguishable inputs produces `d + a*b`
           rather than `d*a + b`, or `MulAddDst(d, a, b, m)` produces `d*a + b` rather than `d + a*b`.
           With d=3, a=5, b=7 the two hypotheses give 22 and 38 — one run decides it.
```

# 0247 · `MulDstAdd`'s destination is a multiplicand while `MulAddDst`'s destination is an addend

## 1 · Claim
Upstream asserts that `MulDstAdd(dst, src1, src2, mask)` computes `dst = dst*src1 + src2` — the
destination register is one of the *multiplicands* — and warns that swapping the two source operands
compiles silently and produces the wrong number. By contrast, `MulAddDst` places the destination as
the *addend*: `dst = dst + src0*src1`. The two APIs (0246) therefore differ in which role `dst`
plays, not merely in name. Not established here: nothing was compiled and no arithmetic was
performed.

The two names are self-describing once read as phrases — "**Mul** the **Dst**, then **Add**" versus
"**Mul**, then **Add** to **Dst**" — and that is the mnemonic worth carrying, because the signatures
are identical and the compiler cannot help.

## 2 · The wrong branch this removes
This is the trap that 0246's resolution creates. Once an agent knows both APIs exist, both compile,
and both take `(dst, src0, src1, mask)`, the natural conclusion is that they are interchangeable
fused multiply-adds. They are not: on the same three registers they compute different values. A
substitution — made to satisfy the whitelist, or to widen dtype support from `MulDstAdd`'s three
float types to `MulAddDst`'s nine — changes the arithmetic with no diagnostic anywhere.

Upstream names the sibling error inside one API: with `MulDstAdd`, weight must go to `src1` and bias
to `src2`; reversed, you compute `x*b + w` instead of `x*w + b`. That version at least stays inside
one API. The cross-API version is worse, because the agent believes it has performed a rename.

Neither error is caught by ordinary checks. Both compile. Both produce finite, plausible numbers of
the right shape and dtype. A unit test with `dst` initialised to zero cannot distinguish them at all —
`0 + a*b` and `0*a + b` differ, but a test that also sets `src1 = 1` or feeds symmetric data can
easily collapse the difference. The detector has to be designed, which is why §5 fixes the inputs
before any run.

## 3 · Ground / Source
**Upstream** — `vec-03-fused-instr.md:49-54`, the 红线 (stop-rules) block, quoted with its neighbours
because the surrounding rules are what a reader will be scanning:

> ## 红线（Stop rules）
>
> - `MulDstAdd(dst, src1, src2, mask)` 语义 = `dst = dst*src1 + src2`（dst 既是源又是目标）。
>   **替换前比对 ground truth 的参数顺序**：weight 走 src1、bias 走 src2；写反得到 `x*b+w`，
>   静默编译通过但精度错。
> - lane 数用 `GetVecLen()/sizeof(dtype)`，**不要借** `B32_DATA_NUM_PER_REPEAT(=64)` 或
>   `ONE_BLK_SIZE/sizeof(dtype)`——换 dtype/换代会全错。
> - 入参用裸 `__ubuf__ T*`，**不要用 LocalTensor**（封装会阻止 RegTensor 寄存器分配）。

and its worked line at `:36`, which agrees with the rule:

```cpp
        MulDstAdd(xR, wR, bR, m);                             // x = x*w + b（in-place）
```

Upstream states nothing about `MulAddDst`'s operand order anywhere. `regbase_api_whitelist.md` lists
the name and no semantics. So the `MulAddDst` half of this claim has **no upstream statement at all**
and rests entirely on the toolkit reading below — which is why the two halves are kept visibly apart.

**Installed toolkit, read under the phase-1 read-only exception.** CANN `Version=9.0.0-beta.2`,
`innerversion=V100R001C10SPC001B214`, 950-era (see 0246 §3 for the three indications). Four data
points, none of them a declaration:

(a) `arm64-linux/asc/impl/basic_api/reg_compute/dav_c310/kernel_reg_compute_vec_unary_impl.h:388` —
inside a Newton-iteration helper, a comment naming the operand roles of the mnemonic `MulAddDst`
lowers to:

```cpp
    vmula(dstRegCopy, regOne, tmpReg, mask, modeValue);      // x = x + x2*0.5x
```

with `dstRegCopy` = x, `regOne` = x2, `tmpReg` = 0.5x. Read against the comment: `dst = dst + src0*src1`.

(b) the same file, `:395`, the mnemonic `MulDstAdd` lowers to:

```cpp
    vmadd(tmpReg, errReg, resReg, mask, modeValue);      // x2 = x2*err + x1
```

with `tmpReg` = x2, `errReg` = err, `resReg` = x1. Read against the comment: `dst = dst*src0 + src1`.

(c) `arm64-linux/asc/impl/adv_api/detail/math/atan/atan_c310_impl.h:279`, a use of the public API with
both the algebra and the mnemonic in one comment:

```cpp
        Reg::MulAddDst(vreg13, vreg11, vreg14, preg0); // y_if = b1*b2 + (-1.0 * y) //vmula
```

— the destination `vreg13` carries `-1.0*y` on entry and `b1*b2` is added to it.

(d) the b64 fallback path of `MulAddDst` itself, quoted in 0246 §3 from
`kernel_reg_compute_vec_binary_impl.h:1857-1876`, which spells the semantics out in ordinary APIs
rather than an intrinsic:

```cpp
            Mul(traitTwoDstTmpReg, traitTwoSrcReg0, traitTwoSrcReg1, maskTrait2);
            Add(traitTwoDstReg, traitTwoDstTmpReg, traitTwoDstReg, maskTrait2);
```

i.e. `dst = (src0*src1) + dst`. Point (d) is the strongest of the four because it is *code*, not a
comment — but it covers only the 64-bit path of one of the two APIs.

So: (a), (b), (c) are comments written by the vendor's implementers, and (d) is code covering one
branch. Together they are consistent with upstream's vec-03 sentence and with the mnemonic reading of
the names. None of them is a declaration, and none is a run. That is the whole reason this entry sits
at `harvested` while 0246 sits at `corroborated`: 0246's evidence was signatures and `static_assert`s,
which a compiler enforces; this entry's evidence is prose beside code, which nothing enforces.

**A contradicting upstream source, and it is not a small one.**
`ascendc-performance-evaluation/references/vector_instruction_types.json` gives:

- `MulAddDst` → `"semantic_expr": "dst = src0 * src1 + dst"`, `"semantic_description": "multiply then add destination"`
- `MulDstAdd` → `"semantic_expr": "dst = dst + src0 * src1"`, `"semantic_description": "multiply then add into destination"`

Those two expressions are algebraically identical, so that file assigns the two APIs the *same*
semantics and distinguishes them only by an English gloss. Its `MulAddDst` row agrees with this
entry; its `MulDstAdd` row does not, and cites vendor documentation
(`asc-devkit/docs/api/SIMD-API/基础API/Reg矢量计算/复合计算/MulDstAdd.md`) as its source. Carried as
its own entry, 0248, and filed as `C-950arch-003`. Art. 7 forbids resolving it by author plausibility;
§4 decides it in one run.

## 4 · Procedure
Runnable later on `950PR`. The claim is arithmetic, so the procedure is a single crafted evaluation —
cheap, decisive, and designed so no input coincidence can hide the difference.

Choose scalars that separate the two hypotheses maximally and are exactly representable in fp32:
`dst = 3.0`, `src0 = 5.0`, `src1 = 7.0`.

- `dst + src0*src1` = 3 + 35 = **38.0**
- `dst*src0 + src1` = 15 + 7 = **22.0**

No third plausible fused form lands on either value, and neither operand order within a hypothesis
collapses onto the other (`dst*src1 + src0` = 26, `dst + src1*src0` = 38 — the multiply is commutative
so only the *role* of `dst` is under test, which is exactly the claim).

Kernel: a `__simd_vf__` that duplicates the three scalars into three `RegTensor<float>`s, calls one
API, stores, and returns. Two builds, one per API, identical otherwise.

```cpp
template <bool useDstAdd>
__simd_vf__ inline void FmaProbeVf(__ubuf__ float* out)
{
    AscendC::Reg::RegTensor<float> dR, aR, bR;
    AscendC::Reg::MaskReg m;
    uint32_t remaining = AscendC::Reg::GetVecLen() / sizeof(float);
    m = AscendC::Reg::UpdateMask<float>(remaining);
    AscendC::Reg::Duplicate(dR, 3.0f);
    AscendC::Reg::Duplicate(aR, 5.0f);
    AscendC::Reg::Duplicate(bR, 7.0f);
    if constexpr (useDstAdd) { AscendC::Reg::MulDstAdd(dR, aR, bR, m); }
    else                     { AscendC::Reg::MulAddDst(dR, aR, bR, m); }
    AscendC::Reg::StoreAlign(out, dR, m);
}
```

`if constexpr` rather than a runtime branch, per the VF hard constraint forbidding runtime `if/else`
inside a VF body (0254).

Arm B — the sibling error inside one API, which is what vec-03 actually warns about. With
`MulDstAdd`, run once as `(x, w, b)` and once as `(x, b, w)` on distinguishable `w` and `b`, and
record that both compile and produce different results. This arm establishes that the silent-swap
hazard is real rather than hypothetical.

Arm C — the dtype cross-check that ties this to 0246. Repeat the `MulAddDst` arm at `int32_t`, where
`MulDstAdd` cannot be instantiated. Integers make the arithmetic exact and remove any residual
question about rounding in the comparison.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All arms run on one named die in one
session; a result read from a different die attributes nothing.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** The vehicle deviates from the
sketch above in form, not in what is measured: the probe is a regbase `__VEC_SCOPE__` block inside a
direct-launch `__vector__` kernel (the sketched `__simd_vf__` + `Duplicate` form was not used);
operand registers are loaded from GM-fed UB constant regions via
`Reg::DataCopy<LoadDist::DIST_NORM>`, the full mask comes from `Reg::CreateMask<float>()`
(default `MaskPattern::ALL`), and results are stored to distinct UB regions and copied out, with
the surrounding UB poisoned so a stray write is visible. Values are checked at lanes 0 and 63 and
the poison boundary is verified intact. Beyond the plan: a second operand set (d=2, s0=3, s1=5 →
11 vs 17) was run as unplanned corroboration. §5's reference arm was built exactly as declared
(`Reg::Mul` then `Reg::Add`, = 38 by construction). Arm B (operand swap) and Arm C (int32) run in
a follow-up job in the same session on the same die, before §6 is written.

## 5 · Checker — acceptance declared before the run
Verdict variables `v_muldstadd` and `v_muladddst`, each the value of `out[0]`, compared exactly —
these are integers in fp32 and no tolerance is appropriate. Process exit code is not the verdict.

Pass, declared now: `v_muldstadd == 22.0f` AND `v_muladddst == 38.0f`.

The two failure modes are named now so neither can be reinterpreted afterwards. If
`v_muldstadd == 38.0f`, this entry is **overturned**, vec-03:51 is wrong, and
`vector_instruction_types.json` is right — the entry is restratified `overturned`, kept, with the
readout in §6, and 0248 is corrected in the opposite direction. If both values are equal, the two
APIs are genuinely aliases and 0246's distinctness table is what needs correcting, not this entry.

Every value must be checked, not just the one expected: a checker that tested only
`v_muldstadd == 22.0f` and reported success would pass on a run where `v_muladddst` also came back
22.0 — that is the known blind species, reading only the line it expects. Both variables are asserted
in the same predicate for exactly that reason.

The positive fixture, stated before the run: build a third arm that calls plain `Mul` followed by
`Add` in the order `dst = dst + a*b`, giving 38.0 by construction. The harness must report this arm
as matching `MulAddDst` and *not* matching `MulDstAdd`. If it reports the reference arm matching
both, the comparison is not live and every verdict from this checker is void.

Arm B has its own verdict: pass iff the two operand orders give different values. Equal values there
would mean the warning in vec-03:51 describes nothing, which is itself a finding.

## 6 · Evidence
RUN 2026-08-25 — the crafted evaluation, both failure-mode guards, the declared positive fixture,
Arm B and Arm C. 2026-08-25 direct-launch probes, Ascend950PR, bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; probe sources and full logs with the verification run.

- **Main predicate**: `v_muldstadd` = **22.0** and `v_muladddst` = **38.0**, exactly (d=3, s0=5,
  s1=7, all 64 lanes, values checked at lanes 0 and 63, poison boundaries intact). PASS as
  declared. Unplanned corroboration at a second operand set (d=2, s0=3, s1=5): **11.0** and
  **17.0** — the same role assignment.
- **Positive fixture, as declared**: the reference arm (`Reg::Mul` then `Reg::Add`, = 38 by
  construction) matched `MulAddDst` and did NOT match `MulDstAdd` (readout "1 0"). The comparison
  is live.
- **Arm B (silent swap)**: `MulDstAdd(d,a,b)` = 22 vs `MulDstAdd(d,b,a)` = **26** — both compile,
  different numbers; vec-03's swap warning describes a real hazard.
- **Arm C (int32)**: `MulAddDst` at `int32_t` runs and returns **38 exact**; `MulDstAdd` at
  `int32_t` and `int64_t` does not instantiate — verbatim diagnostic: "static assertion failed due
  to requirement 'SupportType<int, half, float, __bf16>()': current data type is not supported on
  current device!" (`dav_3510/kernel_reg_compute_vec_fused_impl.h:101`, and `:105` names the
  `vmadd` lowering in the same diagnostic).

So on this pin and part: `MulDstAdd(dst, s0, s1)` = **dst·s0 + s1** (the destination is a
multiplicand — vec-03 is right) and `MulAddDst(dst, s0, s1)` = **s0·s1 + dst** (the destination is
an addend). The JSON's `MulDstAdd` row (0248, `C-950arch-003`) is measured-wrong.

On the toolkit contact: **a header read is not a run.** The four data points in §3 are comments and
one code fragment inside the vendor's implementation headers, read with `grep`; no compile was
attempted, no device was touched, and no value was computed. Comments can be stale, can be
copy-pasted between neighbouring functions, and are not checked by any tool — the sharpest reason to
distrust them here is that the two comments in points (a) and (b) sit seven lines apart in the same
helper, which is exactly the circumstance in which a copy-paste error would produce two consistent-
looking but wrong annotations. The claim stays at `harvested` for that reason.

## 7 · Scope limits — what this entry does NOT establish
Nothing was computed. The entry does not establish either API's semantics — it records that one
upstream card states `MulDstAdd`'s, that vendor implementation comments are consistent with both, and
that a second upstream file contradicts one of them. It does not establish behaviour on any board:
the headers name none, no 950 part was contacted, and BOARD stays `family-claimed(unverified)`. It
says nothing about the `MERGING` mask mode — both implementations `static_assert` ZEROING only, so the
non-ZEROING behaviour is not merely untested but apparently unavailable, and this entry does not
explore it. It says nothing about accumulation order or rounding: a fused multiply-add that keeps the
product at full width before adding is numerically different from separate `Mul` and `Add`, and
neither origin here addresses that, so the §4 reference arm is a *semantic* control, not a bit-exact
one, and a mismatch there would be informative rather than disqualifying. It does not establish which
of `MulDstAdd` and `MulAddDst` is faster, nor that either matches vec-03's disclaimed external −40 %
figure. Nothing transfers to the other book (RULES.md Art. 1): `dav_c310` is arch35 and no 910-era header
was read.

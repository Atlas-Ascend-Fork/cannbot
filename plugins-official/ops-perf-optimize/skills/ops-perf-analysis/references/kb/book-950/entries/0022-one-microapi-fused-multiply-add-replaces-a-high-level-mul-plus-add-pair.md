```
ID:        0022-one-microapi-fused-multiply-add-replaces-a-high-level-mul-plus-add-pair
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:14 — "high-level vector API 每次调用带固定开销；改用 A5 MicroAPI VF，把「加载-乘加-写回」编译成紧凑指令片段、连续展开、吃满一拍 lane。乘加融合（`dst = dst*src1 + src2`）从两条指令降为一条"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:47 — "外部同类改造实测约 **-40%**（作为预期方向，非本库实测；须以本 case 上板 `aiv_time` 前后确认）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board in which the MicroAPI VF form is not faster than
           the high-level `Mul`+`Add` form at a row length well above one VL — the fixed-overhead
           argument would then be wrong for this architecture, and the borrowed −40% would have
           been imported into a case it does not describe.
```

# 0022 · One MicroAPI fused multiply-add replaces a high-level Mul-plus-Add pair

## 1 · Claim
Upstream asserts (card vec-03) that high-level vector intrinsics carry a fixed per-call cost —
`setVecMask`, repeat header, `PIPE_V` synchronisation — so on A5 a hot loop written with
`Mul`+`Add` (or high-level `FusedMulAdd`) can be slower than on older platforms; and that
rewriting the loop as a RegBase MicroAPI VF, with a single fused multiply-add
(`dst = dst*src1 + src2`) replacing the pair, compiles to a compact, unrolled instruction
sequence that fills a full lane beat. The only number attached is external and disclaimed:
about −40% on a comparable external rewrite, offered as a direction and explicitly not measured
in this library. Not established here.

## 2 · The wrong branch this removes
An agent porting a kernel to A5 keeps the high-level API because it is portable and correct, and
concludes from the profile that the kernel is compute bound and irreducible. The card's claim is
that a large part of that "compute" is per-call scaffolding, not arithmetic. The opposite wrong
branch is to import the −40% as an expectation: it is one external rewrite, of a different
operator, with no shape, no board and no case identity. The card's own handling of that number
is the model this book keeps — the figure is stated, labelled borrowed, and fenced with the
measurement that must replace it before it can be repeated.

## 3 · Ground / Source
`vec-03:6-10` diagnostic: adjacent fusable operator pairs on the VECTOR lane; a hot loop still
using high-level intrinsics and slower on A5 than on the older platform; high `aiv_vec_ratio`
with Compute above 60% of total time and an instruction count that looks large.

`vec-03:23-40` gives the after-form inside the platform fence
(`#if defined(__NPU_ARCH__) && (__NPU_ARCH__ == 3510)`), with `RegTensor<float>` operands,
`uint32_t lane = GetVecLen() / sizeof(float);` (entry 0252), `UpdateMask<float>(normDim)` for the
tail (entry 0038), `LoadAlign`/`StoreAlign`, and `MulDstAdd(xR, wR, bR, m)`. `vec-03:43` states
the calling convention: an `__aicore__` wrapper takes `LocalTensor::GetPhyAddr()` and passes a raw
pointer into the VF; the call site branches on platform and keeps the old path elsewhere.

Stop rules, `vec-03:49-55`, each of which is a separate failure mode:
- the operand order — `MulDstAdd(dst, src1, src2)` means `dst = dst*src1 + src2`, weight in src1
  and bias in src2; writing them the other way compiles silently and computes `x*b+w`;
- the lane count must come from `GetVecLen()/sizeof(dtype)`, never borrowed (0252);
- parameters must be raw `__ubuf__ T*`, not `LocalTensor`, or register allocation is blocked;
- 「VF 段后该有的 `PipeBarrier<PIPE_V>()` 要保留——VF 内部不替你做同步」 (entry 0259);
- a tail beat with fewer than 32 active lanes is not worth converting.

The API name is the subject of a live cross-skill disagreement and of an installed-header check;
that is entry 0246, and this entry defers to it rather than resolving it in passing.

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout; device selection per 0010.
1. Build one normalisation-style kernel two ways from a common source tree: (H) high-level
   `Mul`+`Add`; (V) MicroAPI VF with the fused instruction. Record `md5sum` of both kernel
   objects and of a rebuild of each, so a "difference" that is really a build artefact is caught.
2. Sweep `normDim` over five values from below one VL to 64 VLs, so the fixed-overhead argument
   is tested where it should hold and where it should not.
3. Capture `aiv_time`, `aiv_vec_ratio`, `aiv_scalar_ratio`, five repetitions, median and spread.
4. Run the precision regression on both builds and record the maximum relative error, because a
   fused multiply-add may round differently from a separate multiply and add.

## 5 · Checker — acceptance declared before the run
Verdict variable `vf_gain(normDim) = (aiv_time(H) − aiv_time(V)) / aiv_time(H)`, declared before
the runs. Acceptance of the card's mechanism: `vf_gain > spread` for `normDim` above one VL, and
`vf_gain` decreasing as `normDim` falls, crossing zero at or before the 32-lane tail the card
warns about. A uniform gain across all lengths would refute the stated *mechanism* (fixed
per-call overhead) even while confirming the headline.

The borrowed −40% is not the acceptance criterion and is not compared against; it is recorded in
the report next to the measured `vf_gain` so the two are never conflated.

Exit code is not the verdict. Precision is reported alongside; a build that is faster and less
accurate is not a pass.

Red input: `normDim` below one VL, where the card predicts no gain. If the gain is large there
too, the difference is not per-call overhead and the attribution is wrong — the checker reports
`mechanism_unsupported` rather than a pass.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here. The −40% belongs to an external rewrite of a different kernel and
establishes nothing about this one — it is carried only because upstream carried it honestly. No
board, no shape, no dtype coverage is established. The card is fenced to `__NPU_ARCH__ == 3510`,
so it says nothing about any other architecture and nothing about the 910 book. It does not
establish the numerical equivalence of the fused and unfused forms; that is a precision question
the procedure above measures but this entry does not answer. The API spelling is unresolved here
by design and handled in 0246.

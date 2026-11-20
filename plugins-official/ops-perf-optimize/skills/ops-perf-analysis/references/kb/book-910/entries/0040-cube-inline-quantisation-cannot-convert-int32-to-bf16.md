```
ID:        0040-cube-inline-quantisation-cannot-convert-int32-to-bf16
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and no architecture is stated
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:417 — "| Cube 随路量化 | 不支持 int32→bf16 | AIV 做两步转换或 AIC 做 float→bf16 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a FixPipe inline int32→bf16 conversion compiles and produces correct values on a named DAV_2201 board.
```

# 0040 · Cube inline quantisation cannot convert int32 to bf16

## 1 · Claim
Upstream asserts that the Cube unit's inline (随路) quantisation path does not support an
int32-to-bf16 conversion, and names two workarounds: a two-step conversion on the Vector core, or a
float-to-bf16 conversion on the Cube core. No architecture is stated. Not established here.

## 2 · The wrong branch this removes
The int32→bf16 conversion is exactly what a quantised Matmul wants. An int8 × int8 Matmul
accumulates into int32 in L0C, and a bf16 pipeline wants bf16 out. FixPipe exists to do that
conversion on the way out of L0C, at no extra pass — so an agent designing a quantised-Matmul
epilogue reaches for it, and the whole point of the fusion is that it costs nothing.

When it is unavailable, both fallbacks cost something the design did not budget:
- **AIV two-step** moves the L0C result out to the Vector core, converts in two stages, and writes
  back. That is an extra data movement and an extra core's worth of work — the fused epilogue
  becomes an unfused one.
- **AIC float→bf16** requires the accumulator to already be float, which means the Matmul was not
  the int8 path the agent was building.

So the two "workarounds" are not drop-in: one changes the dataflow and the other changes the
Matmul's dtype. Discovering this after the tiling is fixed means redoing the tiling, because the
Vector-side conversion needs UB the original budget did not reserve.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §7 硬件约束速查表, line 417,
verbatim:
```
| Cube 随路量化 | 不支持 int32→bf16 | AIV 做两步转换或 AIC 做 float→bf16 |
```
This is the only statement of the constraint in the sources surveyed for this book — one line, one
file, one repo, and no supporting detail anywhere.

Context for the unit, same file line 29: "| **FixPipe** | 随路处理单元 | L0C → {GM, L1}, L1 → FP
Buffer | 量化/激活/格式转换 |", and §2.2's dataflow at line 84-85 showing FixPipe as the L0C exit
path. The FP Buffer's alignment (128 B) is in 0028; the FB quantisation-scale storage described at
`ops/npu-arch/references/npu-hardware-params.md:118` is plausibly the same structure, and whether
it is is not established.

**What is not stated, and matters**: which conversions the inline path DOES support. The entry
names one gap in a capability whose extent is undocumented, so an agent cannot use it to plan — it
can only use it to avoid one specific assumption. That asymmetry is why this is labelled `trap`
rather than `knowledge`: the value is in not walking into the hole, not in knowing the ground.

No architecture is stated, in a document with per-chip columns elsewhere. Given bf16 is a
DAV_2201-era dtype and this is a constraint rather than a capability, the mechanism is 910-plausible
under this book's routing rule, and the arch gap is recorded in §7.

## 4 · Procedure
Proposed, runnable later; not run.

1. Compile arm, no device: attempt a FixPipe configuration requesting int32→bf16 targeting
   `__NPU_ARCH__` 2201, and record whether it compiles. As in 0036, a rejection is only evidence
   alongside a positive control.
2. Positive control, same arm: the same FixPipe configuration requesting int32→fp16 (or whichever
   conversion the installed SDK documents as supported). If THAT also fails to compile, the harness
   is wrong and the int32→bf16 result means nothing. This control is mandatory and is the reason
   this procedure can conclude anything.
3. Enumeration arm, read-only, and the most valuable of the three: `grep -Rn "FixPipe\|QuantMode\|
   fixpipe" "$ASCEND_HOME_PATH"/*/include` for the supported source/destination dtype enumerations.
   This fills the gap §3 names — what the path DOES support — which upstream leaves blank and which
   an agent needs in order to plan rather than merely to avoid.
4. Device arm, on a named die (occupancy before and after, no substitution), only if step 1
   compiles: run it and compare bitwise against a host reference. A silent wrong conversion is the
   worst case and must be looked for.

## 5 · Checker — acceptance declared before the run
`int32_bf16_compiles`: the claim is upheld iff false AND `int32_fp16_compiles` is true.
The conjunction is the verdict; the first term alone is worth nothing, for the same reason as in
0036 §5. Where the control cannot be established, the result is INCONCLUSIVE and recorded as such.
`supported_pairs`: the enumeration from arm 3, reported in full regardless of the other verdicts.
This is the deliverable a consuming agent actually needs, and it is reported even when the headline
verdict is inconclusive — a procedure that returns nothing when its main arm fails wastes the run.
If step 1 compiles, `bitwise_correct` becomes the verdict and a correct result overturns the entry
while an incorrect one converts it from a capability gap into a silent-corruption trap — a strictly
worse finding that must not be reported as a pass.
Exit code is the observation in arms 1 and 2 only.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; **no architecture stated by the source**, and this is a
single-line claim with no corroboration and no detail anywhere in scope — the thinnest ground of
any entry in this block. It does not establish what the inline path does support (§4 arm 3 exists
to find out). It does not establish the cost of either workaround. It does not establish whether
the restriction is the destination dtype, the source dtype, or the pair. It says nothing about
int32→fp16, int32→fp32, or fp32→bf16, and the mention of "AIC 做 float→bf16" implies at least the
last of those is available without establishing it.

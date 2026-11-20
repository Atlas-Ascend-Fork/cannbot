```
ID:        0065-dav-2201-vector-units-do-not-support-bfloat16
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:123 — "Vector 算力单独列出，总芯片算力 = Cube + Vector（但需注意 Vector 不支持 bfloat16，故 BF16 总算力即 Cube 算力）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a bfloat16 Vector operation compiles and produces correct results at full rate on a named DAV_2201 board.
```

# 0065 · DAV_2201 Vector units do not support bfloat16

## 1 · Claim
Upstream asserts that the Vector unit does not support bfloat16, and draws the consequence in the
same sentence: total chip BF16 throughput equals the Cube figure alone, because the Vector
contribution is zero. Upstream states this while listing Cube BF16/FP16 throughput for Ascend910B2
at 353 TFLOPS and Vector FP16 at 22 TFLOPS. Not established here.

## 2 · The wrong branch this removes
BF16 is the default training dtype in most current pipelines, and an agent porting such a pipeline
assumes the Vector unit handles it as it handles FP16 — they are the same width, and the Cube unit
does support BF16 on this family (upstream's own "Cube 算力 BF16/FP16" column pairs them). The
assumption is specific, plausible and, per upstream, wrong.

The consequences are structural rather than numeric:
- **Every Vector stage in a BF16 pipeline needs a cast.** A fused epilogue after a BF16 Matmul —
  bias, activation, normalisation — cannot operate on the accumulator's natural dtype. The cast
  costs UB, instructions, and a precision step, none of which appear in a throughput model that
  simply assumed BF16 worked.
- **A throughput estimate that adds Cube and Vector is wrong for BF16 by construction**, which is
  exactly what upstream's sentence says. An agent budgeting 353 + 22 = 375 TFLOPS for a BF16
  workload has over-budgeted by the Vector term.
- It compounds 0040 (Cube inline quantisation cannot go int32→bf16) and 0035 (Select cannot write
  int32): three separate dtype restrictions on this family, each stated in one line in a different
  document, and together they constrain the epilogue of a quantised BF16 operator quite tightly.

The reason this is a `trap` and not `knowledge`: nothing in the source says what *happens* on a
BF16 Vector operation. Compile error, silent cast, wrong result and half-rate execution are all
consistent with "不支持", and they call for completely different handling. §4 is built to find out
which, because that is the fact an agent actually needs.

## 3 · Ground / Source
`ops/npu-arch/references/npu-arch-guide.md:123`, verbatim in full:

"> **Cube 算力与 Vector 算力**：上表中 Cube 算力为纯 Cube 单元算力，不含 Vector Core 贡献。Vector
算力单独列出，总芯片算力 = Cube + Vector（但需注意 **Vector 不支持 bfloat16**，故 BF16 总算力即
Cube 算力）。"

Context — the table it qualifies, lines 82-91, whose 910B2 column gives "Cube 算力 BF16/FP16 | 353T"
and "Vector 算力 FP16 | 22T". Note the column labels are themselves the evidence: the Cube row names
BF16 **and** FP16, the Vector row names FP16 **only**. The prose makes explicit what the table
already encodes.

This is a single sentence, in a parenthesis, in a note under a throughput table — thin ground for a
capability claim, and comparable to 0040's single line. It is stated by the repo's declared
architecture truth source (`:74`), which is the strongest provenance available in this repo for a
capability statement, and it is still one sentence.

**No corroboration and no elaboration exists in scope.** Searched and not found: any Vector API
dtype table listing or excluding bf16 for DAV_2201; any statement of what a bf16 Vector operation
does; any DAV_3510 comparison establishing whether the later architecture lifted the restriction.
`ops/npu-arch/SKILL.md:61` lists DAV_3510's new data formats as "新增 FP8 / MXFP8 / MXFP4 / HiF8
Cube MMAD" — Cube formats, silent on Vector bf16 either way.

Adjacent and consistent, from a different skill and the same repo (one origin):
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:303` — "| ReduceSum | 仅支持
half / float（无整型） | 必须 mask → half → ReduceSum |" (entry 0045). That A2-verified table lists
`half` and `float` for a Vector reduction and does not list bfloat16. It is a statement about one
API rather than the unit, so it corroborates weakly at best — but it is the only other place in
scope where a Vector dtype list for this family appears, and bf16 is absent from it too.

## 4 · Procedure
Proposed, runnable later; not run. The claim is a capability absence; the useful output is *which
kind* of absence.

1. Compile arm, no device: build `Add`, `Mul` and `ReduceSum` over `bfloat16_t` tensors targeting
   `__NPU_ARCH__` 2201. Record per API whether it compiles.
2. Positive control, mandatory: the same three over `half`, same target. If those fail, the harness
   is wrong and the bf16 results carry no information — the same conjunction 0036 §5, 0040 §5 and
   0045 §5 require.
3. Device arm, on a named die (occupancy before and after, no substitution), for whatever compiles:
   compare against a host bf16 reference **bitwise**, not within a tolerance. A silent internal cast
   to fp16 would produce results close enough to pass a tolerance check and wrong in the low bits —
   that is the outcome most likely to be missed and most damaging, so the comparison is exact.
4. Rate arm, for whatever compiles and is correct: time the bf16 version against the fp16 version at
   identical shapes. A correct bf16 path at half rate is a different finding from an absent one, and
   is what "不支持" might mean in practice.
5. Emulation probe: disassemble or inspect the device `.text` for cast instructions around the bf16
   op. If the toolchain silently brackets the operation with converts, that is the mechanism and it
   explains a correct-but-slow result.

## 5 · Checker — acceptance declared before the run
`bf16_compiles(api)` per API: the claim is upheld in its strongest form iff false for all three
AND `half_compiles` is true for all three.
`bf16_bitwise_correct`: evaluated only where compilation succeeds. **Three outcomes, kept separate
and never collapsed**: compiles-and-exact / compiles-and-inexact / does-not-compile. The middle one
is the dangerous case — a silent precision loss — and a boolean checker would hide it inside either
neighbour.
`bf16_rate_ratio` from arm 4: reported with no declared threshold. A ratio near 1 with exact results
overturns §1 outright; a ratio near 0.5 with exact results converts the claim from "not supported"
to "supported at reduced rate", which is a correction to §1, not a pass.
The exact-comparison requirement in §4 step 3 is what lets this checker go red on the middle case:
any tolerance wide enough to be robust against normal bf16 rounding would also swallow an
fp16 round-trip.
Exit code is the observation in arms 1 and 2 only.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; the source states an architecture context, not a board. This
entry does not establish what a bf16 Vector operation does — compile failure, silent cast, wrong
result and half-rate are all consistent with the source, and §4 exists precisely because the source
does not say. It does not establish whether the restriction covers all Vector operations or only
arithmetic; upstream says "Vector" without qualification, which is weaker than it sounds. It does
not establish the DAV_3510 position, so nothing here says the restriction was lifted or retained.
The ground is a single parenthetical sentence with no corroboration in scope (§3), which makes this
one of the thinnest-sourced entries in this book despite coming from the truth source.

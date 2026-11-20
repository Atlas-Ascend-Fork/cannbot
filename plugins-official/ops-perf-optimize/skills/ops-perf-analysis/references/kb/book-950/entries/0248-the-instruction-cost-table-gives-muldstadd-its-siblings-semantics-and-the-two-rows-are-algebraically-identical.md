```
ID:        0248-the-instruction-cost-table-gives-muldstadd-its-siblings-semantics-and-the-two-rows-are-algebraically-identical
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared conditional: measured MulDstAdd(3,5,7)
           = 22.0, so json_semantics_correct = FALSE and the JSON row is the wrong one. §6 has the
           readouts; 0247 carries the full evaluation.
BOARD:     950PR (measured 2026-08-25)
SOURCE:    ops/ascendc-performance-evaluation/references/vector_instruction_types.json,
           instructions.MulAddDst — "semantic_expr": "dst = src0 * src1 + dst",
           "semantic_description": "multiply then add destination",
           "supported_dtypes_source": "asc-devkit/docs/api/SIMD-API/基础API/Reg矢量计算/复合计算/MulAddDst-39.md"
SOURCE:    same file, instructions.MulDstAdd — "semantic_expr": "dst = dst + src0 * src1",
           "semantic_description": "multiply then add into destination",
           "supported_dtypes_source": ".../复合计算/MulDstAdd.md"
INDEX:     json_semantics_correct=FALSE — MulDstAdd(3,5,7)=22 measured (JSON says 38-equivalent);
           MulAddDst row measured-right. Run 2026-08-25, Ascend950PR, via 0247.
OVERTURN:  the crafted evaluation in 0247 §4 returning 38.0 for `MulDstAdd(3,5,7)` — the JSON row
           is then correct, this entry is void, and 0247 is the entry that falls.
```

# 0248 · The instruction cost table gives `MulDstAdd` its sibling's semantics, and the two rows are algebraically identical

## 1 · Claim
Upstream asserts, in `vector_instruction_types.json`, that `MulAddDst` computes
`dst = src0 * src1 + dst` and that `MulDstAdd` computes `dst = dst + src0 * src1`. Those two
expressions denote the same function. Upstream therefore assigns the two distinct APIs of 0246 the
same semantics, distinguishing them only by an English gloss ("multiply then add destination" versus
"multiply then add into destination"). A second upstream file (`vec-03-fused-instr.md:51`) and
comments in the installed vendor headers both give `MulDstAdd` a different expression,
`dst = dst*src0 + src1`. Not established here: no arithmetic was performed and the disagreement is
recorded, not adjudicated.

## 2 · The wrong branch this removes
The JSON is not documentation a human skims — it is the data file a generated evaluator loads. An
agent building a performance model from it takes the `semantic_expr` field as the operator's meaning
and may legitimately use it to fold or substitute instructions: two rows with the same expression and
the same execution model (`alu_2slot_t2` for both) look like an obvious simplification. Rewriting
`MulDstAdd` to `MulAddDst` is then a *modelling* decision that becomes a *code generation* decision,
and it silently changes the arithmetic (0247).

There is a second, quieter branch. Because the two expressions are equal, no consistency check over
this file can fire — a validator comparing rows would find them consistent, and a validator comparing
the row against `operand_pattern` ("dst, src0, src1", identical for both) would also find them
consistent. The defect is invisible to every check the file supports. The only thing that catches it
is knowing that two rows in a table of distinct instructions must not denote the same function.

The gloss carries the whole distinction and cannot: "add destination" and "add into destination" are
not a specification. If the intent was that one adds *to* `dst` and the other multiplies *by* `dst`,
the expressions would differ and they do not.

## 3 · Ground / Source
`ascendc-performance-evaluation/references/vector_instruction_types.json` — the two rows, verbatim
and complete except for their dtype lists:

```json
"MulAddDst": {
  "regbase_api_names": ["MulAddDst"],
  "supported_dtypes": ["uint16", ..., "int64", "int64_t"],
  "source": "user-provided performance model: two-cycle dual issue, each instruction processes 256B",
  "supported_dtypes_source": "asc-devkit/docs/api/SIMD-API/基础API/Reg矢量计算/复合计算/MulAddDst-39.md",
  "default_execution_model": "alu_2slot_t2",
  "operation_kind": "fused_update",
  "operand_pattern": "dst, src0, src1",
  "semantic_expr": "dst = src0 * src1 + dst",
  "semantic_description": "multiply then add destination"
},
"MulDstAdd": {
  "regbase_api_names": ["MulDstAdd"],
  "supported_dtypes": ["fp16", "float16", "half", "bf16", "bfloat16", "bfloat16_t", "fp32", "float32", "float"],
  "source": "user-provided performance model: two-cycle dual issue, each instruction processes 256B",
  "supported_dtypes_source": "asc-devkit/docs/api/SIMD-API/基础API/Reg矢量计算/复合计算/MulDstAdd.md",
  "default_execution_model": "alu_2slot_t2",
  "operation_kind": "fused_update",
  "operand_pattern": "dst, src0, src1",
  "semantic_expr": "dst = dst + src0 * src1",
  "semantic_description": "multiply then add into destination"
}
```

Everything about these rows is right except the one field under discussion. The **dtype partition is
exactly correct** — nine families for `MulAddDst` including the 64-bit integers, three float types for
`MulDstAdd` — and matches the `static_assert`s in the installed headers quoted in 0246 §3, field for
field. That is why this entry is filed as a defect in one field rather than as a reason to distrust
the file: whoever wrote these rows had access to real per-API information and reproduced it
faithfully everywhere except the semantics.

The disagreeing sources:

- `ascendc-perf-optimize/.../vec-03-fused-instr.md:51` — "`MulDstAdd(dst, src1, src2, mask)` 语义 =
  `dst = dst*src1 + src2`（dst 既是源又是目标）". Same repo as the JSON, therefore the *same origin*
  (RULES.md Art. 3) — this is an intra-repo contradiction, which is precisely the class Art. 7 says must
  be recorded and resolved by procedure rather than by picking the more plausible author.
- installed toolkit, `dav_c310/kernel_reg_compute_vec_unary_impl.h:395` —
  `vmadd(tmpReg, errReg, resReg, mask, modeValue);  // x2 = x2*err + x1`, a comment consistent with
  `dst = dst*src0 + src1`. Quoted and qualified in 0247 §3; it is a comment, not a declaration.

A third row in the same file compounds the problem. `Mula` carries
`"regbase_api_names": ["Mula", "FusedMulDstAdd"]` with `"semantic_expr": "dst = dst + src0 * src1"`
and the note "No standalone public RegBase Mula API page found in asc-devkit; kept as compatibility
alias". But the installed header
`arm64-linux/asc/impl/basic_api/reg_compute/kernel_reg_compute_vec_fused_intf_impl.h:64-73` shows
`FusedMulDstAdd` and `MulDstAdd` forwarding to the *same* `FusedMulDstAddImpl` with identical
template arguments — so `FusedMulDstAdd` is an exact alias of `MulDstAdd`, and the JSON has grouped
it with `Mula` instead, under a third copy of the same expression. Three rows, one expression, and
the alias is attached to the wrong sibling.

The honest reading of the file's own provenance field is worth keeping: `"source": "user-provided
performance model"` for both rows. The cost model was supplied by a person, and the semantics field
was evidently filled alongside it rather than derived from the header. That is not a scandal — it is
a normal way for a data file to be built — but it means the field carries the pedigree of a note, not
of a specification, and the file does not say so.

Filed as `C-950arch-003` in `harvest/contradictions-950-arch.md`.

## 4 · Procedure
Runnable later on `950PR`. The disagreement is arithmetic and is decided by 0247 §4 — the crafted
evaluation with `dst = 3.0`, `src0 = 5.0`, `src1 = 7.0`, where `dst + src0*src1` = 38.0 and
`dst*src0 + src1` = 22.0. That procedure is not duplicated here; running it twice would be two
contacts with one instrument, not two origins.

What this entry adds are two arms that 0247 does not need and that address the *file* rather than
the instruction.

Arm A — the alias arm, compile only, no device. Instantiate `Reg::FusedMulDstAdd` and
`Reg::MulDstAdd` on `float` in one translation unit and confirm both resolve; then instantiate
`Reg::Mula` and record whether it resolves at all. A `grep` over the installed
`include/ascendc/basic_api/interface/reg_compute/` headers for `Mula` returned nothing, so the
expected result is that `Mula` does not exist on this toolkit and the JSON's third row names no
callable API. That is a finding about the file, not about the hardware, and it needs no board.

Arm B — the consequence arm, which is what makes this actionable rather than pedantic. Run the
skill's own evaluator (`scripts/evaluate_a5_vector_roofline.py`) over a case whose flow contains a
`MulDstAdd` step, then over the same case with the step rewritten to `MulAddDst`, and record whether
the predicted latency differs. Both rows carry `alu_2slot_t2`, so the prediction should be identical
— confirming that the semantics field is *not* consumed by the cost model, which bounds the blast
radius to code generation and design review. If the prediction does differ, the field is load-bearing
in the evaluator and the defect is more serious than §2 argues.

Device selection for the 0247 arm is as stated there: the operator names the device index, the probe
prints it back with `compiler/version.info` and the resolved SoC string, occupancy is checked before
the run (shared machine, ≤4 dies), and no die is substituted for another. Arms A and B need no
device.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** The verdict is taken from
0247's crafted evaluation exactly as this §5 declares, including its reference-arm fixture; see
0247 §4's as-run notes for the vehicle (regbase `__VEC_SCOPE__`, direct launch, GM-fed constant
regions, poison-guarded stores).

## 5 · Checker — acceptance declared before the run
Verdict variable `json_semantics_correct`, taken from 0247's crafted evaluation and stated as a
conditional so it cannot be settled by taste: `json_semantics_correct` is true iff the measured
`MulDstAdd(3,5,7)` equals **38.0**, and false iff it equals **22.0**. Any other value means the probe
is wrong and neither entry moves.

If false — the outcome §3's evidence points toward — this entry stands and the JSON row is corrected
upstream-side; if true, this entry is overturned and kept, restratified, with the readout in §6, and
0247 falls with it. Both outcomes are named now precisely because the field under test is a *label*,
and labels are the kind of thing a reader resolves by preference after the fact.

The checker must be able to go red, and the input that does it is the reference arm from 0247 §5: a
plain `Mul` then `Add` composed as `dst = dst + a*b`, which is 38.0 by construction. The harness must
report that arm as matching the JSON's `MulDstAdd` expression and *not* matching vec-03's. If it
reports the reference matching both, the comparison is not live and every verdict is void.

Arm A's verdict `alias_grouping_correct` is separate: pass iff `FusedMulDstAdd` and `MulDstAdd` both
resolve and `Mula` does not. Arm B's verdict `semantics_field_is_inert` is separate again: pass iff
the two evaluator predictions are bit-identical. Three verdicts, never aggregated — a single boolean
would let the arithmetic result stand in for the file-structure findings, which are independent.

Process exit codes are not the verdict anywhere: in Arm A a failed instantiation of `Mula` is the
expected outcome.

## 6 · Evidence
RUN 2026-08-25 (verdict from 0247's evaluation, as §5 declares; 2026-08-25 direct-launch probes, Ascend950PR, bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; probe sources and full logs with the verification run).

`json_semantics_correct` = **FALSE**: measured `MulDstAdd(3,5,7)` = **22.0** (and 11.0 on the
second operand set), not 38.0. The declared fixture behaved as required: the plain Mul-then-Add
reference (= 38 by construction) matched the JSON's `MulDstAdd` expression and did NOT match
vec-03's — the comparison was live, and the JSON row still lost. Per §5's declared outcomes: this
entry STANDS — `vector_instruction_types.json`'s `MulDstAdd` row is measured-wrong on 950PR, its
`MulAddDst` row is measured-right (38.0), and the two APIs the file renders algebraically identical
in fact compute different values on the same operands (22 vs 38). A cost model keyed on that file
would price the wrong instruction for every `MulDstAdd` call site.

## 7 · Scope limits — what this entry does NOT establish
No arithmetic was performed. The entry does not establish that the JSON row is wrong — it establishes
that the file assigns two distinct APIs algebraically identical expressions, which cannot both be
right if 0246's distinctness holds, and that two other sources give one of them a different
expression. Which one is wrong is decided only by 0247 §4 on a named board. It does not establish
that the `semantic_expr` field is consumed by anything; Arm B exists because the blast radius is
currently unknown, and §2's argument that it reaches code generation is reasoning about how the file
is used, not an observation of use. It does not impugn the rest of the file: the dtype partitions, the
execution models, and the per-row provenance in these rows are consistent with the installed headers
wherever they can be checked, and 0266 carries the table as a whole. It says nothing about the vendor
documentation pages the rows cite (`asc-devkit/docs/...`) — those were not available on this machine
and may state either expression, which would relocate the defect rather than remove it. Nothing
transfers to the other book (RULES.md Art. 1). Finally, the `Mula` observation rests on a `grep` finding
nothing in one header directory of one toolkit; an absence found by one search is weak evidence and
Arm A exists to replace it.

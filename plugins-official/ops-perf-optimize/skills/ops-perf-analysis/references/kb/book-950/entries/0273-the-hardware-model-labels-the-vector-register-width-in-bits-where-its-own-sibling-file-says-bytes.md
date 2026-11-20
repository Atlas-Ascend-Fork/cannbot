```
ID:        0273-the-hardware-model-labels-the-vector-register-width-in-bits-where-its-own-sibling-file-says-bytes
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared `vl_unit` choice: bytes (64 fp32 /
           128 half from one full-mask store each). §6 has the readouts. Previously harvested
           (documentary conflict only).
BOARD:     950PR (measured 2026-08-25)
SOURCE:    ops/ascendc-performance-evaluation/references/hardware/ascend950pr.json,
           `common.vector_core_spec` — "vector_reg_width_bits": 256, "predicate_reg_width_bits": 32,
           "wide_reg_width_bits": 768, "vec_calc_size": 128, "regbase_ooo_dual_issue_factor": 2
SOURCE:    ops/ascendc-performance-evaluation/references/vector_instruction_types.json — top level
           "bytes_per_instruction": 256, with `units.bytes_per_instruction` = "B/instruction"
           # same skill as the row above — ONE origin (RULES.md Art. 3), which is the point: the
           # contradiction is internal to one skill's own two data files.
SOURCE:    ops/ascendc-regbase-best-practice/.../vf-programming-rules.md:9 — "向量寄存器，VL=256B。
           b16→128 元素，b32→64 元素"; ops/npu-arch/references/npu-arch-guide.md:303 — "多条 VL=256 B
           矢量寄存器"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `Ascend950PR_9589.ini` `[AICoreSpec]`:
           `vector_reg_width=256`, `predicate_reg_width=32`, `wide_reg_width=768` — NO unit given.
INDEX:     vl_unit=bytes — full-mask store extents 64 (fp32) / 128 (half), device GetVecLen()=256.
           Run 2026-08-25, Ascend950PR. JSON field re-derivable by file read:
           python3 -c "import json;print(json.load(open('references/hardware/ascend950pr.json'))['common']['vector_core_spec'])"
OVERTURN:  a full-mask `RegTensor<float>` store measured writing 8 elements on a 950 part at this
           pin — the bits label would then be right and 0219 falls with it.
```

# 0273 · The hardware model labels the vector register width in bits where its own sibling file says bytes

## 1 · Claim
Upstream asserts, in `references/hardware/ascend950pr.json`, a field named
`vector_reg_width_bits` with the value 256, alongside `predicate_reg_width_bits: 32` and
`wide_reg_width_bits: 768`. Upstream asserts, in the sibling data file of the same skill,
`bytes_per_instruction: 256` with the unit explicitly declared as `B/instruction`. Two other upstream
skills state the width as 256 **bytes** and derive 128 b16 / 64 b32 elements from it. The installed
CANN 9.0.0-beta.2 ini carries the source field as bare `vector_reg_width=256` with no unit at all. The
three underlying numbers are identical to the ini's; only the suffix differs. Not established here:
nothing was compiled and `GetVecLen()` was never called.

## 2 · The wrong branch this removes
The two readings differ by a factor of eight, and the error arrives through a *field name* rather than
through any calculation — nothing type-checks a unit.

Under the bits reading, a vector register holds 32 bytes, so `VL_FP32` is 8 elements, not 64. Every
Regbase VF loop bound is `ceil(totalElems / (VL/sizeof(T)))` and every offset is `i * (VL/sizeof(T))`
(0219, 0252). An agent that takes 256 bits computes eight-element steps and either overruns nothing and
processes one eighth of the data per pass — leaving the remainder silently dropped if the mask is
derived from the same constant — or, in the model rather than the kernel, predicts eight times too many
instructions and produces a Vector-time estimate 8× too large. In the roofline (0264) that inflates the
`vector` term until it dominates `max(mte2, vector, mte3)`, so every operator is diagnosed
Vector-bound and the memory path is never examined.

What makes this a `trap` rather than a typo is where it sits. This is not prose a reader skims; it is
the hardware model a generated evaluator loads. The suffix is the only documentation the field has, and
it is authoritative-looking: a JSON key that says `_bits` reads as a deliberate unit declaration, more
so than prose saying "256 B". An agent choosing between "a data file says bits" and "a markdown table
says bytes" has a defensible reason to trust the data file.

The strongest argument against the bits reading is not any of the external sources — it is the same
skill's own sibling file. `bytes_per_instruction: 256`, with `units.bytes_per_instruction` spelled out
as `B/instruction`, describes the same quantity from the instruction side: one vector instruction
consumes one register's worth of data. Both cannot be 256 in different units. So the skill contradicts
itself internally, and the reader does not need to arbitrate between skills to see it.

`predicate_reg_width_bits: 32` is the one place where the bits reading is *more* plausible, and it
should be flagged rather than swept along. A 32-bit predicate register is an ordinary thing; a 32-byte
one is unusual. But 0219 §3 already records that neither reading closes the arithmetic — 128 b16 lanes
need 128 mask bits and the field says 32 either way — so this field is unresolved independently of the
suffix question, and this entry does not claim it.

## 3 · Ground / Source
`references/hardware/ascend950pr.json`, `common.vector_core_spec`, verbatim and complete:

```json
"vector_core_spec": {
  "vec_calc_size": 128,
  "vector_reg_width_bits": 256,
  "predicate_reg_width_bits": 32,
  "wide_reg_width_bits": 768,
  "regbase_ooo_dual_issue_factor": 2
}
```

Note `vec_calc_size: 128` in the same object, carried through **without** a unit suffix — which is the
field's ini name exactly. So the file renames three fields by appending `_bits` and leaves the fourth
alone. That is a per-field editorial decision, not a systematic convention, which is what makes it look
deliberate.

The installed toolkit, `Ascend950PR_9589.ini` `[AICoreSpec]` — the source these were transcribed from:

```
vector_reg_width=256
predicate_reg_width=32
wide_reg_width=768
```

Bare integers. The ini declares no unit for any of them, so the `_bits` suffix is not transcription —
it is an interpretation added at transcription time, and it is the only place in this material where
that interpretation appears.

The sibling file that contradicts it, `references/vector_instruction_types.json`:

```json
"bytes_per_instruction": 256,
"units": {
  "bytes_per_instruction": "B/instruction",
  ...
}
```

One skill, two data files, two units for one number. Both are loaded by the same evaluator
(`SKILL.md:53-58` passes `--hardware-json` and `--instruction-json` to
`evaluate_a5_vector_roofline.py`), so the contradiction is not merely documentary — the two files meet
inside one program.

The external sources, both giving bytes:
`ascendc-regbase-best-practice/.../vf-programming-rules.md:9` — "| `AscendC::Reg::RegTensor<T>` |
向量寄存器，VL=256B。b16→128 元素，b32→64 元素 |", which is decisive on its own because the derived
element counts only work in bytes; and `npu-arch/references/npu-arch-guide.md:303` — "多条 VL=256 B
矢量寄存器". The same regbase file's `:43` adds "内部自动递减 VL_T（float:64，half:128）" (0255), and its
`:98` hardcodes `constexpr uint32_t kRepF32 = 256 / sizeof(float);  // = 64` — arithmetic that is only
correct in bytes.

So: three upstream files plus a derived element count plus the ini's unitless field say bytes; one
field suffix says bits. Filed as `C-950arch-008` in `harvest/contradictions-950-arch.md`.

This entry does not assert which is right — Art. 7 forbids resolving a contradiction by author
plausibility, and the weight of evidence being lopsided is not the same as a run. What it asserts is
that the suffix is unsupported by its own source and contradicted inside its own skill.

## 4 · Procedure
Runnable later on `950PR`. This is 0219's procedure with the unit question made the verdict; it is not
duplicated in full there, and the two entries share one run deliberately — running it twice would be
two contacts with one instrument, not two origins.

Arm A — the API value, in a VF. Evaluate `AscendC::Reg::GetVecLen()` and store it as a raw integer,
printed beside `sizeof(float)` so a reader sees 256/4 = 64 rather than being handed 64. Under the bytes
reading the value is 256; under the bits reading a `GetVecLen()` that returns bytes would return 32.

Arm B — the element count, which settles the unit and cannot be produced by a constant. Fill a
`RegTensor<float>` under a full mask, `StoreAlign` to a UB region pre-poisoned with a sentinel, and
count how many 4-byte words changed: 64 under bytes, 8 under bits. Repeat for `half`: 128 versus 16.
Two dtypes, because a single one cannot distinguish "the width is 256 bytes" from "the lane count
happens to be 64".

Arm C — the overrun arm, which makes Arm B's count trustworthy. Poison the *entire* destination region,
not only the expected extent, and report words changed beyond the expected 64. A non-zero count means
the store wrote past VL and neither reading is right.

Arm D — the model arm, which is what this entry adds over 0219. Run
`scripts/evaluate_a5_vector_roofline.py` over one elementwise case as shipped, then again with
`vector_reg_width_bits` scratch-edited to 2048 (256 bytes expressed in bits), and record whether the
predicted latency changes. If it does not, the field is inert in the evaluator and the defect is
documentary only — which bounds the blast radius and is worth knowing. If it does, the field is
load-bearing and the suffix is a live modelling error.

Device selection is explicit for Arms A-C: the operator names the device index, the probe prints it
back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Arm D needs no device and should run
first, because it is the cheapest and it decides how much the rest matters.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** Arm B shares 0219's run, as
§4 intends: one regbase `__VEC_SCOPE__` kernel, direct launch, full-mask single-register stores
counted against poison regions sized 2× the expected extent. The fp32 and half stores ran in the
same session on the same die.

## 5 · Checker — acceptance declared before the run
Verdict variable `vl_unit`, derived from Arm B and stated as a choice between two named outcomes so
neither can be reinterpreted afterwards.

`vl_unit = bytes` iff the float store writes 64 elements **and** the half store writes 128. In that
case this entry stands: the `_bits` suffix is wrong, 0219 stands, and `C-950arch-008` resolves against
the hardware JSON.

`vl_unit = bits` iff the float store writes 8 **and** the half store writes 16. In that case this entry
is overturned and kept, restratified, with the readout in §6 — and 0219 falls with it, along with
`vf-programming-rules.md`'s derived element counts and the `kRepF32 = 256/sizeof(float)` idiom in every
canonical VF loop (0253).

Any other pair means neither reading is right and both entries are corrected in place, with the observed
counts logged.

Both dtypes are required in the same predicate. A checker asserting only the fp32 count would go green
under the bits reading if some unrelated constant happened to be 64 — the known blind species. The two
counts must also stand in a 2:1 ratio to each other, and that relation is checked explicitly rather
than inferred from two independent passes.

`overrun_words` (Arm C) — pass iff zero. Non-zero voids `vl_unit` regardless of what Arm B counted.

`field_is_load_bearing` (Arm D) — pass/fail is not meaningful; it is reported as the delta in predicted
latency under the scratch edit. A zero delta is the more reassuring outcome and is recorded as such.

The positive fixture, declared before the run: run Arm B with the mask narrowed via `UpdateMask` to a
remaining count of 8. The float count must then be 8, not 64. If the counter still reports 64, it is
measuring the buffer rather than the store, and every count it produced is void — including a
`vl_unit = bits` verdict, which would otherwise look like a finding.

Process exit code is not the verdict for any arm.

## 6 · Evidence
RUN 2026-08-25 (shared with 0219's run; 2026-08-25 direct-launch probes, Ascend950PR (npu-smi occupancy checked before/after; single one-block kernels), bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; probe sources and full logs with the verification run).

`vl_unit` = **bytes**: the full-mask float store wrote **64** elements and the half store wrote
**128** (poison-counted, zero beyond-extent words, narrowed-mask fixture wrote exactly 8). Device
echo `GetVecLen()` = 256. Under §5's declared outcomes: this entry STANDS — the hardware JSON's
`_bits` suffix is measured-wrong on 950PR (256 is bytes; in bits the same register is 2048), 0219
stands, and `C-950arch-008` resolves against `ascend950pr.json`'s field naming. The JSON's own
sibling file (`bytes_per_instruction: 256`, unit stated "B/instruction") was right.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the width is 256 bytes — that is 0219,
also unrun, and this entry deliberately claims only that the `_bits` suffix is unsupported by the ini
it was transcribed from and contradicted by the sibling file loaded into the same evaluator. It does not
establish that the bytes reading is right *because* more sources say so; Art. 7 forbids resolving a
contradiction by counting authors, and §4 is the only thing that decides it. It does not establish
whether the field affects any prediction — Arm D is open, and the blast radius is currently unknown. It
makes **no claim about `predicate_reg_width`**: 0219 §3 records that 32 does not obviously fit a
128-lane mask under either unit, so that field is unresolved independently and is quoted here only
because it carries the same suffix. It says nothing about `wide_reg_width=768`, which no upstream
document in this scope mentions in any unit. It says nothing about `regbase_ooo_dual_issue_factor: 2`,
which sits in the same object and is upstream's own unverified dual-issue assumption (0223's subject).
BOARD is `950PR` because the JSON is scoped to it and its variants; **nothing here covers 950DT**, which
upstream's hardware model has no variant for. The ini reading is pinned to toolkit `9.0.0-beta.2`, host
directory `aarch64-linux`, one machine — and note that the JSON's own `source_ini` fields cite
`Ascend/cann-9.1.0/...`, a toolkit not installed here, so the transcription could not be checked against
the file its authors actually read.

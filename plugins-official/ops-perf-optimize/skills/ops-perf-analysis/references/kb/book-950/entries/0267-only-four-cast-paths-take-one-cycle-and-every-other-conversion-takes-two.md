```
ID:        0267-only-four-cast-paths-take-one-cycle-and-every-other-conversion-takes-two
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-performance-evaluation); the row's own
           `source` field marks it "user-confirmed hardware model", i.e. a human-supplied timing.
           Nothing was compiled and no conversion was timed.
BOARD:     950PR
SOURCE:    ops/ascendc-performance-evaluation/references/vector_instruction_types.json,
           `execution_model_defaults.conversion_2slot_t1.source` — "conversion fast path: 1-cycle
           throughput; ONLY the four conversions fp32<->fp16 and fp32<->bf16; width = max(src,dst)
           dtype bytes"; `.conversion_2slot_t2.source` — "conversion default: 2-cycle throughput for
           every Cast path EXCEPT the four fp32<->fp16/bf16 fast-path conversions"
SOURCE:    same file, `instructions.Cast.source` — "user-confirmed hardware model: only the four
           16/32-bit float conversions fp32->fp16, fp32->bf16, fp16->fp32, bf16->fp32 are 1-cycle
           throughput; every other conversion path is 2-cycle"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a timed Cast on 950PR outside the four named paths achieving 1-cycle throughput, or one
           of the four achieving 2 — either breaks the partition, and a single path decides it.
```

# 0267 · Only four Cast paths take one cycle, and every other conversion takes two

## 1 · Claim
Upstream asserts that Regbase `Cast` throughput on DAV_3510 is not uniform: exactly four conversion
paths — fp32→fp16, fp32→bf16, fp16→fp32, bf16→fp32 — run at 1 cycle per instruction, and **every**
other conversion path runs at 2. Upstream asserts that both models occupy 2 issue slots (the
dual-replicated vector ALU) and that the byte width consumed is `max(src_dtype_bytes,
dst_dtype_bytes)` rather than either operand's own width. Not established here: nothing was compiled
and no conversion was timed.

## 2 · The wrong branch this removes
Cast is the instruction a Regbase kernel emits without deciding to. Low-precision inputs promoted to
fp32 for accumulation, results demoted on the way out, index arithmetic widened — a norm or a
quantisation operator can spend a third of its Vector instructions on conversions, and upstream's own
flow schema warns that a two-VF low-precision flow casts its input *twice*
(`SKILL.md:27`: "注意每个 VF 各 cast 一次，所以 2-VF 的低精度流会对输入 cast 两次").

An agent carrying one cost for `Cast` prices all of that identically. Two consequences follow and both
are invisible.

First, a dtype choice that looks free is not. Routing int32→fp32 instead of fp16→fp32 doubles the
conversion cost of that step; both are "a cast", both compile, both are correct. An agent optimising a
chain will not consider moving the conversion to a fast path because it has no model in which fast
paths exist.

Second, and worse for a *model*: the roofline's Vector term (0264) sums per-instruction times, so a
uniform Cast cost makes the predicted latency wrong by up to 2× on the conversion-heavy portion. The
error is systematic, not noisy, and it points the same way every time — which means it will be
absorbed into whatever fudge factor makes the model fit, and then carried into every other operator.

The `max(src, dst)` width rule is a third trap in its own right. An fp16→fp32 conversion consumes
4 bytes per element, not 2 — so a VL-wide instruction handles 64 elements, not 128, even though the
source is 16-bit. An agent computing conversion instruction counts from the *source* width
overestimates throughput by 2× on every widening cast, independently of the cycle question. The two
errors compound: a widening cast off the fast path is 2× the cycles at half the elements.

## 3 · Ground / Source
The two execution models, verbatim from
`references/vector_instruction_types.json`, `execution_model_defaults`:

```json
"conversion_2slot_t1": {
  "unit": "vector_alu",
  "issue_slots": 2,
  "throughput_cycles": 1,
  "dtype_byte_rule": "max(src_dtype_bytes, dst_dtype_bytes)",
  "source": "conversion fast path: 1-cycle throughput; ONLY the four conversions fp32<->fp16 and fp32<->bf16; width = max(src,dst) dtype bytes"
},
"conversion_2slot_t2": {
  "unit": "vector_alu",
  "issue_slots": 2,
  "throughput_cycles": 2,
  "dtype_byte_rule": "max(src_dtype_bytes, dst_dtype_bytes)",
  "source": "conversion default: 2-cycle throughput for every Cast path EXCEPT the four fp32<->fp16/bf16 fast-path conversions; width = max(src,dst) dtype bytes"
}
```

and the `Cast` row's own source string, which enumerates the four paths rather than describing them:

```
"source": "user-confirmed hardware model: only the four 16/32-bit float conversions fp32->fp16,
           fp32->bf16, fp16->fp32, bf16->fp32 are 1-cycle throughput; every other conversion path
           is 2-cycle"
```

`instructions.Cast.legacy_intrinsic_aliases` is `["vconv"]`, which is the mnemonic a disassembly will
show and therefore the thing §4 counts.

Three observations about the shape of this claim.

The two models are written as a **partition with an explicit complement** — "ONLY the four" and
"EXCEPT the four" — stated twice, once from each side. That is a falsifiable form: a single conversion
path timed off-partition kills it. Most cost-table rows in this file state a value; this pair states a
rule, and a rule is cheaper to break.

The provenance register is `"user-confirmed hardware model"`, not `"hardware-provided model"`. 0266
records that this file distinguishes the two, and that the FMA rows carry the weaker
`"user-provided performance model"` label. `user-confirmed` sits between them and is not defined
anywhere in the file. The honest reading is that a human asserted this and someone checked it; what
"checked" meant is not recorded, which is why §4 does not treat it as a measurement.

The four paths are exactly the fp32↔{fp16, bf16} set — the conversions a mixed-precision Vector kernel
performs constantly. So the fast path covers the common case, which is good engineering and also the
reason the partition is easy to believe without testing: an agent that only ever casts between fp32
and 16-bit floats would never observe the 2-cycle case.

The one place this interacts with a rule outside the file: `vec-02` in the perf-optimize card library
fuses casts into load and store via `DIST_UNPACK_B16` / `DIST_PACK_B32` (0257's neighbourhood), which
removes the Cast instruction entirely rather than making it faster. Whether a load-fused conversion
obeys this partition at all is not addressed by either source.

## 4 · Procedure
Runnable later on `950PR`. The claim is a partition, so the procedure must sample both sides and the
boundary — timing only the four fast paths would confirm nothing.

Arm A — the four fast paths. Build a `__simd_vf__` doing a long chain of `Reg::Cast` at fixed element
count, one build per path: fp32→fp16, fp32→bf16, fp16→fp32, bf16→fp32. Enough repeats that head and
tail are under 1 % of total, minimum `aiv_time` over 50 repetitions, one die, one session. Compute
achieved cycles per instruction = `aiv_time × vec_freq / instruction_count`, with `vec_freq` read from
the resolved ini and printed rather than assumed, and `instruction_count` derived from the element
count divided by `VL / max(src,dst)` — note the width rule is *used* here, so Arm C must validate it
or Arm A's instruction count is wrong.

Arm B — the complement, sampled across kinds so a single unrepresentative path cannot carry it:
fp16→bf16 (16-bit to 16-bit float), fp32→int32 (float to int, same width), int32→fp32 (int to float),
fp16→int8 (narrowing across widths), int8→fp16 (widening across widths), fp32→int8. Six paths. Under
the claim all six are 2-cycle. Any one at 1 cycle breaks the partition.

Arm C — the width rule, which Arm A depends on and which is separately falsifiable. For fp16→fp32,
poison a UB destination and count how many elements one full-mask `Cast` plus `StoreAlign` actually
writes. Under `max(src,dst)` = 4 bytes the answer is 64; under the source width of 2 bytes it would be
128. Repeat for fp32→fp16, where the rule also gives 4 bytes and so also 64 — the informative case,
since a naive reading of a *narrowing* cast would predict 128 outputs. Two directions, because a single
one cannot distinguish `max(src,dst)` from `dst` alone.

Arm D — the instruction-count control, which makes Arms A and B attributable. Disassemble each build
and count `vconv` mnemonics in the inner loop, confirming the count matches what the width rule
predicts. A cycles-per-instruction figure computed from an assumed instruction count is an inference
dressed as a measurement; this arm removes the assumption.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All paths in one comparison run on one named
die in one session — cycles-per-instruction figures gathered across dies attribute nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `cast_cycles[path]`, one per path, ten paths, never aggregated. A partition claim
collapsed into one boolean would let four confirming fast paths outvote a single broken complement,
and the complement is where the claim is at risk.

Pass is declared now as: `cast_cycles[p] ∈ [0.9, 1.1]` for each of the four named paths, **and**
`cast_cycles[p] ∈ [1.8, 2.2]` for each of the six complement paths. Both halves in the same
predicate. The partition fails if either half fails, and the failing path is named rather than
absorbed into an average.

`cast_width_elements[path]` (Arm C) — pass iff fp16→fp32 and fp32→fp16 both write 64 elements under a
full mask. A count of 128 for either overturns the `max(src,dst)` rule and simultaneously invalidates
every `cast_cycles` figure, since the instruction count they were computed from would be wrong by 2×.
This verdict therefore **gates** the others: `cast_cycles` is reported as `NOT ESTABLISHED` unless
Arm C passes.

`vconv_count_matches` (Arm D) — pass iff the disassembled mnemonic count equals the predicted count
for every build. A mismatch means the compiler emitted something other than one `vconv` per predicted
instruction — a fused load-store conversion, or a scalarised path — and the timing is measuring a
different program than the model describes.

The positive fixture, declared before the run: build one Arm A chain with the element count halved.
Every `cast_cycles` value must stay put while `aiv_time` halves. If `cast_cycles` moves, the
cycles-per-instruction computation is not normalising correctly and every figure it produced is void.
A second, sharper fixture: run Arm B's fp16→bf16 path against Arm A's fp32→fp16 path and require the
harness to report them as *different* — if it reports every path at the same cost, the timing is
dominated by something outside the Cast chain (loop overhead, memory) and the whole partition test is
inert. Without these, the checker only reads "ten numbers came out near 1 or 2", which is the known
blind species: a ±10 % band cannot tell a real partition from a loop-bound kernel.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
conversion was timed, and no disassembly was inspected. §3 is a read of one upstream JSON file; the
row's own provenance register says "user-confirmed hardware model", and what confirmation took place
is not recorded there, so it is not treated here as a readout.

## 7 · Scope limits — what this entry does NOT establish
Nothing was timed. The entry does not establish the 1-cycle / 2-cycle partition, the `max(src,dst)`
width rule, or the issue-slot count — Arms A-D are all open, and Arm C gates the rest. There is **no
second origin**: the two execution models and the `Cast` row are one upstream file, and nothing in the
installed toolkit states a conversion throughput (the headers carry dtype `static_assert`s, not
cycles). BOARD is `950PR` because upstream scopes the file to A5 / DAV_3510 and calibrates on 950PR
parts; **nothing here covers 950DT**. It does not establish which conversions are *available* — that is
the header question, and a path being 2-cycle in this table does not mean the toolkit exposes it. It
says nothing about the fp8 and HiF8 conversion paths that DAV_3510 adds (0220 lists the formats), which
have no `Cast` treatment in either source and are therefore uncovered rather than 2-cycle. It says
nothing about precision: a fast path and an accurate path are different properties, and the four
1-cycle conversions include two narrowing ones whose rounding behaviour is not addressed here. It says
nothing about load-fused or store-fused conversions (`DIST_UNPACK_B16` / `DIST_PACK_B32`), which remove
the instruction rather than accelerate it and are outside both sources. Finally, `throughput_cycles` is
a throughput figure and not a latency: a dependent chain of casts may cost more per instruction than
this model predicts, which is exactly the low-ILP case upstream's own `target_efficiency` /
`dependency="dependent"` knobs exist for (0264 §3) and which §4 deliberately avoids by using
independent chains.

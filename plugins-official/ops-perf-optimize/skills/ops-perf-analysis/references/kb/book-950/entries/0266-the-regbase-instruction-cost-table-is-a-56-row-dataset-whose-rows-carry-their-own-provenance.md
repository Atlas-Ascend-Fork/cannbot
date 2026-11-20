```
ID:        0266-the-regbase-instruction-cost-table-is-a-56-row-dataset-whose-rows-carry-their-own-provenance
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (ops/ascendc-performance-evaluation). Where rows can be
           cross-checked against the installed toolkit's `static_assert`s, the dtype sets agree
           (0246); that spot-check is not corroboration of the cost model, which nothing outside
           this skill states.
BOARD:     950PR
           # upstream scopes the file to "A5 DAV_3510 pure-vector theoretical performance
           # evaluation" and calibrates against 950PR parts; 950DT is not covered.
SOURCE:    ops/ascendc-performance-evaluation/references/vector_instruction_types.json — top level:
           `"schema_version": 2`, `"name": "ascend950_vector_instruction_types"`,
           `"scope": "A5 DAV_3510 pure-vector theoretical performance evaluation"`,
           `"bytes_per_instruction": 256`; `units.issue_slots` = "issue resources per cycle: 2 for
           VALU-only (dual-issue) instructions, 1 for instructions needing the single
           non-replicated VECTOR engine"; `units.issue_per_cycle` = "instructions/cycle =
           issue_slots / throughput_cycles"; 56 rows under `instructions`.
SOURCE:    ops/ascendc-performance-evaluation/SKILL.md:42,48 — "RegBase 指令执行单元与吞吐模型：
           `references/vector_instruction_types.json`" … "单指令吞吐 + 超越函数 overlap 由 skill 内仪器
           `tests/calibration/instruments/regbase-microbench/` 标定（源码 + 入库板上原始数据作溯源）"
INDEX:     none — nothing measured; see SOURCE. The table's shape is re-derivable by file read:
           python3 -c "import json;d=json.load(open('references/vector_instruction_types.json'));print(len(d['instructions']),list(d['execution_model_defaults']))"
OVERTURN:  a measured single-instruction throughput on 950PR that disagrees with its row's
           `issue_slots / throughput_cycles` by more than the calibration instrument's own stated
           variance — for any one of the 56 rows.
```

# 0266 · The Regbase instruction cost table is a 56-row dataset whose rows carry their own provenance

## 1 · Claim
Upstream asserts a per-instruction cost model for Regbase Vector micro-instructions on Ascend950 /
DAV_3510, as a machine-readable dataset rather than prose: 56 instruction rows, each naming its
`regbase_api_names`, its `supported_dtypes` with a `supported_dtypes_source`, its
`default_execution_model` and any per-dtype overrides, and a `source` string recording where the
timing came from. Cost is expressed as `issue_per_cycle = issue_slots / throughput_cycles`, with
`issue_slots` = 2 for instructions that occupy the dual-replicated vector ALU and 1 for those needing
the single non-replicated VECTOR engine, and every instruction processing 256 bytes. Upstream asserts
the single-instruction throughputs and the transcendental-overlap model were calibrated by an
in-skill on-board microbenchmark whose source and raw data are committed. Not established here:
nothing was run and no instruction was timed.

**This entry deliberately does not decompose the table into one entry per instruction.** It is a
dataset with per-row provenance; splitting it would multiply 56 rows by seven sections and would
detach each row from the execution-model vocabulary that gives it meaning. The claim harvested here
is the table's *structure, scope and provenance model*; the data stays where it is, cited by path.

## 2 · The wrong branch this removes
Without this entry an agent needing a Vector cost model builds one from first principles: count
instructions, multiply by a cycle estimate, divide by frequency. That produces a number and it is
wrong in a specific, structural way — it has no notion of issue slots, so it cannot represent the two
facts the table exists to encode.

First fact: instructions differ in *how many issue resources* they consume, not only in latency. A
`reduce_1slot_t1` reduction and an `alu_2slot_t1` add both have `throughput_cycles = 1`, and the
reduction is half the throughput because it needs the single non-replicated VECTOR engine. A model
that tracks only cycles rates them equal, and an agent optimising on it will replace a reduction chain
with something "the same cost" that is twice as fast, or decline a rewrite that would have been free.

Second fact: `throughput_cycles` varies per *dtype within one instruction*, not just per instruction.
`Cast` is 1 cycle for exactly four conversion paths and 2 for every other (0267); `Exp` is 4 cycles at
fp32 and different at fp16. An agent with one number per API name cannot express that and will price a
cast chain wrong by 2× depending on which dtypes it happens to use.

The third wrong branch is about the dataset rather than the model: an agent that reads the table's
`semantic_expr` fields as authoritative API semantics. They are not uniformly reliable — 0248 records
two rows whose expressions are algebraically identical for two distinct APIs. The dtype sets and the
execution models in this file check out against the installed headers; the semantics field does not.
Knowing which fields of a data file to trust is part of using it.

## 3 · Ground / Source
The header of `references/vector_instruction_types.json`, which is where the vocabulary is defined:

```json
"schema_version": 2,
"name": "ascend950_vector_instruction_types",
"scope": "A5 DAV_3510 pure-vector theoretical performance evaluation",
"bytes_per_instruction": 256,
"units": {
  "bytes_per_instruction": "B/instruction",
  "issue_slots": "issue resources per cycle: 2 for VALU-only (dual-issue) instructions, 1 for instructions needing the single non-replicated VECTOR engine",
  "throughput_cycles": "cycles/instruction per issue resource group",
  "issue_per_cycle": "instructions/cycle = issue_slots / throughput_cycles",
  "parallel_elements_per_cycle": "elements/cycle/core"
}
```

`bytes_per_instruction: 256` with the unit spelled out as `B/instruction` is the second origin for the
byte reading of the vector register width (0219, 0273) and it is inside this same file — which is why
0273 records the sibling hardware JSON's `vector_reg_width_bits` label as an internal contradiction.

The ten execution models, from `execution_model_defaults`:

| model | unit | issue_slots | throughput_cycles | dtype width rule |
|---|---|---|---|---|
| `alu_2slot_t1` | vector_alu | 2 | 1 | `dtype_bytes` |
| `alu_2slot_t2` | vector_alu | 2 | 2 | `dtype_bytes` |
| `conversion_2slot_t1` | vector_alu | 2 | 1 | `max(src,dst)` — ONLY fp32↔fp16 and fp32↔bf16 |
| `conversion_2slot_t2` | vector_alu | 2 | 2 | `max(src,dst)` — every other Cast path |
| `reduce_1slot_t1` | vector | 1 | 1 | `dtype_bytes` |
| `vector_1slot_t1` | vector | 1 | 1 | `dtype_bytes` |
| `pack_unpack_1slot_t1` | vector | 1 | 1 | `dtype_bytes` |
| `valu_2slot_t4` | vector_alu | 2 | 4 | `dtype_bytes` |
| `valu_2slot_t8` | vector_alu | 2 | 8 | `dtype_bytes` |
| `model_required` | model_required | null | null | — |

`instruction_defaults.default_execution_model` is `alu_2slot_t1`, with the note "Most RegBase vector
micro-instructions default to the dual-replicated vector ALU model unless an instruction or dtype
override selects a different execution model."

Two entries in that table are worth reading as design rather than data. `reduce_1slot_t1`'s own source
string states the contention explicitly — "single-issue: reductions need the non-replicated VECTOR
engine, throughput_cycles=1; shares the vector resource with data-reorder and Pack/UnPack" — so
reductions, `Interleave`/`DeInterleave` and `Pack`/`UnPack` compete for one resource, which is a
scheduling fact no per-instruction latency table would express. And `model_required` is an explicit
*hole*: a row marked `model_required` has no cost model, and upstream's SKILL.md declares
"`references/vector_instruction_types.json` 里没有的隐式特殊数学模型" out of scope. A dataset that
names its own gaps is doing something most do not.

The 56 rows, in file order:

> Add, Sub, Mul, Max, Min, Abs, Relu, LeakyRelu, Prelu, Neg, Adds, Muls, Maxs, Mins, Not, And, Or,
> Xor, ShiftLeft, ShiftRight, ShiftLefts, ShiftRights, Axpy, Compare, Compares, Select, Cast, Mull,
> MulDstAdd, MulAddDst, Mula, AbsSub, Truncate, ReduceMax, ReduceMin, ReduceSum, BlockReduceMax,
> BlockReduceMin, BlockReduceSum, PairReduceSum, CompareScalar, Duplicate, Interleave, DeInterleave,
> Pack, UnPack, Exp, ExpSub, Ln, Log, Log2, Log10, Div, Sqrt, Rsqrt, Reciprocal

The per-row provenance model is the part worth imitating. Two `source` registers appear:

- `"source": "hardware-provided model: Axpy throughput_cycles=1 for all supported dtypes on
  dual-replicated vector ALU"` — a vendor-supplied timing.
- `"source": "user-provided performance model: two-cycle dual issue, each instruction processes 256B"`
  — a human-supplied timing (both FMA rows carry this).

and separately `supported_dtypes_source`, which cites a vendor documentation page per row, e.g.
`"asc-devkit/docs/api/SIMD-API/基础API/Reg矢量计算/复合计算/Axpy-38.md"`. So each row says *twice* where
it came from — once for its cost, once for its dtype set — and distinguishes vendor-provided from
human-provided. One row is candid about having no source at all: `Mula`'s
`supported_dtypes_source` reads "No standalone public RegBase Mula API page found in asc-devkit; kept
as compatibility alias…".

Where these rows can be checked against something outside the skill, they hold: the `MulAddDst` and
`MulDstAdd` dtype sets match the `static_assert`s in the installed CANN 9.0.0-beta.2 `dav_c310`
headers field for field (0246 §3). That is a spot-check of two rows' dtype data against an independent
origin; it says nothing about the 56 rows' *timings*, which nothing outside this skill states.

The calibration instrument, `SKILL.md:48`: "单指令吞吐 + 超越函数 overlap 由 skill 内仪器
`tests/calibration/instruments/regbase-microbench/` 标定（源码 + 入库板上原始数据作溯源）；GM 带宽由
`tests/onboard/kernels/membw` 标定。标定哲学（绝不为让某个算子通过而调常量）…" — the instrument's source
and its on-board raw data are committed to the repo as provenance, and the calibration philosophy is
0272. `tests/calibration/bench_results/insn_throughput.csv` is the committed readout.

## 4 · Procedure
Runnable later on `950PR`. Upstream ships the instrument, so the procedure is to re-run it
independently rather than to invent one — and then to attack the rows it cannot reach.

Arm A — re-derive the committed calibration. Build and run
`tests/calibration/instruments/regbase-microbench/` from source on a named 950PR die and compare the
produced per-instruction throughputs against the committed
`tests/calibration/bench_results/insn_throughput.csv` and against each row's
`issue_slots / throughput_cycles`. Report per row, never aggregated.

Arm B — the issue-slot contention, which is the structural claim and is not testable one instruction
at a time. Build two kernels of identical instruction *count*: one all `Add` (`alu_2slot_t1`), one
alternating `Add` and `ReduceSum` (`reduce_1slot_t1`). Under the model the second is slower by more
than its instruction mix alone predicts, because the reduction serialises on the single VECTOR engine.
Then build a third mixing `Add` with `Pack` — a different `1slot` instruction — and confirm the two
mixes degrade the same way. If they do not, the shared-resource claim in `reduce_1slot_t1`'s source
string is wrong even if every individual row is right.

Arm C — the per-dtype overrides. For `Cast`, time all four fast paths (fp32↔fp16, fp32↔bf16) and at
least three other conversion paths, at identical element counts, on one die in one session. Expected
ratio 2:1 (0267). For `Exp`, time fp32 and fp16 and compare against the row's per-dtype cycles.

Arm D — the transcendental overlap, which upstream models as free. `SKILL.md:64` asserts the
`vector_transcendental` sub-pipeline overlaps with 1-cycle ALU work. Build a kernel with a long `Exp`
chain, then the same chain interleaved with independent `Add`s, and record whether the adds are free.
This is the one modelling assumption in the Vector time model that is not a per-instruction number,
and it is the one an ILP-poor kernel will violate.

Arm E — the `model_required` rows and the coverage question. Enumerate which of the 56 rows carry
`model_required`, and separately enumerate the `Reg::*` API surface in the installed headers to find
instructions with **no** row at all. A cost model's silent gaps matter as much as its wrong numbers,
and this arm is a file read plus a header read — it needs no device and should run first.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All arms of one comparison run on one named
die in one session — per-instruction timings gathered across dies attribute nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `row_agrees[api, dtype]`, one per row per dtype from Arm A — never aggregated into a
table-level boolean. A 56-row dataset with one pass/fail would let 55 agreements hide the one row a
generated kernel actually leans on, and the point of a per-row dataset is per-row accountability.

Pass per row is declared now as measured `issue_per_cycle` within ±10 % of
`issue_slots / throughput_cycles`, with the band fixed before any readout. Rows whose `source` is
`"user-provided performance model"` are flagged in the report regardless of outcome: they are the rows
with the weakest pedigree and a pass there is worth less than a pass on a `"hardware-provided model"`
row.

`slot_contention_holds` (Arm B) — pass iff the `Add`+`ReduceSum` mix is slower than the pure-`Add`
kernel by the factor the 1-slot model predicts, **and** the `Add`+`Pack` mix degrades comparably. One
mix agreeing is not enough: a single mixed kernel being slow has many ordinary causes, and the claim
is specifically that a *shared resource* is the cause. Two different 1-slot instructions degrading the
same way is the evidence; one is an anecdote.

`overlap_is_free` (Arm D) — reported with run variance, no pass threshold. Upstream states the overlap
and does not quantify it; a measured cost below variance is reported as "below variance", never as
zero.

`uncovered_apis` (Arm E) — the set of `Reg::*` VF-safe APIs present in the installed headers with no
row in the table. Reported as a list. A non-empty list is not a failure; it is the model's honest
coverage boundary and belongs in the delivered skill.

The positive fixture, declared before the run: Arm A must be shown to go red on a known-wrong input.
Re-run it with one row's `throughput_cycles` doubled in a scratch copy of the JSON. That row's
`row_agrees` **must** flip to false and no other row's may move. If nothing flips, the comparison is
not reading the table; if several flip, the rows are not independent and per-row verdicts are
meaningless. Without this the checker only reports "the numbers looked close", which is the known
blind species — and a ±10 % band over 56 rows is exactly wide enough to absorb a real error silently.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The instrument was not built,
no instruction was timed, and the committed `insn_throughput.csv` was not reproduced. The table's
structure reported in §3 — 56 rows, ten execution models, the units block, the per-row provenance
fields — comes from parsing the JSON file, which is a file read; it establishes what the dataset
contains and nothing about whether its numbers are right. The dtype cross-check against the installed
`dav_c310` headers covers two rows' dtype sets, not any row's cost.

## 7 · Scope limits — what this entry does NOT establish
Nothing was timed. The entry does not establish any of the 56 rows' throughputs, the issue-slot model,
or the transcendental overlap — Arms A-D are all open. It does not establish the table's *semantics*
fields, and 0248 records two rows where those are demonstrably confused; the fields that check out
against an independent origin are the dtype sets, on two rows. BOARD is `950PR` because upstream scopes
the file to A5 / DAV_3510 pure-Vector and calibrates on 950PR parts; **nothing here covers 950DT**, and
a run on one would not establish the other. It covers pure-VectorCore Regbase micro-instructions only
— Cube, mixed Cube-Vector, and any math model absent from the file are declared out of scope by
upstream itself. It does not establish that the 56 rows cover the callable `Reg::*` surface; Arm E
exists because the gap is unmeasured, and `model_required` rows are acknowledged holes rather than
values. It says nothing about how the table composes into an operator-level prediction — that is the
roofline (0264), a separate claim with separate corrections. The calibration provenance is upstream's:
committed instrument source plus committed board data, dated, which is the strongest provenance in
this scope and is still upstream text under RULES.md Art. 3. Finally, the whole file is pinned to
`schema_version: 2` and to whatever toolkit its authors used; the sibling hardware model cites
`cann-9.1.0`, which is not installed on this machine, so nothing here was checked against the toolkit
the calibration was performed on.

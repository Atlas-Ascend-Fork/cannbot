```
ID:        0103-tiling-output-is-a-fixed-schema-whose-buffer-sizes-are-formulas-not-numbers
LABEL:     procedure
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/index.md:100-158 —
           "理想 Tiling Data 输出格式 ... buffers: - name: L1_A
            size_formula: \"kAL1 * baseM * sizeof(AType) * (pbAL1 ? 2 : 1)\""
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case on a named 950 board where a plan emitted in this schema, with every
           size_formula satisfied against the queried capacities, still overflows the buffer at
           runtime — that would show the schema omits a term the hardware charges for.
```

# 0103 · Tiling output is a fixed schema whose buffer sizes are formulas, not numbers

## 1 · Claim
Upstream asserts a single output schema for every tiling model in this reference set, in two
shapes: a Cube/fusion shape carrying `multicore`, `l1_split`, `l0_split`, `ub_split`, `buffers`,
`branches`, and a Vec shape carrying `multicore`, `ub_split`, `buffers`, `branches`. Upstream
further asserts — by construction of the schema rather than in prose — that each buffer entry
carries a `size_formula` string in the parameters rather than a computed byte count, e.g.
`"kAL1 * baseM * sizeof(AType) * (pbAL1 ? 2 : 1)"` for `L1_A`, and that `branches` enumerates the
dtype and shape-size dimensions the plan must cover. Not established here.

## 2 · The wrong branch this removes
Without the formula-not-number discipline a harness agent emits `L1_A: 65536` — a plan that is
correct for exactly one shape, one dtype, and one double-buffer decision, and silently wrong for
every other point in the branch table it also emits. The wrongness is invisible: the number is
plausible, the schema validates, and the mismatch only appears when someone changes `pbAL1` and
the budget no longer tracks. Carrying the formula makes the double-buffer factor, the dtype width,
and the L1 K-coverage explicit terms that a reader can check against capacity, and makes the
plan re-derivable rather than pasted — which is the same discipline this book applies to its own
§4 sections.

The `branches` block removes a second wrong branch: a plan presented without its coverage
dimensions reads as universal. Upstream's schema forces the emitter to say which dtypes and which
shape regimes the plan was derived for, i.e. to state its own scope.

## 3 · Ground / Source
`ops/ascendc-perf-optimize/references/tiling/index.md:102-137`, the Cube/fusion schema in full:

```yaml
tiling_data:
  multicore:
    split_dim: "M,N"
    single_core_m: 128
    single_core_n: 256
    core_num: 8
  l1_split:                    # L1 是主切分层
    base_m: 64
    base_n: 128
    base_k: 32
    need_chunk: false
    chunk_formula: ""
    double_buffer: "A1_B1"     # L1 ping-pong 策略
  l0_split:                    # L0 是 L1 的子切分
    mL0: 64
    nL0: 16
    kL0: 16
  ub_split:                    # UB 是 weight/fmap DMA 暂存
    weight_trans: false
    fmap_dma: false
  buffers:
    - name: L1_A
      size_formula: "kAL1 * baseM * sizeof(AType) * (pbAL1 ? 2 : 1)"
    - name: L1_B
      size_formula: "kBL1 * baseN * sizeof(BType) * (pbBL1 ? 2 : 1)"
    - name: L0_C
      size_formula: "mL0 * nL0 * sizeof(float32) * (pbCL0 ? 2 : 1)"
  branches:
    - dim: dtype
      conditions: ["fp16", "bf16", "fp32"]
    - dim: shape_size
      conditions: ["large", "small"]
```

and `:139-158`, the Vec schema:

```yaml
tiling_data:
  multicore:
    split_dim: "batch"
    single_core_size: 4096
    core_num: 4
  ub_split:                    # UB 是唯一切分层
    block_size: 256
    repeat: 16
  buffers:
    - name: UB_in
      size_formula: "block_size * sizeof(dtype)"
    - name: UB_out
      size_formula: "block_size * sizeof(dtype)"
  branches:
    - dim: dtype
      conditions: ["fp16", "fp32"]
```

Two observations recorded against the schema itself. First, `core_num: 8` in the Cube example and
`core_num: 4` in the Vec example are illustrative literals with no chip behind them; the same
subtree carries `coreNum` as 64, 72, 32, 8 and 24 across scripts and worked examples (C-007 in
`harvest/CONTRADICTIONS.md`, cited not duplicated here). Second, the schema's three split blocks
are peers with no marker of which is the decision level, while the prose two paragraphs earlier
says the Cube decision level is L1 (0102) — the discipline is not carried by the artifact that
gets copied.

`L0_C`'s accumulator width is fixed to `sizeof(float32)` in the formula regardless of the `dtype`
branch, which is the only place in the schema where a hardware fact is asserted rather than
parameterised.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; export `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after
and discard the case if the die moved.

Budget-faithfulness sweep. Take one matmul shape per `branches.dtype` value (fp16, bf16, fp32) and
one per `shape_size` value, six cases. For each, emit the plan in the schema above, evaluate every
`size_formula` at the plan's parameter values, and compare the sum of L1 buffers against the L1
capacity read at runtime (never a literal — see 0141 and 0104). Then walk each case up in `baseK`
until the evaluated formula sum reaches exactly the queried capacity, build, and run; then one
step further, build, and run. Record for each point: build success, host echo of the parameters
actually used, output match against the fp64 reference within the operator's tolerance, and
`aic_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations with the first 5 dropped.
The `pbAL1/pbBL1/pbCL0` flags are swept as an independent arm so the `(x ? 2 : 1)` factor is
exercised rather than assumed.

Refuses to assume: that a free die stays free; that a die may be substituted; that the capacity is
the value any script literal asserts; that a formula which fits at fp16 fits at fp32 (each dtype
is its own case); that a run on 950PR says anything about 950DT.

## 5 · Checker — acceptance declared before the run
Verdict variable `formula_is_tight`: for each case, the largest `baseK` whose evaluated formula sum
is ≤ capacity must build, run, and produce a correct result; the next step up must fail (build
error, launch error, or wrong result). Declared acceptance: `formula_is_tight` true for all six
cases. Declared falsification, in either direction: a point inside the formula budget that fails
at runtime (the schema omits a charged term — the OVERTURN condition), or a point well outside it
that runs correctly (the schema over-charges, and every plan derived from it is conservative by an
unmeasured margin). Both are reported with numbers.

The exit code is not the verdict. A build whose parameters were clamped back inside the budget
exits 0 and produces a correct result, which would read as confirmation of a boundary that was
never approached. The checker therefore requires the host echo of `baseM/baseN/baseK/pbAL1/pbBL1`
to match the request exactly and goes red on any mismatch, so "clamped" and "fitted" are not
confusable. It also fails red if fewer than the expected number of `msprof` rows appear, rather
than reading the rows that are there.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no plan was emitted, built, or run. The entry does not establish that the
schema is complete — the `buffers` list in the example omits `L0_A`/`L0_B` entirely, and whether
that is an omission or a deliberate scoping is not stated upstream. It does not establish the
capacity of L1, L0C or UB on any board, does not establish that `sizeof(float32)` is the right
accumulator width for every dtype branch, and does not validate the illustrative `core_num`
literals (see C-007). No chip is named anywhere in `index.md`, so BOARD is
`family-claimed(unverified)` and §7 records that the chip is unstated; §4 names 950PR/950DT
because that is where a future run of ours would happen, not because upstream's evidence touched
them. Nothing here is established for any 910-family board.

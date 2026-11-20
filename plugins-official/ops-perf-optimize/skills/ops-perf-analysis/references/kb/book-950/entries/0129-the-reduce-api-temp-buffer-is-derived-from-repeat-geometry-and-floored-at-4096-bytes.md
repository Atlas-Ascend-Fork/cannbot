```
ID:        0129-the-reduce-api-temp-buffer-is-derived-from-repeat-geometry-and-floored-at-4096-bytes
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/tiling-flow.md:357-367 —
           "elements_per_repeat = 256 / dtype_bytes; elements_per_block = 32 / dtype_bytes;
           repeat_count = ceil(r_align / elements_per_repeat);
           tmp_buf_size = ceil(repeat_count / elements_per_block) × elements_per_block × dtype_bytes;
           tmp_buf_size = max(tmp_buf_size, 4096)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured reduction on a named 950 board that runs correctly with a temp buffer below
           the 4096 B floor, or that fails at exactly the formula's value — either kills the
           formula as written, and with it every template budget that subtracts it.
```

# 0129 · The Reduce-API temp buffer is derived from repeat geometry and floored at 4096 bytes

## 1 · Claim
Upstream asserts a formula for the temporary buffer the hardware Reduce instruction requires,
built from two hardware granularities: `elements_per_repeat = 256 / dtype_bytes` and
`elements_per_block = 32 / dtype_bytes`. From these, `repeat_count = ceil(r_align /
elements_per_repeat)`, then `tmp_buf_size = ceil(repeat_count / elements_per_block) ×
elements_per_block × dtype_bytes`, and finally `tmp_buf_size = max(tmp_buf_size, 4096)`. Upstream
lists the 4096 B floor separately in its alignment table as `tmp_buf_size | ≥ 4096B | Reduce API
下限`. Not established here.

## 2 · The wrong branch this removes
`tmp_buf` is subtracted from `ub_size` in three of the five template budgets (0123) before the
division that sizes the tile, so an agent that omits it or guesses it gets a tile that is too large
by a bounded but real amount. Guessing is the natural failure: 4096 looks like the answer, since
the floor is stated in the alignment table where a reader is most likely to look, and the formula
is in a section titled "Reduce API 临时区" three headings away. But the formula exceeds the floor
whenever `repeat_count` is large — at FP32, `elements_per_repeat = 64` and `elements_per_block = 8`,
so `r_align = 65536` gives `repeat_count = 1024`, `ceil(1024/8) × 8 × 4 = 4096`, exactly the floor;
`r_align = 131072` gives `repeat_count = 2048` and `tmp_buf_size = 8192`, twice it. So the floor is
right up to `r_align ≈ 65536` at FP32 and wrong above it, in the large-R regime that is precisely
where AR-Recompute lives.

The second wrong branch is the two granularities themselves. 256 B per repeat and 32 B per block
are hardware quantities that appear here as bare numerators, without a board and without a source.
An agent that carries them into any other calculation — vector loop sizing, alignment padding — is
propagating an unverified constant out of a tiling formula into an architectural claim. The
deep-dive that surveyed this skill listed both among the quantities with *no* upstream authority
anywhere, to be established from scratch; this entry is where the reduction family's use of them
is recorded, not where they are established.

## 3 · Ground / Source
`reduction/fallback/tiling-flow.md:357-367`, §8 in full:

```
## 8. Reduce API 临时区

使用硬件 Reduce 指令时需预留临时 buffer：

elements_per_repeat = 256 / dtype_bytes
elements_per_block = 32 / dtype_bytes
repeat_count = ceil(r_align / elements_per_repeat)
tmp_buf_size = ceil(repeat_count / elements_per_block) × elements_per_block × dtype_bytes
tmp_buf_size = max(tmp_buf_size, 4096)
```

Restated as a floor in two alignment tables — `reduction/fallback/tiling-flow.md:378`
(`| tmp_buf_size | ≥ 4096B | Reduce API 下限 |`) and
`reduction/fallback/tiling-fields.md:116` (`| tmp_buf_size | ≥ 4096B |`) — and carried as a field
in `tiling-fields.md:42`: `| tmp_buf_size | Reduce API 临时缓冲字节数 | 所有模板 |`. The
template/field cross-table at `tiling-fields.md:105` marks `tmp_buf_size` as present only for
AR-FullLoad (`| tmp_buf_size | ➖ | ✅ | ➖ | ➖ | ➖ |`), while `:42` says `所有模板`. The two
statements are in the same file, seven lines apart in effect, and they disagree about which
templates carry the field. Registered as C-950tiling-011.

Re-derived worked values, computed here and not quoted, at FP32 (`dtype_bytes = 4`, so
`elements_per_repeat = 64`, `elements_per_block = 8`):

| `r_align` | `repeat_count` | pre-floor `tmp_buf_size` | after floor |
|---:|---:|---:|---:|
| 512 | 8 | `ceil(8/8)×8×4 = 32` | 4096 |
| 4096 | 64 | `ceil(64/8)×8×4 = 256` | 4096 |
| 65536 | 1024 | `ceil(1024/8)×8×4 = 4096` | 4096 |
| 131072 | 2048 | `ceil(2048/8)×8×4 = 8192` | 8192 |

and at FP16 (`elements_per_repeat = 128`, `elements_per_block = 16`): `r_align = 131072` gives
`repeat_count = 1024`, `ceil(1024/16)×16×2 = 2048`, floored to 4096. So the crossover sits an
octave higher at FP16 — the formula only exceeds the floor above `r_align = 262144`. The floor
therefore governs almost the entire practical range and the formula governs only very large R,
which is the opposite of what the section's prominence suggests.

The `256` and `32` numerators are the repeat granularity and block granularity respectively. They
appear elsewhere in this domain as alignment rules — `tiling-flow.md:375-377`:
`| R 方向 | 32B / dtype_bytes 个元素 | DataCopyPad 要求 |` and `| UB Buffer | 32B | 最小搬运单位 |`
— with the same 32 B, and the 64/128-element `a0_tile_unit` at `:376` is described as
`向量寄存器宽度`, i.e. 256 B at FP32 and at FP16 alike. So three independent statements in this
family are consistent with a 256 B vector register and a 32 B memory block, and all three are
literals in markdown with no board and no measurement.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Floor test — the arm that can go red. Take an AR-FullLoad case at `r_align = 512` FP32, where the
formula's pre-floor value is 32 B and the floor raises it to 4096 B, a 128× gap. Build four
variants that differ *only* in the allocated temp buffer: 32 B (the formula's own pre-floor value),
1024 B, 4096 B (the floor) and 8192 B. One compiler pin, md5 each binary, host echo of
`tmp_buf_size` and the derived `rows_per_ub`. Check every variant against an fp64 reference within
the operator's declared tolerance — the failure mode of an undersized Reduce temp is most likely a
wrong result rather than a crash, so the numeric check is the primary instrument here and the
timing is secondary. Record `aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10
iterations, first 5 dropped, per case.

Formula test. Take `r_align = 131072` FP32, where the formula gives 8192 B, above the floor, and
build at 4096 B and 8192 B. If 4096 B produces a correct result, the formula's growth term is
unnecessary at this size; if it does not, the term is doing work and the floor alone is unsafe in
the large-R regime.

Granularity test, indirect. Sweep `r_align` finely across a repeat boundary
(`r_align ∈ {60, 64, 68, 124, 128, 132}` elements at FP32) with a fixed generous temp buffer and
record `aiv_time`; a step at multiples of 64 elements is evidence for
`elements_per_repeat = 256/dtype_bytes`. This measures a consequence of the granularity, not the
granularity itself, and is labelled as such.

Refuses to assume: that a free die stays free; that a die may be substituted; that an undersized
temp fails loudly — the numeric check is what catches it; that `256` and `32` are correct (the
third arm probes one of them behaviourally and neither is established); that a result at FP32
transfers to FP16, where both granularities double in elements.

## 5 · Checker — acceptance declared before the run
Verdict variable `min_safe_tmp(r_align, dtype)`: the smallest allocated temp buffer at which the
result matches the fp64 reference within tolerance across all iterations. Declared before the run:
the floor is supported iff `min_safe_tmp` at `r_align = 512` FP32 lies in (1024, 4096]; the formula
is supported iff `min_safe_tmp` at `r_align = 131072` FP32 lies in (4096, 8192]. The OVERTURN fires
iff `min_safe_tmp` ≤ 1024 at the small case (the floor is 4× or more too conservative) or iff the
formula's own value fails at the large case (the formula under-allocates). The granularity arm's
verdict is `repeat_step_observed ∈ {64, other, none}` at FP32.

The exit code is not the verdict — a kernel producing wrong results exits 0. The primary instrument
is the numeric comparison, and the checker fails red if any variant produced no comparison at all
(missing reference, missing output) rather than treating an absent comparison as a pass. Second
guard, and the one that keeps this from being a self-confirming test: the host echo of
`tmp_buf_size` must equal the requested value at every point, because a host that silently applied
its own floor would make the 32 B variant identical to the 4096 B variant and produce
`min_safe_tmp ≤ 32`, an apparent overturn from an experiment that never undersized anything. Any
mismatch marks the point `clamped` and the checker goes red.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The worked table in §3 is
arithmetic on upstream's formula, computed here, not a readout.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish the 4096 B floor, the 256 B repeat granularity
or the 32 B block granularity — all three are literals in upstream markdown with no board, no
derivation and no measurement, and two of them are on the list of quantities this project must
establish from scratch. It does not establish that the Reduce API needs a temp buffer at all, only
that upstream reserves one. It does not resolve whether `tmp_buf_size` is present in all five
templates or only in AR-FullLoad (C-950tiling-011). It does not establish that the interleaved
templates' fixed 16 KB temp (0128) and this computed temp are the same object under two rules; they
are described in different sections and this entry does not merge them. No board is named in the
source, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT
because that is where our run would happen. Nothing here is established for any 910-family board.

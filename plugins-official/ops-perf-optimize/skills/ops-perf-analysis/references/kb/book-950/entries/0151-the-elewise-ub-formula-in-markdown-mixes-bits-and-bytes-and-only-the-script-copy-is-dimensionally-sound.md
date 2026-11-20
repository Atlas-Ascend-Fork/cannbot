```
ID:        0151-the-elewise-ub-formula-in-markdown-mixes-bits-and-bytes-and-only-the-script-copy-is-dimensionally-sound
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/elewise/fallback/tiling-flow.md:44-52 —
           "bufferDivisor = bufferNum * elemBytes ... maxElemNum = (ubSize - extraSize) * 8 /
           bufferDivisor" ; elewise/fallback/script/elewise_tiling.py:170-175 —
           "double_buffer = 2 ... buffer_divisor = double_buffer * cfg.buffer_num * cfg.elem_bytes
           ... max_elem_num = (cfg.ub_size - cfg.extra_size) // buffer_divisor" ;
           broadcast/fallback/tiling-flow.md:82 — "maxElemNum = (ubSize - extraSize) * 8 /
           (bufferNum * maxDtypeBits)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board in which the markdown formula's `ubFormer` allocates
           successfully and runs correctly — the dimensional analysis in this entry would then be
           wrong about what the formula produces, and the entry is corrected in place.
```

# 0151 · The elewise UB formula in markdown mixes bits and bytes, and only the script copy is dimensionally sound

## 1 · Claim
Upstream asserts three versions of one UB-capacity formula across two families. The elementwise flow
document asserts `bufferDivisor = bufferNum * elemBytes` (bytes per element per buffer) and
`maxElemNum = (ubSize - extraSize) * 8 / bufferDivisor`, multiplying a byte capacity by 8 and dividing
by a byte quantity. The elementwise reference script asserts
`buffer_divisor = double_buffer(2) * buffer_num * elem_bytes` with
`max_elem_num = (ub_size - extra_size) // buffer_divisor` — no factor of 8, and an explicit
double-buffer factor of 2 that neither markdown document carries. The broadcast family asserts
`maxElemNum = (ubSize - extraSize) * 8 / (bufferNum * maxDtypeBits)`, dividing a bit capacity by a bit
quantity. Not established here; the dimensional reading below is this book's arithmetic on upstream's
formulas, not a measurement.

## 2 · The wrong branch this removes
Only one of the three is dimensionally closed *and* accounts for double buffering, and it is the one an
agent is least likely to read. Taking `ubSize = 253952` (248 KiB), `extraSize = 0`, `bufferNum = 2`,
fp16 (`elemBytes = 2`, `maxDtypeBits = 16`):

- elewise markdown: `253952 × 8 / (2 × 2) = 507 904` elements. At 2 bytes per element across 2
  buffers that is 2 031 616 bytes — eight times the UB.
- elewise script: `253952 / (2 × 2 × 2) = 31 744` elements. Times 2 bytes, 2 buffers, 2 (ping-pong)
  = 253 952 bytes — exactly the UB.
- broadcast: `253952 × 8 / (2 × 16) = 63 488` elements. Times 2 bytes, 2 buffers = 253 952 bytes —
  exactly the UB, with no double buffering.

So the markdown elewise formula overshoots by 8× at fp16, and by 4× at fp32 and 16× at int8 — the
error scales with `8 / elemBytes`, which is the tell that a bits-based numerator was kept while the
denominator was switched to bytes. The two correct forms differ from each other only in whether
double buffering is charged, which is a real modelling difference and not an error.

An agent that reads the elewise flow document and computes `ubFormer` from it produces a tile eight
times too large. `ubFormer` then feeds `ubLoopFormer = CeilDiv(blockFormer, ubFormer)`, so the loop
count collapses to 1 and the kernel attempts one enormous tile — an allocation failure or a silent
overwrite, not a slow run. And the failure is dtype-dependent, so a plan validated at fp32 and
deployed at int8 fails worse.

The general shape is worth naming because it recurs across this subtree: a formula copied between
families with one term converted and one not. The unit that survives the copy is the one that makes
the sentence read naturally, and dimensional analysis is the only check that catches it — no test
does, because the formula produces a number.

## 3 · Ground / Source
`elewise/fallback/tiling-flow.md:42-56`, §3 in full:

```
## 3. UB切分

原dtype直算分支:
  bufferDivisor = bufferNum * elemBytes

升精度分支:
  bufferDivisor = bufferNum * elemBytes + K * sizeof(float)

maxElemNum = (ubSize - extraSize) * 8 / bufferDivisor
ubFormer = AlignDown(maxElemNum, 256*8/minDtypeBits)

ubLoopFormer = CeilDiv(blockFormer, ubFormer)
ubTailFormer = blockFormer - (ubLoopFormer-1) * ubFormer
```

Note that the *alignment* line two rows down, `AlignDown(maxElemNum, 256*8/minDtypeBits)`, is
bits-based and dimensionally consistent (`256 × 8` bits divided by bits per element gives elements) —
so the same code block mixes a bits-based alignment with a bytes-based divisor. `minDtypeBits` is used
here and `elemBytes` in the divisor; the two are the same quantity in different units, three lines
apart.

`elewise/fallback/script/elewise_tiling.py:168-179`, the script's version:

```python
def _calc_ub_former_basic(cfg: _ElewiseConfig, k_extra_bufs: int) -> int:
    """Calculate UB former with basic double-buffer division."""
    double_buffer = 2
    if k_extra_bufs > 0:
        buffer_divisor = double_buffer * cfg.buffer_num * cfg.elem_bytes + k_extra_bufs * 4
    else:
        buffer_divisor = double_buffer * cfg.buffer_num * cfg.elem_bytes
    max_elem_num = (cfg.ub_size - cfg.extra_size) // buffer_divisor
    align_factor = ALIGN_256 // cfg.elem_bytes
    ub_former = (max_elem_num // align_factor) * align_factor
    if ub_former <= 0:
        ub_former = align_factor
    return ub_former
```

Two further differences from the markdown, both in the script's favour. The alignment factor is
`ALIGN_256 // elem_bytes` — bytes divided by bytes per element, giving elements, consistent with the
markdown's bits form and simpler. And there is a floor: `if ub_former <= 0: ub_former = align_factor`,
so a shape that cannot fit still gets a legal minimum rather than zero. The markdown has no floor, and
its `ubLoopFormer = CeilDiv(blockFormer, ubFormer)` divides by it.

`broadcast/fallback/tiling-flow.md:82` and its script,
`broadcast/fallback/script/broadcast_tiling.py:219-221`:

```
maxElemNum = (ubSize - extraSize) * 8 / (bufferNum * maxDtypeBits)
```
```python
def _calc_max_elem_num(cfg: _TilingConfig) -> int:
    raw = (cfg.ub_size - cfg.extra_size) * 8 // (cfg.buffer_num * cfg.max_dtype_bits)
```

Broadcast's markdown and script agree exactly, and both are dimensionally closed. So the divergence is
specifically the elewise markdown, and specifically its divisor.

The promotion branch inherits the same defect: `bufferDivisor = bufferNum * elemBytes + K *
sizeof(float)` adds bytes to bytes, which is internally consistent, and is then multiplied against a
bits numerator by the same line. The script's promotion branch adds `k_extra_bufs * 4` to a
bytes divisor and divides a bytes numerator — consistent.

`extraSize`, `bufferNum`, `K` and `maxDtypeBits` are given no values in either markdown document;
`extraSize` defaults to 0 in both scripts and `bufferNum` is a caller parameter. Under 0104's
provenance rule the double-buffer 2, `MIN_TILING_BITS = 32768`, `ELEM_ALIGN_FACTOR = 512` and
`ALIGN_256 = 256` all trace to literals and are software 经验值; `ubSize` is a chip specification
field and must be queried (0141), which neither script does — both default it to `248 * 1024`
(C-006, cited not duplicated).

Registered as C-950tiling-025: the same UB formula in three forms, one dimensionally unclosed, with
the only dimensionally-sound elewise copy living in the script rather than in the document.

## 4 · Procedure
Proposed. Arm 1 needs no device and is permitted in this phase; it has not been run.

Arm 1 — dimensional and numeric cross-check, no device. Evaluate all three formulas at the queried or
assumed `ubSize` for every dtype in {int8, fp16, bf16, fp32} and `bufferNum ∈ {1, 2, 4}`, tabulate
`maxElemNum` and the implied UB bytes, and record which forms exceed the capacity and by what factor.
This is arithmetic and establishes nothing about a board; it is recorded as arithmetic.

Arm 2 — allocation test on a named 950 board (950PR or 950DT); never run in this phase.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved.

Take one elementwise operator (`Abs`, fp16, `dim0 = 2^24`) and build three kernels differing only in
which formula computed `ubFormer`: the elewise markdown form, the elewise script form, and the
broadcast form. One compiler pin; md5 each; host echo of `ubFormer`, `ubLoopFormer`, `blockFormer`,
`coreNum` and the queried `ubSize`. For each: record whether it builds, whether it launches, whether
the output matches an fp64 reference within the operator's declared tolerance, and `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped. Repeat at int8 and fp32,
where the predicted overshoot factors differ (16× and 4×).

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` is
248 KiB (queried per 0141, and this family's script hardcodes it); that the markdown form fails — arm 2
exists to find out, and if it succeeds the dimensional reading in §2 is wrong; that a `ubFormer` that
builds was used (host echo required).

## 5 · Checker — acceptance declared before the run
Verdict variable `md_form_viable`: true iff the markdown-derived `ubFormer` builds, launches and
produces a correct result. Declared before the run: this entry's reading is supported iff
`md_form_viable` is false at every dtype. The OVERTURN fires iff `md_form_viable` is true at any dtype
— the formula would then be producing something other than what the dimensional analysis says, and
this entry is corrected in place per the template's promotion note. Verdict `overshoot_factor(dtype)`
from arm 1, expected to be `8 / elemBytes`, reported as computed. Verdict `db_charged`: whether the
script's double-buffer factor is needed, from comparing the script form against the broadcast form on
the same case.

The exit code is not the verdict: an allocation that silently clamps to a legal size exits 0 and runs
correctly, which would score `md_form_viable = true` for a tile that was never attempted. The host
echo of `ubFormer` must therefore match the value the formula produced, any mismatch marks the point
`clamped`, and the checker goes red rather than issuing a verdict when a point is clamped. Second
guard: the queried `ubSize` is printed with every point and the checker fails if it differs between
the arithmetic and the run, since the whole comparison is against a capacity.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 507 904 / 31 744 / 63 488
figures in §2 are arithmetic on upstream's formulas, computed here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and arm 1 — which needs no device — has not been run either. The entry does not
establish that the markdown formula fails on a board; it establishes that the three stated forms
disagree and that only one closes dimensionally while also charging double buffering. It does not
establish `extraSize`, `bufferNum`, `K` or `maxDtypeBits`, none of which upstream values. It does not
establish `ubSize` for any board. It does not establish that the double-buffer factor of 2 is correct
for elementwise and absent-by-design for broadcast — that difference is recorded, not adjudicated. No
chip is named anywhere in the elewise or broadcast markdown, so BOARD is `family-claimed(unverified)`
and the chip is unstated; §4 arm 2 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board, including the `DAV_2201` branch the broadcast
family carries (0155).

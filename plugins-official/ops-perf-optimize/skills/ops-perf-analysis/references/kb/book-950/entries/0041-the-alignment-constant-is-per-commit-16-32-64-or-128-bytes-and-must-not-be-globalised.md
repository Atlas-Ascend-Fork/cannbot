```
ID:        0041-the-alignment-constant-is-per-commit-16-32-64-or-128-bytes-and-must-not-be-globalised
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-01-aligned-contiguous-copy.md:43 — "对齐阈值来自当前 API/硬件契约；950 历史提交中出现 16B、32B、64B、128B 等不同约束，不能抽成一个全局常量"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-05-l2-bypass-one-shot.md:40 — "对齐按物理布局而非逻辑 shape 判断。950 历史样本以 128B cache line 校验，ND/NZ 与 scale 的 stride 分别检查；实际 API 以当前 CANN 头文件为准"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an inspection of the installed CANN headers and platform configuration showing a single
           alignment constant that governs every case the four values are cited for — the
           multiplicity would then be an artefact of the commit history rather than of the contract.
```

# 0041 · The alignment constant is per-commit — 16, 32, 64 or 128 bytes — and must not be globalised

## 1 · Claim
Upstream asserts that the alignment threshold comes from the current API and hardware contract,
that 950-era commit history shows 16-byte, 32-byte, 64-byte and 128-byte constraints in different
places, and that these must not be abstracted into one global constant. Upstream asserts, in the
L2 card, the same discipline for a different constant: 950 samples validate against a 128-byte
cache line, ND/NZ and scale strides are checked separately, and the authority is the CANN header
in use. Not established here; no constant was checked against any header or board.

## 2 · The wrong branch this removes
Four values for one concept is exactly the shape that invites a cleanup. An agent — or a
maintainer with good instincts — will define `ALIGN_BYTES` once and replace all four uses, and the
result compiles, passes the tests that exist, and is wrong wherever the real constraint was
larger. The failure is asymmetric: aligning to 128 where 32 was needed wastes UB and issues extra
padding; aligning to 32 where 128 was needed produces a misaligned access that is slow or
incorrect depending on which contract was being satisfied.

The general form, which is the transmissible part: a constant repeated with different values in
different places is evidence about the *contract*, not evidence of untidiness. Before unifying,
find out which contract each use is satisfying — cache line, DMA burst, register width, DataCopy
block — because those are four different quantities that happen to be powers of two in the same
range. This book's own record already lists four incompatible UB capacities under the same species
(0018).

## 3 · Ground / Source
`mem-01:39-44`, the stop rules, third bullet quoted in SOURCE, in context: the first two bullets
forbid judging contiguity from logical shape and require the slow path's padding value, tail mask
and write range to be verified independently; the fourth requires keeping the general path when
alignment-driven splitting shrinks tiles.

`mem-05:37-42`, the L2 card's stop rules, second bullet quoted in SOURCE. Note the differing
authority claims: mem-01 points to the API/hardware contract, mem-05 points to the CANN header in
use, and neither names a header or a field.

Where the individual values appear in this scope: 32 bytes as the RVEC load/store alignment in
vec-14 (0039) and in the same card's `BLOCK_TYPE_SIZE / sizeof(T)` formula; 64-byte alignment as a
requirement of `Brcb`/`WholeReduceMax`/`ReduceSum` buffers in vec-04 and vec-07, stated without a
unit; 128 bytes as the cache line in mem-05; 16 bytes as the M-dimension alignment in the MC²
split search (`pipeline_balancing.md:203-209`, entry 0067). Four constants, four contracts, one
skill. The claim that alignment must follow physical layout rather than logical shape is stated in
three cards (mem-01:41, mem-05:40, mem-06:41) and is the same discipline as this one applied to a
different property.

## 4 · Procedure
Arm 1 is read-only inspection of the installed toolkit and needs no device; it is the arm that can
actually settle where each constant comes from.
```bash
# read-only; -R follows symlinked dirs, -r does not
T=/usr/local/Ascend/cann-9.0.0-beta.2
grep -RIn "ONE_BLK_SIZE\|BLOCK_CUBE\|CACHE_LINE\|cacheLine\|ALIGN" $T/arm64-linux/asc/include | head -30
find $T -name "*.ini" -path "*platform*" -exec grep -Hn "align\|cache" {} \; | head -20
```
Arm 2 (later phase, needs a card; device selection per 0010, board token from the driver readout):
for each candidate alignment A ∈ {16, 32, 64, 128}, time a fixed-size copy whose source and
destination addresses are offset by every residue modulo 128, and record `aiv_time` as a function
of the residue. The pattern of the curve — where the steps are — identifies the boundaries that
actually cost, independently of what any document says.

## 5 · Checker — acceptance declared before the run
Verdict variable `step_boundaries` = the set of residues at which the timing curve steps by more
than the run spread. Acceptance for the "not one constant" claim: `|step_boundaries| > 1`, i.e.
the curve has structure at more than one granularity. Acceptance for a *specific* value A: a step
at every multiple of A and at no finer residue.

Exit code is not the verdict. The full curve is published; reporting only the extremes would hide
the intermediate steps, which are the entire content of this measurement.

Red input: an aligned-to-128 baseline, which must sit at the fastest end of the curve. If the
curve is flat everywhere, alignment costs nothing on this path at this size, and the correct report
is `no_alignment_effect` for that transfer size — not a refutation of the documents, which speak of
several different contracts, only one of which a copy timing can see.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
No constant is established here, and that is the point: this entry records that four values are in
use and forbids collapsing them, not which one applies where. Nothing was read from a header or a
platform ini for this entry beyond the commands above being written down. The 64-byte requirement
in vec-04/vec-07 does not even state its unit (elements or bytes), and this entry does not resolve
it. No board is implicated; alignment contracts may differ between 950PR and 950DT and nothing
here would detect that.

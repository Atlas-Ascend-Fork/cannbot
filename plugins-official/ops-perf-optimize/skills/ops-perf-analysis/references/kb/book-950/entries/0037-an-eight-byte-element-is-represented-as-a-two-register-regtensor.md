```
ID:        0037-an-eight-byte-element-is-represented-as-a-two-register-regtensor
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — upstream text plus a second, independent origin (the installed CANN
           9.0.0-beta.2 headers, read-only); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-12-preg-split.md:9 — "int64 用 `RegTensor<T, RegTraitNumTwo>` 表达（一个逻辑 int64 = 2 个物理 32-bit 子寄存器 `reg[0]/reg[1]`）"
           INSTALLED TOOLKIT (independent origin, read-only): /usr/local/Ascend/cann-9.0.0-beta.2/arm64-linux/asc/impl/basic_api/reg_compute/dav_c310/kernel_reg_compute_vec_binary_impl.h:1857-1863 — "if constexpr (sizeof(ActualT) == 8) { RegTensor<ActualT, RegTraitNumTwo> traitTwoDstTmpReg; … RegTensor<ActualT, RegTraitNumTwo> traitTwoSrcReg0;"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a header read at another toolkit pin, or a disassembly on a named 950 board, showing an
           8-byte element type held in a single physical vector register — the two-register
           representation would then be an implementation choice of one CANN version rather than
           a property of the programming model.
```

# 0037 · An eight-byte element is represented as a two-register RegTensor

## 1 · Claim
Upstream asserts, in a technique card, that int64 on arch3510 is expressed as
`RegTensor<T, RegTraitNumTwo>` — one logical value in two physical 32-bit sub-registers. The
installed CANN 9.0.0-beta.2 headers state the same shape independently and more generally: the
c310 register-compute implementation branches on `sizeof(ActualT) == 8` and builds
`RegTensor<ActualT, RegTraitNumTwo>` for destination and source operands, and the same
`RegTraitNumTwo` trait appears in other c310 advanced-API implementations. Both origins are
documents; nothing was compiled, and nothing was measured.

## 2 · The wrong branch this removes
An agent budgeting registers, or reading a `RegTensor<int64_t>` declaration, counts one. Two
consequences follow from counting wrong. Register pressure is underestimated by a factor of two
for the widest type, which is 0036's spill problem. And the operand width assumptions in masking
and lane arithmetic go wrong: a mask created for a 64-bit logical lane count is not the mask the
two 32-bit halves want, which is why the vendor implementation calls `MaskPack` before delegating
to the two-register path.

Stating the representation separately from the performance claim is deliberate. What the header
supports is *how the value is laid out*; what it does not support is *what that costs in
allocation* — that is a claim about the register allocator, and it stays in 0036 at the harvested
stratum.

## 3 · Ground / Source
Origin 1, `vec-12:9`, quoted in SOURCE, plus `metrics.md:97`, which states the same fact from the
trace-reading side: preg spill/reload 成对出现 … 寄存器溢出，int64 用双寄存器时实际 preg ×2.

Origin 2, independent per `form/STRATA.md` S2, read-only, no execution:
- `.../reg_compute/dav_c310/kernel_reg_compute_vec_binary_impl.h:1849-1863` — `MulAddDstImpl`
  admits `int64_t`/`uint64_t` among its supported types, and its `sizeof(ActualT) == 8` branch
  declares `RegTensor<ActualT, RegTraitNumTwo>` temporaries for destination and both sources, and
  calls `MaskPack(maskTrait2, mask)` to build the mask for the doubled layout;
- `.../adv_api/detail/math/clamp/clamp_c310_impl.h:209,227` — `using RegT = Reg::RegTensor<T,
  Reg::RegTraitNumTwo>;` used for the same purpose in an advanced-API implementation;
- the companion trait name `RegTraitNumOne` appears in the same file's guard
  (`CheckRegTrait<U, RegTraitNumOne>()`), so the one-register and two-register cases are
  distinguished explicitly in the vendor code rather than by convention.

`dav_c310` is upstream's own token for DAV_3510 / arch35 / the 950 family per
`form/CONVENTIONS.md` — a statement about which source tree implements it, not about a board.

## 4 · Procedure
Two arms. The first is read-only and needs no device; the second needs a card and settles the part
the headers cannot.
```bash
# Arm 1 — re-derive at the pinned toolkit (read-only; -R follows symlinked dirs, -r does not)
T=/usr/local/Ascend/cann-9.0.0-beta.2
grep -RIn "RegTraitNumTwo" $T/arm64-linux/asc/impl | head -20
grep -RIn "sizeof(ActualT) == 8" $T/arm64-linux/asc/impl/basic_api/reg_compute | head
```
Arm 2 (later phase, needs a card; device selection per 0010, board token from the driver): compile
a VF holding K live `RegTensor<int64_t>` values and the same VF holding K live
`RegTensor<int32_t>` values, sweep K upward, and read the disassembly for the number of distinct
physical vector registers referenced and for the first appearance of spill/reload.

## 5 · Checker — acceptance declared before the run
Verdict variables `phys_per_logical(dtype)` = distinct physical registers referenced divided by K,
from the disassembly, and `K_spill(dtype)`. Acceptance: `phys_per_logical(int64_t) == 2` and
`phys_per_logical(int32_t) == 1`; the corroborated claim of this entry is the first of those, and
`K_spill` belongs to 0036.

Exit code is not the verdict; the disassembler exits 0 on a function it fails to demangle. The
checker asserts that the int32 arm returns exactly 1 before any int64 figure is accepted — an
analysis that returned 2 for everything would otherwise "confirm" the claim.

Red input: the int32 arm, named above.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing compiled, run or measured; both origins are source text. It establishes the representation,
not its allocation cost — the ×2 preg pressure claim stays unverified in 0036. It is specific to
one toolkit pin on one machine and to the `dav_c310` implementation directory; another CANN
version may lay 8-byte types out differently. It says nothing about which operations support
8-byte types (the sets differ per API, cf. 0246), about the physical register count of the
architecture, or about any board. Nothing transfers to the 910 book.

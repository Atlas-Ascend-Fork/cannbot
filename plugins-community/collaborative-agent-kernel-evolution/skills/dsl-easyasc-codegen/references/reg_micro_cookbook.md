# Reg/micro cookbook (a5 data-dependent kernels)

Patterns for **reg-based, data-dependent** a5 kernels — gather/LUT, sort/merge,
compact/filter, histogram/scatter-stat. These are NOT elementwise/tiling ops; the
`easyasc_a5_cheatsheet.md` cube+UB material does not cover them.

A data-dependent kernel is one whose control flow or memory access depends on the input
*values* (indices, ordering, counts), not just shapes. They are authored at the micro
(`@vf` / register) level: `RegTensor`-sized batches, `MaskReg` predicates, gather/scatter,
and horizontal reductions — rather than whole-UB-tensor vec ops.

> **Resolve semantics against the hardware.** easyasc a5 `gather/select/vmin/vmax/...`
> lower onto arch35 `MicroAPI` (`RegTensor<T>` + `MaskReg` + `MaskMergeMode`). Same name
> ≠ same thing vs a2. For the full **name → MicroAPI mapping table, recipes, and pitfalls
> with file + symbol pointers into real arch35 kernels**, see
> [`arch35_micro_reference.md`](arch35_micro_reference.md). Read the cited kernel before
> guessing an op's behavior — that doc is the ground-truth index; this one is the
> conceptual map of *which pattern to reach for*.

---

## Pattern A — LUT / gather / register broadcast

**When**: dtype conversion via a lookup table, per-block scale/bias, or any `y[i] = table[idx[i]]`.

Techniques:
- **Keep the table UB-resident** and gather from it per chunk; one gather fills one register.
- **Broadcast a scalar to all lanes** (`Duplicate`) when a single value governs a chunk.
- **Gather indices are byte offsets, not element offsets** — scale by `sizeof(dtype)` first.
  Gather does no bounds checking; clamp out-of-range indices with a compare + select.
- **The gather/load source must match the register width** — pad the UB tensor (and the
  backing GM) so a full-width read never runs past the end, then mask out the junk at store.
- **Prefer a bit-pattern reinterpret over a LUT** when the conversion is a pure bit reshuffle
  (e.g. an exponent-only float format → wider float = a fixed shift). A shift + reinterpreted
  view is far cheaper than a table gather and carries no lookup cost.
- **For masked work on narrow dtypes, prefer dual-compute + `select`** over a masked
  elementwise op — masked arithmetic on narrow types is unreliable in the simulator
  (see `error_recipes.md`). Compute both candidates, splice with a mask.

Study (arch35): the `gather_nd` / indexed-load kernels and any kernel using `DataCopyGather`.

---

## Pattern B — sort / merge

**When**: dedup, set operations, top-k, ordering, run detection — anything needing sorted data.

Techniques:
- **Use the HW sort intrinsics** (`Sort` / `MrgSort`) rather than hand-rolling, when available.
  `MrgSort` merges several pre-sorted lists in one shot; pad unused list slots and set the
  valid-bit tail accordingly.
- **Sort operates on `(value, index)` structs** — interleave value+index before sorting and
  de-interleave (gather with the struct stride) after.
- **Sorting integers via the float path**: a direct int→float cast is exact only within the
  mantissa range. For full integer range, sort on a **sign-bit-flipped bit-reinterpretation**
  (XOR the sign bit) so signed order matches unsigned bit order; flip back after.
- **Handle alignment**: sort/concat/extract process fixed-size chunks. Pre-fill the padded
  region with a sentinel (−inf ascending, +inf descending) so partial blocks sort correctly.
- **Detecting run boundaries** (leaders / duplicates): a scalar walk is fine at small sizes;
  to vectorize, use an adjacent-difference (`x[i] != x[i±1]`) producing a boundary mask.
- **A non-sort route can win**: HW sort carries a fixed dispatch overhead. For small outputs
  a binary-search or merge route may beat it — see `micro_perf_rules.md` §algorithm-selection.

Study (arch35): the `sort` / `sort_with_index` / `top_k` kernel families.

---

## Pattern C — compact / filter (variable-size output)

**When**: keep only the elements passing a predicate, producing a dense prefix plus a count.

Techniques:
- **Stream-compact with the mask-gather primitive** (`GatherMask`): packs masked lanes
  contiguously. Reset the count register before the loop and read it back after to get the
  output length.
- **Count via reduction**, but **derive counts algebraically when a relation exists** instead
  of computing each independently — e.g. when totals are fixed, compute one count and subtract.
  This removes whole reduction + cast + barrier chains.
- **Misaligned neighbor access** (comparing a lane against its shifted neighbor across a chunk
  boundary): use the **unaligned-load** primitive (with its Pre/Post wrappers) plus **sentinels**
  at the two chunk edges. Only the boundary sentinels are read — don't waste writes on interior pad.
- **Variable-size copy-out**: write a prefix of length `count` per section plus a separate sizes
  tensor; the host (or a downstream op) splits on the counts.

Study (arch35): the `unique_consecutive` kernels (compaction, adjacent-diff, variable-size copy-out).

---

## Pattern D — histogram / scatter-stat

**When**: bucket counts, duplication/repetition scoring, mode/heavy-hitter estimation, choosing a
downstream template (e.g. sort vs atomic-add) from a data-distribution statistic.

Techniques:
- **Fold all bytes of a wide key into one bucket byte** (XOR-fold) rather than taking a single
  byte — a single-byte bucket discards the other bytes, so unrelated data aliases into the same
  buckets and the statistic becomes meaningless.
- **Use two independent views** to defeat structured-input aliasing: one on the raw fold, one on
  a hashed fold (e.g. an FNV-style multiply-xor). Combine the two scores so a bucket only counts
  as "concentrated" when both views agree.
- **Score with a normalized statistic, not a bare max** — e.g. `max / (#buckets above a noise
  floor)`. A bare max mistakes a flat, noisy histogram for a real peak.
- **Width constraints**: histogram/bucketing primitives run on fixed lane widths; document any
  "length must be a multiple of N" contract on the op and tail-pad accordingly.

Study (arch35): the index-statistics / `scatter_nd_add` indices-sort utilities and `top_k` radix histograms.

---

## Cross-cutting authoring rules for reg/micro kernels

1. **Lane width is fixed by dtype** (wider dtypes → fewer lanes per register). Tile inner chunks
   to the lane width, not to an arbitrary `TILE_L`.
2. **Pre-compute permutation and mask tables on the host**, pass them as UB tensors. Building
   index/permutation/half-masks at runtime wastes micro instructions.
3. **Reinterpret beats cast** whenever the conversion is a pure bit reshuffle; reserve a real
   `Cast` for genuine value conversions.
4. **Mask dtype must match the register dtype** across mask creation, the op, and the data copy.
   Narrow/wide dtypes need explicit mask pack/unpack — mismatches corrupt lanes silently.
5. **Read the cited arch35 kernel** (`arch35_micro_reference.md`) before guessing an a5 micro op's
   semantics — direction, argument order, and mask conventions are not inferable from the name.

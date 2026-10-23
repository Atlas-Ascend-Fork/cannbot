# Performance Question Playbook

## From Perf Symptom To Compiler Question

Rewrite the current round symptom into one narrow compiler-side question before reading source. Good starting forms are:

- which pass family would explain this stage transition?
- which subsystem would plausibly introduce this copy or sync behavior?
- which compiler-side constraint does this IR symptom imply for the current operator?

## Suspicious Stage Transition

- Start from the suspicious adjacent stages already identified in `opt-round-N/ir/`.
- Read pass docs first.
- Then inspect the matching `<compiler-source-dir>/bishengir/lib/` subtree.

## Vectorization Loss

- Confirm the loss in IR first.
- Read pass or feature docs for the likely vectorization subsystem.
- Inspect `<compiler-source-dir>/bishengir/lib/Conversion/` and `<compiler-source-dir>/bishengir/lib/Transforms/`.

## Copy Or Sync Growth

- Confirm the growth in IR or `perf-analysis.md`.
- Read feature docs first.
- Inspect dialect or conversion code under `<compiler-source-dir>/bishengir/lib/` that can introduce those operations.

## Buffer Expansion Or Memory-Planning Issue

- Confirm the symptom in IR first.
- Read feature docs for memory- or layout-related behavior.
- Inspect the matching implementation subtree under `<compiler-source-dir>/bishengir/lib/`.

## Fusion Or Lowering Shape Regression

- Confirm where the structure changes across stages.
- Read pass docs first, then inspect the implementation subtree under `<compiler-source-dir>/bishengir/lib/`.

## Vector Engine Saturation In Split/Mix Kernels

- Confirm what the vector-side functions actually own before attributing the
  saturation to data movement. A split/mix kernel usually exposes one
  cube-side function and several outlined vector-side functions; check whether
  the vector-side functions take any global-memory arguments at all. When they
  take only UB buffers and scalars, the vector engine is computing **per-lane
  address/mask vectors** (often i64) that the cube side then uses to drive its
  own global loads — the saturation is addressing work, not byte movement.
- Locate operator staging by the LL-level helper calls in the cube-side
  function and attribute each to its **argument index** (trace which kernel
  argument each staging helper consumes) before blaming a specific operand.
  Distinguish helper kinds: a plain 2D-copy helper vs a transpose/NZ helper; an
  ND-to-fractal copy helper is cube-side **hardware DMA staging** and its
  presence does not imply vector-side layout conversion. Remember that for the
  mix path this staging can come from a **precompiled template library** rather
  than a steerable pass; passes that fuse transposes into loads may live on a
  different lowering path and never match the mix kernels.
- Standardize the census as evidence: per-function argument spaces (global vs
  on-chip), staging/helper call counts with argument indices, and an **A/B
  diff of those counts between candidate revisions**. Prefer the discriminating
  reading "vector time tracks iteration count x per-iteration lane count" over
  "vector time tracks bytes moved". Working escalation order: engine profile
  (which engine is hot) -> IR function-role census (who does what) -> compiler
  source (why the lowering chose it). The same census is a useful standard step
  for the IR-analysis skill, not only for compiler-source questions.
- Check the load-form constraint: masked `tl.load` lowers to an
  init-out-buffer/padded form, and some fusion passes explicitly reject loads
  with padding fields. Unmasking the hot loads (zero-padded operands) is often
  the prerequisite, not the fix itself.
- Check whether an operand-layout shortcut exists but is unreachable from the
  frontend: the compiler may seed a fractal layout for rank>=4 global values or
  accept layout annotations, while the Triton frontend flattens arguments to
  rank-1 and offers no annotation channel. `tl.make_block_ptr` metadata may not
  change the lowering at all.
- Finish by translating the finding into a source-side action: restructure the
  hot loop so its loads become scalar-affine and mask-free with fewer
  iterations (deeper K chunks, 2D/row grid, fused taps), instead of trying to
  disable the staging from Triton source.

## Turning Source Findings Into Operator Actions

Always finish by writing:

- the likely compiler-side explanation
- what that implies for the current Triton operator
- what the next operator change should target

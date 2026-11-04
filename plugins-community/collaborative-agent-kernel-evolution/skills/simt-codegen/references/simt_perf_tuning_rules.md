# SIMT Performance Tuning Rules

> Read during `cake-evo` performance rounds after correctness is established (20/20).

---

## A. Decision Rules

### PERF-1: Classify the bound before tuning

Compute effective bandwidth (bytes transferred / device time) against the device peak (~1 TB/s on A5). If cases with equal byte counts differ in execution time, the kernel is compute-bound or occupancy-bound — UB staging and coalescing improvements will not help.

### PERF-2: Occupancy first for compute-bound element-wise ops

Raising `__launch_bounds__` + threads-per-block is usually the single largest lever for compute-bound ops. Time scales approximately as 1/threads up to the 56-core x 2048-resident-thread ceiling (~115K concurrent lanes on A5).

**The sign flips for memory/index-bound ops.** PERF-1 gates PERF-2 — classify first.

### PERF-3: Unroll sweet-spot is small; watch occupancy

ILP=2 (phased dual-load) is typically optimal for latency-bound random-load kernels. Higher unroll raises register pressure that lowers occupancy, and occupancy x in-flight-loads is the real product — u4/u8 regress.

8x unroll won for transpose only because it is a pure data-movement op with no divergent compute pressure on registers.

### PERF-4: UB pre-staging pays off only with reuse

Stage GM to UB to compute to DMA-back wins only when a staged region is re-read multiple times to amortize the copy. Ops with one independent index per output element (`index.shape == output.shape`, e.g. `torch.gather`) have no slice reuse — UB staging is a strict net-add.

Reserve UB staging for ops with slice/broadcast reuse (e.g. `index_select`, reductions) or pure data-movement via the bitcast dodge (see `memory_optimization_guide.md` §9).

### PERF-5: Cache hints net-neutral when the working set fits L2; size-gate them

Forced streaming (`asc_ldcg`) hurts small/medium cases when the 192 MB L2 already holds the working set. Gate streaming bypass behind a size threshold (e.g. N > 8M elements) rather than applying unconditionally.

### PERF-6: For atomic-ballot kernels, sweep numBlocks downward

On contended atomic writes to hot cells, fewer blocks reduces contention and launch overhead, monotonically. Always sweep the cap in both directions. Do not assume max grid = max speed.

### PERF-7: Coalesced full-scan beats scattered bounded-work

Reducing the iteration domain (e.g. scanning only the updated elements instead of the full output) is a loss if it converts coalesced writes into scattered ones. Memory access pattern dominates work count on this hardware.

### PERF-8: Bit-width-aware narrowing

When operand magnitudes provably fit a narrower type, compute in the cheaper width. For integer reductions like GCD, `gcd(a, b) <= min(|a|, |b|)`, so when both operands fit in 32 bits, use uint32 binary GCD instead of uint64.

### PERF-9: Stop honestly at the ceiling

After the tuning space saturates, test structural hypotheses one at a time and measure each. If N independent structural levers all regress or wash, the op is at its physical ceiling — report that rather than spending additional rounds past diminishing returns. Keep the best correct variant as the fallback body for any specialized path so specialization can never regress the baseline.

### PERF-10: Time thermally-fair

Cross-round/variant comparisons must be re-timed back-to-back in one session against a same-session baseline. Sessions can differ approximately 5% on thermals, which is larger than most real perf wins. Interleave A/B (round-robin, same session) for deltas below approximately 1.5x.

---

## B. Known Physical Ceilings

Do not re-sweep these — they are from hardware measurements.

| Op | Ceiling | Bound | Notes |
|----|---------|-------|-------|
| gather | ~2.35x | HBM-latency (random single-element reads, no slice reuse) | 4 structural disproofs; 3x is unreachable |
| gcd (int32 full-range) | ~1.84x | compute (GCD iters proportional to bit-width; ctz blocked on bisheng) | int16 (15-bit) reaches 2.33x; int32 (31-bit) has ~2x the iterations |
| scatter (clone-algo) | ~1.6x | launch-bound (2 stream-ordered launches; fusing races cross-core) | single-launch kernel performance is open |
| top_k | 9.458x | compute on O(k*S) for grid-saturated cases | scan-partition |
| transpose | 2.42x | memory/index-latency on large-square strided transposes | aspect < 8 shapes stay on direct path; no lever beat direct there |

---

## C. Reusable Optimization Levers

### Rank specialization

`template<typename T, uint32_t RANK>` with register-resident coordinate arrays and fully-unrolled index math. The per-element integer math (modulo, divide, stride multiply) for N-D indexing is the dominant cost in strided-access ops, not GM bandwidth.

Generalizes to any N-D index-math-bound op (transpose, gather, scatter, any multi-dim permutation).

### UB-bitcast dodge

For pure data-movement ops (no arithmetic on values), carry 4-byte dtypes (float32, int32) through a `float` UB tile via raw pointer bitcast, and int64 through native int64 UB. Sidesteps the 507035 non-fp32/int64 UB fault while remaining bit-exact (NaN/inf survive).

See `memory_optimization_guide.md` §9 for carrier/TILE constraints and shape-gating rules.

### Cooperative disjoint-band selection

For under-parallelized large-k/small-numSlices reductions: assign tpg threads per slice, each owning a disjoint output-rank band. Band-start cursor via a self-contained inline 4-bit MSD radix rank-select (histogram overlays candV[0..15], stays under the 507035 private-array ceiling). Adaptive host gate fires only where it pays (`numSlices < 2048 && S <= 32768 && k*S > 1e6`); `tpg=1` everywhere else reproduces the baseline exactly (zero regression).

A14-safe: no device helper calls, single-launch, no scratch.

### Two-launch GM-scratch scan-partition

For tiny-numSlices huge-S cases: split S into P = sqrt(S/k) contiguous chunks over two stream-ordered launches. Phase A: P blocks parallel-reduce their chunk-local top-k global indices into an int64 scratch output tensor (not OPP workspace — avoids error 334). Phase B: one worker/slice merges the P*k candidates into the final sorted top-k.

Adaptive gate: `dtype != int64 && numSlices < 64 && S > 32768 && S*k > 1e6`.

### F3 single-owner partition

Flag any kernel where two code paths write the same output cell under different partitions (the "no-clone race"). Route the special branch first and `return` before the general seed step, so each output cell has exactly one writer.

### Env-driven grid/block sweep without rebuild

Generalize the pattern of `<OP>_TPB` / `<OP>_MAXBLK` environment variables that the host reads at tiling time, with baked defaults for submission. Enables fast configuration sweeps during cake-evo rounds without kernel recompilation.

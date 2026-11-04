# Builtin Parity Optimizations

> Optimization ideas to explore when your SIMT op is **correct but slower than the builtin**.
> These are not correctness rules and do not change generated-code defaults — they are a menu
> of techniques to consider during performance tuning.
>
> Cross-references: `memory_optimization_guide.md` (lessons 1, 3), SKILL.md Rule 7 (lesson 2).

---

## 1. Stage GM→UB, compute on-chip, DMA back

**What it is**: Copy the working set from global memory (`__gm__`) into UB (`__ubuf__`) once,
perform all computation on-chip, then DMA the result back to GM. Avoid indexing `__gm__`
per-element inside the hot loop.

**When it helps**: Compute-heavy ops; random-access patterns (scatter/gather-style reads);
any op where the same GM region is touched multiple times per output element.

**When it does NOT help / trade-off**: Pure coalesced memory-bound copies where every element
is read exactly once — the DMA overhead can exceed the cache benefit. Also limited by the
VF-readable UB ceiling (8 KB static `__ubuf__` in a VF function; see
`memory_optimization_guide.md` §6).

---

## 2. Collapse multi-launch orchestration into one in-place kernel

**What it is**: A host-side init tensor (`zeros_like` or `empty`) + a copy pass + a compute
pass is often replaceable by a single kernel that aliases output to input and performs init +
compute behind a device barrier, eliminating host round-trips and extra kernel-launch overhead.

**When it helps**: Ops with a fixed, enumerable output domain where the "base" value is just
the input (scatter, masked fill, where). Saves one kernel launch and one host allocation.

**When it does NOT help / trade-off**: When the two passes have a true cross-core data
dependency that cannot be expressed within a single VF (see SKILL.md Rule 7 — the safe
serialization pattern remains two separate launches with a phase attr when in doubt).

---

## 3. Per-core contiguous slices + UB double-buffering

**What it is**: Assign each core a contiguous region of the output domain and ping-pong two
UB buffers so DMA (MTE2) overlaps compute (V pipe), instead of a pure global grid-stride
with single-buffered per-element GM traffic.

**When it helps**: Bandwidth-bound ops with large working sets per core; ops where DMA
latency (LDG RTT ≈ 173 cy, STG RTT ≈ 255 cy on A950) is the bottleneck.

**When it does NOT help / trade-off**: Small inputs where the double-buffer setup cost
dominates; ops with irregular access patterns that prevent contiguous slice assignment.
See `memory_optimization_guide.md` §1 (coalescing) and §6 (UB pre-staging) for the
underlying mechanics.

---

## 4. Order-based tie-breaking instead of a global atomic ballot

**What it is**: "Last-write-wins" and similar duplicate-handling semantics can come from
processing each output row serially on one core (natural overwrite) rather than a separate
cross-core atomic-max winner pass.

**When it helps**: Ops with duplicate index handling (scatter variants, segment ops) where
the spec allows last-write-wins or any-winner semantics. Eliminates the atomic overhead
entirely.

**When it does NOT help / trade-off**: When the spec requires a specific winner (e.g.,
first-write-wins, min/max reduction) that cannot be guaranteed by serial processing order.
Serial-per-row also limits parallelism — only viable when row count >> core count.

---

## 5. Cheaper algorithmic primitive + fuse broadcast into copy-in

**What it is**: Prefer the cheaper per-element primitive (e.g., bit-shift or subtraction
over integer modulo) and broadcast/expand a scalar or small tensor during the GM→UB load
rather than materializing an expanded tensor on the host before the kernel call.

**When it helps**: Ops with a repeated scalar operand (bias add, scale, modulo-based index
remapping). Fusing the broadcast into the DMA load eliminates a host allocation and a
separate copy kernel.

**When it does NOT help / trade-off**: When the "cheaper" primitive changes numerical
behavior (e.g., shift vs. division for non-power-of-two denominators). Verify equivalence
before substituting.

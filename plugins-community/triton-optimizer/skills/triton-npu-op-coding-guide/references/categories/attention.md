# Attention — softmax(Q·Kᵀ)·V with blocked KV and online softmax

## Scope

The attention main chain `softmax(Q @ K^T / sqrt(d)) @ V` in its fused form:
multi-head attention, SDPA, flash-attention forwards, GQA/MQA (KV-head
sharing), causal/sliding-window/softcap masks, and prefill/decode variants.
Projections around the attention are GEMMs — [matmul.md](matmul.md) owns their
rules (weight layout, transposes, tiling); [softmax-norm.md](softmax-norm.md)
owns the softmax numerics; this card owns the blocked online-softmax structure
that fuses them.

## Writing essentials

- Never materialize the `[S_Q, S_K]` score matrix. One program owns a
  `(batch, head, q_block)` task: load the Q tile once, loop over KV blocks, and
  carry the online-softmax state in registers across iterations —
  `m` (running row max), `l` (running exp-sum), `acc` (`[BLOCK_Q, BLOCK_D]`
  fp32 output accumulator). Per KV block:
  `m_new = max(m, rowmax(scores))`, `p = exp(scores - m_new)`,
  `alpha = exp(m - m_new)`,
  `l = l * alpha + sum(p)`, `acc = acc * alpha + tl.dot(p, v)`,
  `m = m_new`. Dropping the `acc *= alpha` rescale or the `m` update silently
  corrupts every later block. Final output is `acc / l`.
- Both `tl.dot` operands must be the same dtype, explicitly cast: a masked
  `tl.load` keeps its pointer's element dtype (`other=0.0` does not promote
  the result), and mismatched operands are a hard compile error. Keep
  operands in the input's native dtype
  with an fp32 accumulator; never replace the dots with per-dimension
  outer-product loops (`for d in range(D): scores += q[:, None] * k[None, :]`)
  — that idles the matrix unit entirely.
- Pin the precision contract before writing: what dtype does the reference
  compute each segment in? If the reference works in fp32 (`.float()` calls),
  keep `scores`/`p`/`acc`/`l` fp32 throughout. If the reference computes in
  fp16/bf16, it rounds at every step (matmul output, softmax output), and the
  implementation must round at exactly those steps — computing "more
  accurately" than the reference fails verification. Write dtype dispatch with
  fp16/bf16/fp32 branches complete and fp32 as the `else` fallback, so an
  fp32 input is never cast down mid-chain.
- Exclude padded KV lanes explicitly. When `S_K % BLOCK_KV != 0`, the masked
  load's `other=0.0` is not a mask: `exp(0 - m) > 0` ghost columns leak into
  the softmax denominator and shrink every output. Apply
  `tl.where(kv_valid, scores, NEG)` before the row max and
  `tl.where(kv_valid, p, 0.0)` before the sum. Test with both divisible and
  non-divisible sequence lengths.
- Mask with a finite negative constant, never `-inf`: an entirely masked row
  produces `exp(-inf - (-inf)) = NaN`. Use a `tl.constexpr` like `-3.0e38` or
  `-1e30` (a plain module global raises `NameError` inside the kernel).
- `BLOCK_D = ceil16(head_dim)` with a `d_offs < D` mask — not
  `next_power_of_2(D)`, which wastes a third to a half of the tile on common
  head dims (96, 160, 192), and not a hardcoded constant, which silently
  computes only the first dimensions when `head_dim` grows. Do not put
  `BLOCK_D` in an autotune search space for the same reason.
- Express causal/window masks as `tl.constexpr` flags (`IS_CAUSAL`,
  `HAS_LOWER`/`HAS_UPPER`, `HAS_SOFTCAP`) so unused mask code is compiled out,
  and fold causal + window into per-q-block KV bounds on the host
  (`kv_lo`, `kv_hi` from the q-block's absolute positions). Do not align
  `kv_lo` up to a `BLOCK_KV` boundary — that re-scans up to half a block that
  is entirely masked. Compute mask conditions in absolute sequence positions
  (`q_pos >= kv_pos`), watching the off-by-one at block corners.
- Host side does no layout surgery: pass the original strides into the kernel
  (the head-dim axis is contiguous in the usual layouts) and let
  `BLOCK_D = ceil16(D)` masking handle D padding — no `.permute().contiguous()`,
  no zero-padded copies, no transposing K on the host; if a transposed view of
  K is needed, load it transposed through strides.
- Hoist input transforms (RoPE, position encodings, bias preprocessing) out of
  the KV loop into their own Triton kernel writing a workspace: recomputing
  them per KV block multiplies their cost by the iteration count, and their
  intermediates eat the on-chip memory that block sizes need. That kernel
  obeys the same grid rules as the main one, and takes separate input and
  output strides (a transposed-view input and a contiguous workspace have
  different strides; sharing one set scatters stores).
- Interleaved reordering (rotate-half RoPE) must come from one contiguous load
  split apart — `tl.split`/`tl.join` on a reshaped tile — never from computed
  partner indices (`offs_d - 1` / `offs_d + 1`) used as gather addresses,
  which degenerates to per-element access. RoPE's `inv_freq` must replicate
  the reference's arithmetic structure exactly (positive exponent, then
  reciprocal — not an algebraically equivalent `exp(-x)`): a 1-ULP difference
  is amplified by the sequence length. `tl.sin`/`tl.cos` already reduce large
  angles correctly — never reduce ranges by hand (`a - floor(a / 2π) * 2π`
  is less accurate, since 2π is inexact in fp32). There is no float64 on the
  Ascend backend; matching the reference's operation order is the only tool.
- Grid rule for every kernel in the operator, not just the attention kernel:
  `grid = (min(core_count, total_tasks),)` with an in-kernel stride loop
  (`for task in range(pid, total_tasks, num_programs)`). An auxiliary kernel
  launched with one program per row (`grid = (B * N * S,)`) hits the grid-dim
  hard limit on large shapes and fails at runtime. Pass the program count as a
  `tl.constexpr`.
- `tl.arange` arguments must be compile-time constants: any block-derived
  value (`ceil16(D)`, `BLOCK_D // 2`) must be computed on the host and passed
  as a `tl.constexpr` parameter, never derived from runtime shapes inside the
  kernel. Likewise, no runtime-indexed tile assignment (`acc[:, d] = x` with a
  loop variable) — use whole-tile operations.
- Compute the softmax scale on the host (`1 / sqrt(head_dim)`); whether the
  kernel multiplies by it or divides depends on the reference — if the
  reference divides and bit-exactness matters, replicate the division (see
  repair guide §11).
- GQA/MQA maps query heads to KV heads by `kv_head = q_head // (num_heads //
  num_kv_heads)` and addresses K/V at `kv_head * stride_head` — no KV copies.
  Validate the divisibility on the host.
- Dispatch prefill versus decode on the host: long-sequence prefill uses the
  blocked online-softmax path; decode (`S_Q` of 1 or a few) gains nothing from
  Q blocking and wants a split-K path that parallelizes over the KV length
  with a partial-result merge.
- When the reference calls a `torch_npu.npu_*` operator (fused-attention
  family), the NPU operator's real behavior is the golden — mask polarity,
  window semantics, and output shapes (for example `softmax_max`/`softmax_sum`
  returned with the last dimension padded to 8) can differ from the docstring
  fallback. Probe the actual op's behavior before writing the kernel. In
  conv-hybrid attention variants, set `torch.npu.conv.allow_hf32 = False` on
  the host before the first conv call — the default HF32 path visibly deviates
  from an fp32 reference.
- Size blocks by an area budget with everything live counted — the fp32 score
  tile plus the fp32 accumulator plus any transform intermediates — and shrink
  blocks for small shapes (`min` against the actual extents). A preventive
  `BLOCK = min(BLOCK, 64)  # avoid UB overflow` is a symptom: hoist the
  transform that eats the memory instead of capping the block. And do not
  split the fused attention into QK / softmax / PV kernels to save memory —
  the three-stage form materializes the score matrix this card exists to
  avoid. The compiler already hoists loop invariants and reuses buffers;
  hand-optimizing those is a no-op.

## Common mistakes and fixes

```python
# Wrong: per-dimension outer product instead of the QK dot
for d in range(D): scores += q[:, d, None] * k[None, d, :]
# Right: load K as [D, S_K] through strides; scores = tl.dot(q_tile, kT)

# Wrong: masked-load fill doing the masking job
s = tl.load(k_ptrs, mask=kv < S_K, other=0.0)   # then straight into exp
# Right: s = tl.where(kv < S_K, s, NEG)          # finite NEG, before the max

# Wrong: -inf mask constant
scores = tl.where(mask, scores, float("-inf"))  # all-masked row → NaN
# Right: NEG: tl.constexpr = -3.0e38            # exp(NEG - m) == 0

# Wrong: online update missing the rescale
l = l + tl.sum(p); acc = acc + pv               # earlier blocks over-weighted
# Right: l = l * alpha + tl.sum(p); acc = acc * alpha + pv; m = m_new

# Wrong: power-of-two head-dim block
BLOCK_D = triton.next_power_of_2(D)             # D=96 → 128, wasted lanes
# Right: BLOCK_D = ceil16(D) with (d_offs < D) masking

# Wrong: RoPE recomputed inside the KV loop
for kv in range(...):
    k = apply_rope(load(k_block))               # per-block transform cost
# Right: precompute rope_k in its own kernel; loop reads the workspace

# Wrong: interleaved pairing by computed gather indices
partner = tl.where(is_odd, offs_d - 1, offs_d + 1)
x_pair = tl.load(p + partner)                   # data-dependent addressing
# Right: one contiguous load, tl.split/tl.join for the even/odd halves

# Wrong: algebraically simplified inv_freq
inv = tl.exp(-e * LN_1E4)                       # 1-ULP off, grows with S
# Right: inv = 1.0 / tl.exp(e * LN_1E4)         # reference's op order

# Wrong: transform kernel sharing one stride set
rope_kernel[grid](q, q_out, ..., q.stride(0), q.stride(1), ...)
# Right: pass q's strides for the load and q_out's strides for the store

# Wrong: auxiliary kernel grid unfolded per row
rope_kernel[(B * N * S,)](...)                  # can exceed the 65535/dim limit
# Right: grid = (min(CORES, B * N * S),) with the in-kernel stride loop

# Wrong: runtime-derived arange argument
half = tl.arange(0, BLOCK_D // 2)               # BLOCK_D runtime-derived
# Right: pass HALF_D: tl.constexpr from the host

# Wrong: manual trig range reduction
a = ang - tl.floor(ang / TWO_PI) * TWO_PI
# Right: tl.sin(ang) directly — built-in reduction is more accurate
```

## Recommended patterns

Blocked online-softmax forward (one program per `(b, h, q_block)`):

```python
NEG: tl.constexpr = -3.0e38

@triton.jit
def attn_fwd_kernel(q_ptr, k_ptr, v_ptr, o_ptr, ...strides...,
                    S_Q, S_K, inv_sqrt,
                    HEAD_DIM: tl.constexpr, BLOCK_D: tl.constexpr,
                    BLOCK_Q: tl.constexpr, BLOCK_KV: tl.constexpr,
                    IS_CAUSAL: tl.constexpr, NUM_PROG: tl.constexpr):
    total = tl.num_programs(0) * tl.cdiv(S_Q, BLOCK_Q) * H  # task-space walk
    for task in range(tl.program_id(0), TOTAL_TASKS, NUM_PROG):
        b, h, q0 = decode_task(task)                       # host-folded mapping
        q = tl.load(q_tile_ptrs)                           # once, resident
        m_i = tl.full([BLOCK_Q], NEG, tl.float32)
        l_i = tl.zeros([BLOCK_Q], tl.float32)
        acc = tl.zeros([BLOCK_Q, BLOCK_D], tl.float32)
        kv_lo, kv_hi = kv_bounds(b, h, q0, IS_CAUSAL)      # host-side folding
        for kv0 in range(kv_lo, kv_hi, BLOCK_KV):
            kT = tl.load(kT_ptrs)                  # [BLOCK_D, BLOCK_KV] via strides
            v = tl.load(v_tile_ptrs)
            s = tl.dot(q, kT) * inv_sqrt           # fp32 accumulator
            s = apply_mask(s, q0, kv0)                     # finite NEG
            valid = kv_offs < S_K
            s = tl.where(valid, s, NEG)
            m_new = tl.maximum(m_i, tl.max(s, 1))
            p = tl.exp(s - m_new[:, None])
            p = tl.where(valid, p, 0.0)                    # ghost columns out
            alpha = tl.exp(m_i - m_new)
            l_i = l_i * alpha + tl.sum(p, 1)
            acc = acc * alpha[:, None] + tl.dot(p, v)
            m_i = m_new
        tl.store(o_ptrs, (acc / l_i[:, None]).to(OUT_DTYPE))
```

(The skeleton abbreviates pointer/stride plumbing — fill real strides and
masks; `decode_task` and `kv_bounds` are host-precomputed index math.)

Operand-dtype mismatch in `tl.dot`, `tl.trans`-before-dot alignment faults,
UB overflow from oversized score tiles, and 1-ULP scale-division mismatches:
see repair guide `triton-npu-repair-guide/references/repair-experience.md`
§9, §10, §16, §11.

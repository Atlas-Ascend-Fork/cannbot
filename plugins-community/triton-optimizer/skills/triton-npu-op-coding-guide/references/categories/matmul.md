# Matmul — GEMM contractions and fused epilogues

## Scope

Matrix-multiply contractions: `torch.matmul` / `mm` / `bmm` / `F.linear`,
einsum patterns like `ij,jk->ik`, transposed-weight projections, batched and
grouped (MoE) variants, and matmul-with-epilogue fusions (bias, activation,
scale/quantization). Linear-attention operators use this card for their
projection GEMMs and [attention.md](attention.md) for the softmax structure.

## Writing essentials

- Express every contraction as `tl.dot`: operands in their native dtype, an
  fp32 accumulator (`tl.zeros((BLOCK_M, BLOCK_N), tl.float32)`, the `tl.dot`
  default), cast to the output dtype once at the store. Never simulate the
  matmul with a broadcast multiply and reduction
  (`tl.sum(a[:, None, :] * b[None, :, :])`) — that idles the matrix unit and
  is a correctness-preserving but order-of-magnitude-slow shape. Do not upcast
  operands to fp32 unless the reference computes that segment in fp32
  (`.float()` in the reference is a precision contract — then fp32 operands
  are required, not forbidden). Keep all three dot block extents at least 16.
- Handle transposes through strides, never by materializing a transposed copy:
  `nn.Linear.weight` is `[out_features, in_features]`, so the projection is
  `x @ W^T` — pass `w.stride(1), w.stride(0)` (swapped) into the kernel. A
  wrong transposition on square weights is silent: shapes still match, only
  the values are wrong. Validate with non-square shapes while developing.
- Respect the row-width alignment rule: the contiguous-loaded row of each
  operand tile should be a multiple of 512 bytes (256 fp16/bf16 or 128 fp32
  elements). With no transposes the two row widths are the K and N tiles; with
  B accessed transposed both row widths come from the K tile, so align
  `BLOCK_K` first. `BLOCK_M=128, BLOCK_N=256, BLOCK_K=256` (fp16/bf16) is the
  standard starting point; scale blocks down for small matrices rather than
  padding them away.
- Use `tl.make_block_ptr` with `boundary_check` and `tl.advance` for regular
  2D tiles instead of hand-built index arithmetic — cleaner addressing, and
  ragged M/N/K edges are handled by the boundary check (`other` defaults to
  zero, the correct identity for the accumulator).
- Grid mapping: one program per output tile by default, with the standard
  grouped pid swizzle (`GROUP_SIZE` blocks of M sharing N columns) so
  neighboring programs reuse operands; or a persistent form with
  `grid = (min(core_count, num_tiles),)` and an interleaved block loop
  (`for t in range(pid, num_tiles, num_programs)`). Matmul work runs on AI
  (cube) cores — read `num_aicore` once at init and pass the program count as
  a `tl.constexpr` so the loop bound specializes.
- Budget every concurrently live tile against the on-chip memory ceiling:
  A tile + B tile + the fp32 accumulator (BLOCK_M × BLOCK_N × 4 bytes), plus
  any epilogue temporaries. Derive blocks from that sum, and cap any
  `next_power_of_2` size with `min(..., actual_extent)` so small matrices do
  not compile oversized tiles.
- Fuse the epilogue into the matmul kernel: bias add, activation, scaling,
  RoPE, or quantization applied to the accumulator before its store. Writing
  C to memory and launching a second pointwise kernel over it is the pattern
  to avoid. Keep one GEMM output per kernel by default — fusing two output
  tiles doubles the live accumulators and forces smaller blocks; adopt that
  only with measurements behind it.
- Feed and write tensors by stride, not by copies: pass input and output
  strides separately (a transposed view input and a contiguous workspace have
  different strides; sharing one set scatters stores to wrong addresses), and
  write the output directly in the target layout. Do not wrap the kernel in
  host-side `.contiguous()`/`permute` when the kernel can consume the original
  strides. Test with non-contiguous inputs — contiguous-only tests hide
  stride bugs.
- Two-stage GEMM chains (FFN-style `x @ W1 → activation → @ W2`): one kernel
  per stage with the activation fused in stage 1's epilogue; preserve the
  reference's intermediate dtype and cast timing. Grouped/MoE variants: each
  expert's token segment is a contiguous row range — compute the global row
  offset (`token_start`) on the host and base both the temporary and output
  stores on it; per-expert weights are addressed by `expert_id * stride(0)`.
- Quantized matmul chains follow the int path: int8 × int8 into an int32
  accumulator, dequantize/activate in fp32, requantize, second int8 dot —
  keep the int32 and fp32 stages explicit rather than folding through fp16.

## Common mistakes and fixes

```python
# Wrong: matmul as broadcast-multiply + sum (matrix unit idles)
acc += tl.sum(a[:, None, :] * b[None, :, :], axis=2)
# Right: acc += tl.dot(a_tile, b_tile)          # fp32 accumulator

# Wrong: projection without the weight transpose
y = tl.dot(x, w_tile)                    # w loaded as [in, out]
# Right: nn.Linear is y = x @ W.T — swap the weight strides at the launch:
#        kernel[grid](x, w, y, ..., w.stride(1), w.stride(0), ...)

# Wrong: fp16 accumulator
acc = tl.zeros((BM, BN), dtype=tl.float16)
# Right: tl.float32 accumulator; cast at the final store

# Wrong: unaligned tile rows
BLOCK_N = 100                            # fp16 row of 200 bytes
# Right: keep contiguous row widths multiples of 512B (256 fp16 elements)

# Wrong: uncapped power-of-two blocks
BLOCK_K = triton.next_power_of_2(K)      # K = 1000 → 1024, fine; but a
                                         # small K must cap the block too
# Right: BLOCK = min(next_power_of_2(extent), cap) with the UB budget checked

# Wrong: one stride set for input and output
kernel[grid](x, y, x.stride(0), x.stride(1))   # y has different strides
# Right: pass each tensor its own strides

# Wrong: host-side copies around the GEMM
x = x.permute(0, 2, 1).contiguous()
# Right: pass the permuted strides; let the kernel read strided tiles

# Wrong: transposing a tile inside the kernel before the dot
b = tl.trans(b_tile)
acc = tl.dot(a, b)                       # risks ADDR_MISALIGN (repair §10)
# Right: build/load the tile with the needed orientation via strides

# Wrong: cdiv from the wrong namespace
n = triton.cdiv(M, BLOCK_M)              # inside @triton.jit
# Right: tl.cdiv in-kernel; triton.cdiv on the host

# Wrong: MoE segment writing local rows
tl.store(out_ptr + local_row * stride, v)     # overwrites earlier experts
# Right: tl.store(out_ptr + (token_start + local_row) * stride, v)
```

## Recommended patterns

Standard tiled GEMM with grouped pid mapping and fused epilogue:

```python
@triton.jit
def gemm_kernel(a_ptr, b_ptr, c_ptr, M, N, K,
                sam, sak, sbk, sbn, scm, scn,
                BLOCK_M: tl.constexpr, BLOCK_N: tl.constexpr,
                BLOCK_K: tl.constexpr, GROUP_SIZE: tl.constexpr,
                OUT_DTYPE: tl.constexpr):
    pid = tl.program_id(0)
    num_pid_m = tl.cdiv(M, BLOCK_M)
    num_pid_n = tl.cdiv(N, BLOCK_N)
    num_pid_in_group = GROUP_SIZE * num_pid_n
    group_id = pid // num_pid_in_group
    first_pid_m = group_id * GROUP_SIZE
    group_size_m = min(num_pid_m - first_pid_m, GROUP_SIZE)
    pid_m = first_pid_m + (pid % group_size_m)
    pid_n = (pid % num_pid_in_group) // group_size_m

    a = tl.make_block_ptr(a_ptr, (M, K), (sam, sak), (pid_m * BLOCK_M, 0),
                          (BLOCK_M, BLOCK_K), order=(1, 0))
    b = tl.make_block_ptr(b_ptr, (K, N), (sbk, sbn), (0, pid_n * BLOCK_N),
                          (BLOCK_K, BLOCK_N), order=(1, 0))
    acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)
    for _ in range(0, K, BLOCK_K):
        acc += tl.dot(tl.load(a, boundary_check=(0, 1)),
                      tl.load(b, boundary_check=(0, 1)))
        a = tl.advance(a, (0, BLOCK_K))
        b = tl.advance(b, (BLOCK_K, 0))
    # epilogue on the accumulator (bias / activation / scale) before the store
    c = tl.make_block_ptr(c_ptr, (M, N), (scm, scn), (pid_m * BLOCK_M, pid_n * BLOCK_N),
                          (BLOCK_M, BLOCK_N), order=(1, 0))
    tl.store(c, acc.to(OUT_DTYPE), boundary_check=(0, 1))
```

Host: `grid = (triton.cdiv(M, BM) * triton.cdiv(N, BN),)`, or the persistent
form with the grid clamped to the cached AI-core count. Batched matmul adds
the batch index to the grid or walks it in the interleaved loop.

Mixed-dtype `tl.dot` failures, `tl.trans`-before-dot alignment faults, and
UB overflow from oversized tile sets: see repair guide
`triton-npu-repair-guide/references/repair-experience.md` §9, §10, and §16.

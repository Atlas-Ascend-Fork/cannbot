# Common Pitfalls for CV (Cube+Vector) Lowering

## Critical Pitfalls

### 1. Cross-Core Signal Mismatch

**Problem:** Cube sets signal at wrong granularity (e.g., per block_n instead of per block_m).

**Impact:** Vector reads stale data or deadlocks.

**Rule:** Match signal placement exactly to DSL. If DSL places `tl.cross_core_set()` after the inner `block_n` loop, place `CrossCoreSetFlag` at the same level.

### 2. Workspace Pointer Offset Error

**Problem:** Vector kernel reads from wrong workspace region.

```cpp
// WRONG: forgot to offset past matmul workspace
gm_inv.SetGlobalBuffer((__gm__ float*)workspace);

// CORRECT: offset by M*N floats
gm_inv.SetGlobalBuffer((__gm__ float*)workspace + (uint64_t)m * n);
```

### 3. Subcore Boundary Check Missing

**Problem:** Last subcore processes negative rows.

```cpp
// WRONG: no boundary check
uint32_t curr_m = sub_m;

// CORRECT: clamp to actual remaining rows
uint32_t curr_m = (sub_offset_m + sub_m <= actual_m) ? sub_m :
                  (actual_m > sub_offset_m ? actual_m - sub_offset_m : 0);
if (curr_m == 0) return;
```

### 4. Mixing up AIC Core Index vs Vector Subcore Index

**Problem:** Using `GetBlockIdx()` directly in vector scope.

```cpp
// WRONG in vector scope:
uint32_t coreIdx = AscendC::GetBlockIdx();  // This is the global block index!

// CORRECT in vector scope:
uint32_t aicoreIndex = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
uint32_t subcoreIndex = AscendC::GetSubBlockIdx();
```

### 5. Buffer Size Too Small for 2D Tile

**Problem:** Allocating buffer for `actual_n` elements but needing `L1_N` stride.

```cpp
// WRONG: buffer too small when actual_n < L1_N (UB layout uses L1_N stride)
pipe.InitBuffer(inQueue, 1, actual_n * sizeof(float));

// CORRECT: allocate for full tile including stride padding
pipe.InitBuffer(inQueue, 1, (L1Shape::M / VEC_NUM) * L1Shape::N * sizeof(float));
```

### 6. Forgetting `using namespace Catlass`

**Problem:** All Catlass types unresolved.

**Fix:** Add `using namespace Catlass;` after includes.

### 7. Wrong L0Shape K Dimension

**Problem:** Setting L0_K to match L1_K.

**Rule:** L0_K is hardware-determined, typically 64:
```cpp
using L0Shape = GemmShape<128, 256, 64>;  // L0_K = 64 always
```

### 8. Missing `Arch::Resource` Before BlockMmad

**Problem:** BlockMmad constructed without resource.

```cpp
// WRONG:
BlockMmad blockMmad;

// CORRECT:
Arch::Resource<ArchTag> resource;
BlockMmad blockMmad(resource);
```

## Performance Pitfalls

### 9. Not Using 2D Copy Helpers for Large Tiles

For CV vector scope with 2D tile layouts, use Catlass copy helpers:
```cpp
using CopyGmToUb = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
using CopyUbToGm = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
```
These handle stride-based 2D transfers efficiently. For 1D row-by-row access, `DataCopyPad` is acceptable.

### 10. Redundant Cross-Core Waits

Only call `CrossCoreWaitFlag` once per tile iteration in the vector scope. Do not place it inside inner loops.

### 11. Unnecessary Vector Scope for Pure Type Cast

**Problem:** When the Vector scope only performs `tl.vcast(dst, src)` for fp32→fp16 conversion with no other computation (no GELU, RMSNorm, reduction, etc.), using the full CV dual-core architecture introduces unnecessary overhead: workspace allocation, KernelVector class, cross-core synchronization, and 2D copy helpers — all for a single type cast.

**Impact:** Extra memory usage (workspace buffer), added latency from cross-core sync, and more complex code without computational benefit.

**Solution:** Use fixpipe mode. Set `ElementC = half` so the Cube hardware outputs fp16 directly via its built-in fixpipe unit. Remove KernelVector, workspace allocation, and all cross-core synchronization:
```cpp
// WRONG: full CV pipeline for a simple cast
using ElementC = float;   // Cube outputs fp32
using ElementD = half;    // Vector casts to fp16
// + KernelVector with Cast() + workspace + CrossCoreSetFlag/WaitFlag

// CORRECT: fixpipe Cube-only
using ElementC = half;    // Cube outputs fp16 directly via fixpipe
// No ElementD, no KernelVector, no workspace, no cross-core sync
```

**Detection:** If the DSL has no `tl.scope('vector')` and `DTYPE_C = tl.half`, the lowering should follow the fixpipe path (see the Fixpipe section in SKILL.md).

## int8 Quantized MatMul Pitfalls

### 12. Wrong L1/L0 K Dimension for int8

**Problem:** Using fp16 K dimensions (L1_K=256, L0_K=64) for int8 matmul.

**Impact:** Incorrect tile sizes cause silent data corruption or hardware errors.

**Rule:** int8 elements are 1 byte (vs 2 bytes for fp16), so K dimensions double:
```cpp
// WRONG: fp16 K dimensions
using L1Shape = GemmShape<128, 256, 256>;  // L1_K=256 is for fp16
using L0Shape = GemmShape<128, 256, 64>;   // L0_K=64 is for fp16

// CORRECT: int8 K dimensions (2x fp16)
using L1Shape = GemmShape<128, 256, 512>;  // L1_K=512 for int8
using L0Shape = GemmShape<128, 256, 128>;  // L0_K=128 for int8
```

### 13. Wrong B Layout for Transposed Weight

**Problem:** B is stored as [N, K] in memory, but LayoutB is constructed as `LayoutB(N, K)` instead of `LayoutB(K, N)`.

**Impact:** Matmul reads wrong data — the layout dimensions represent the logical matrix shape (rows, cols), not the storage shape.

**Rule:** When B=[N,K] is stored row-major in memory, the matmul sees it as a (K, N) matrix in ColumnMajor:
```cpp
// WRONG: using storage shape dimensions
using LayoutB = layout::ColumnMajor;
LayoutB layoutB(N, K);  // Wrong! This describes a (N,K) matrix

// CORRECT: using logical matrix dimensions for matmul
using LayoutB = layout::ColumnMajor;
LayoutB layoutB(K, N);  // Correct: (K,N) matrix in column-major = [N,K] storage
```

### 14. InferDataType Propagating int8 to Output

**Problem:** Using `GetInputDataType(0)` in `InferDataType` when input is int8 but output should be fp16.

**Impact:** Framework expects int8 output tensor, causing runtime type mismatch errors.

**Rule:** For mixed-type operators, hardcode the output dtype:
```cpp
// WRONG: propagates int8 input type to output
static ge::graphStatus InferDataType(gert::InferDataTypeContext *context)
{
    context->SetOutputDataType(0, context->GetInputDataType(0));  // Returns DT_INT8!
    return ge::GRAPH_SUCCESS;
}

// CORRECT: hardcode fp16 output
static ge::graphStatus InferDataType(gert::InferDataTypeContext *context)
{
    context->SetOutputDataType(0, ge::DT_FLOAT16);
    return ge::GRAPH_SUCCESS;
}
```

### 15. Output Tensor Dtype from a.options() with int8 Input

**Problem:** In pybind C++ code, using `at::empty({M, N}, a.options())` when `a` is int8. This creates an int8 output tensor instead of fp16.

**Impact:** The output tensor has wrong dtype, causing shape/type mismatch errors during evaluation.

**Rule:** For mixed-type operators, construct explicit TensorOptions:
```cpp
// WRONG: inherits int8 dtype from input
at::Tensor result = at::empty({M, N}, a.options());  // Creates int8 tensor!

// CORRECT: explicit fp16 dtype
at::Tensor result = at::empty({M, N}, at::TensorOptions().dtype(at::kHalf).device(a.device()));
```

### 16. Workspace Size Using Wrong Element Size

**Problem:** Computing workspace size using `sizeof(int8)` (input element size) instead of `sizeof(int32_t)` (accumulation element size).

**Impact:** Workspace is 4x too small, causing out-of-bounds memory access and silent corruption.

**Rule:** int8 matmul accumulates into int32, so workspace must use int32 element size:
```cpp
// WRONG: using input element size
size_t requiredWorkspaceBytes = (size_t)M * (size_t)N * sizeof(int8_t);  // 4x too small!

// CORRECT: using accumulation element size
size_t requiredWorkspaceBytes = (size_t)M * (size_t)N * sizeof(int32_t);
```

### 17. Full M×N Workspace Instead of Double-Buffered L1-Sized Workspace

**Problem:** Allocating `M * N * sizeof(int32_t)` workspace for quant matmul when only `L1_M * L1_N * coreNum * WORKSPACE_STAGES * sizeof(int32_t)` is needed.

**Impact:** For typical shapes (M=4096, N=12288), full M×N workspace = 192 MB. Double-buffered workspace = ~26 MB (for 100 cores). The excess memory causes allocation failures on memory-constrained devices and wastes GM bandwidth.

**Rule:** Use double-buffered workspace when both Cube and Vector process tiles sequentially:
```cpp
// WRONG: full M×N workspace (192 MB for M=4096, N=12288)
size_t requiredWorkspaceBytes = (size_t)M * (size_t)N * sizeof(int32_t);

// CORRECT: double-buffered L1-sized workspace (~26 MB)
constexpr size_t L1_M = 128;
constexpr size_t L1_N = 256;
constexpr size_t WORKSPACE_STAGES = 2;
size_t requiredWorkspaceBytes = L1_M * L1_N * aicCoreNum * WORKSPACE_STAGES * sizeof(int32_t);
```

**When to apply:** Any CV operator where Cube writes tiles to workspace and Vector reads them sequentially. Each core only needs `WORKSPACE_STAGES` slots (ping-pong), not the full output matrix.

### 18. Row-by-Row Epilogue Instead of 2D Tile Processing with Broadcast Ops

**Problem:** Using `DataCopyPad` row-by-row (one DMA per row) and per-row `Mul()`/`Muls()` for the dequant epilogue, instead of `CopyGm2Ub`/`CopyUb2Gm` 2D tile helpers and tile broadcast operations.

**Impact:** For L1_M=128, this means 128 individual DMA calls + 128 vector operations per tile. Tile-based processing uses ~4 DMA calls + ~4 broadcast operations per tile (with EPILOGUE_TILE_M=32). The row-by-row approach under-utilizes DMA bandwidth and vector ALU throughput.

**Rule:** Use tile-based processing with broadcast operations:
```cpp
// WRONG: row-by-row processing (128 DMA + 128 Mul per L1 tile)
for (uint32_t r = 0; r < currM; ++r) {
    DataCopyPad(ubC, gmC[rowOffset], ...);  // 1D DMA per row
    Mul(ubFloat, ubFloat, scaleF32, N);      // per-row Scale multiply
    Muls(ubFloat, ubFloat, perTokenVal, N);  // per-row PerTokenScale multiply
    DataCopyPad(gmD[rowOffset], ubD, ...);   // 1D DMA per row
}

// CORRECT: tile-based processing (4 DMA + 4 broadcast per L1 tile)
for (uint32_t ep = 0; ep < currM; ep += EPILOGUE_TILE_M) {
    copyGmToUbC(ubC, gmC[wsOffset], ubLayout, wsLayout);  // 2D tile DMA
    tileRowBroadMul(ubFloat, ubFloat, scaleF32);           // tile row broadcast
    tileBrcbOneBlk(ptBrcb, ptRaw);                          // Brcb scatter
    tileColBroadMul(ubFloat, ubFloat, ptBrcb);             // tile col broadcast
    copyUbToGmD(gmD[outOffset], ubD, outLayout, ubLayout); // 2D tile DMA
}
```

### 19. Scalar GetValue() Per Row Instead of Batch Loading Scale Vectors

**Problem:** Using `gmPerToken.GetValue(rowId)` to read one scalar from GM per row, then `Muls()` for scalar multiply. This generates 128 individual GM scalar reads per L1_M tile.

**Impact:** Each `GetValue()` is a separate GM read transaction. For L1_M=128 rows, this creates 128 small GM reads with poor memory access patterns (each read fetches a full cache line for a single float). Batch loading reads all values in one DMA transfer.

**Rule:** Batch-load scale vectors, then use tile broadcast operations:
```cpp
// WRONG: scalar GetValue() per row (128 GM reads per tile)
for (uint32_t r = 0; r < currM; ++r) {
    half perTokenHalf = gmPerToken.GetValue(rowId);  // scalar GM read
    float perTokenVal = static_cast<float>(perTokenHalf);
    Muls(ubFloat, ubFloat, perTokenVal, N);           // scalar multiply
}

// CORRECT: batch load + tile broadcast (1 DMA + 2 ops per epilogue tile)
DataCopyPad(ptIn, gmPerToken[rowStart], ExtParams(1, count * sizeof(float), ...));  // batch load
tileBrcbOneBlk(ptBrcb, ptRaw);           // Brcb scatter: (M,1) → (M,blk)
tileColBroadMul(ubFloat, ubFloat, ptBrcb); // tile column broadcast multiply
```

### 20. UB Budget Exceeds Per-Sub-Block Limit (~192KB on Atlas A2)

**Problem:** Allocating too much UB memory for AIV buffers, especially when using double-buffered TQue (depth=2).

**Impact:** Runtime "VEC instruction error: the ub address out of bounds" crash. The TPipe allocates buffers contiguously; later buffers extend past the UB boundary.

**Rule:** On Atlas A2 with 2 sub-blocks per AIV core, each sub-block has ~192KB UB (not 256KB). Calculate total UB budget carefully:
```cpp
// WRONG: assumes 256KB UB per sub-block
constexpr uint32_t UB_N_TILE = 16384;
pipe.InitBuffer(inQueue, 2, UB_N_TILE * sizeof(bf16));  // 64KB
pipe.InitBuffer(fp32Buf, UB_N_TILE * sizeof(float));     // 64KB
pipe.InitBuffer(absBuf, UB_N_TILE * sizeof(float));      // 64KB
// Total ≈ 208KB > 192KB → OOB crash!

// CORRECT: reduce UB_N_TILE to fit within 192KB
constexpr uint32_t UB_N_TILE = 12288;  // Reduced from 16384
pipe.InitBuffer(inQueue, 2, UB_N_TILE * sizeof(bf16));  // 48KB
pipe.InitBuffer(fp32Buf, UB_N_TILE * sizeof(float));     // 48KB
pipe.InitBuffer(absBuf, UB_N_TILE * sizeof(float));      // 48KB
// Total ≈ 157KB < 192KB ✓
```

**Detection:** If you see "VEC instruction error: the ub address out of bounds" in msprof or runtime logs, sum all `pipe.InitBuffer` sizes. If total > 192KB per sub-block, reduce buffer sizes.

### 21. Reducing L1Shape::M Hurts AIC Cube Performance

**Problem:** Reducing L1Shape::M (e.g., from 128 to 64) to increase pipeline overlap between AIC and AIV.

**Impact:** Each BlockMmad call processes fewer rows, increasing per-tile overhead relative to useful work. Cube utilization drops significantly. Measured: L1_M=64 caused 26-30% AIC slowdown on m=6144 cases.

**Rule:** Keep L1Shape::M=128 for bf16 matmul on Atlas A2. The cube unit is optimized for 128-row tiles. For improving AIC/AIV overlap, use AIV-side optimizations (double-buffering, prefetch) instead:
```cpp
// WRONG: reducing tile size for more pipeline stages
using L1Shape = GemmShape<64, 256, 256>;   // More tiles but worse cube utilization
using L0Shape = GemmShape<64, 256, 64>;

// CORRECT: keep optimal cube tile size, optimize AIV instead
using L1Shape = GemmShape<128, 256, 256>;  // Optimal cube utilization
using L0Shape = GemmShape<128, 256, 64>;
// Use inQueue depth=2 + prefetch pattern for AIV DMA/compute overlap
```

---
name: dsl-baseline-generation-cv
disable-model-invocation: true
description: Generate initial AscendDSL code with scope('cube')/scope('vector') structure for CV fused operators. Use after ascend-call-generation-cv creates the CV project scaffold.
---

## What I do

Generate initial AscendDSL code for **Cube+Vector (CV) fused operators** — kernels that combine matrix multiplication (cube) with element-wise or reduction operations (vector). The generated DSL uses `tl.scope('cube')` and `tl.scope('vector')` to separate compute phases, with cross-core synchronization.

## Prerequisite: env.json

Read `output/{op_name}/env.json` before generating cube/vector DSL. Use `soc_version`, `cube_core_cnt`, `vector_core_cnt`, and memory-size fields for hardware budgets. Treat `null` fields as unknown rather than falling back silently.

## Workflow

1. Read input functional PyTorch code `output/{op_name}/{op_name}_functional.py`
2. Read CV DSL knowledge: @references/ascend_dsl_cv.py
3. **Match examples** — find the best reference for each sub-pattern in the operator:

   **Direct match** (operator maps to a single example):

   | Operator pattern | Example pair (`references/input_example/` + `references/output_example/`) |
   |---|---|
   | matmul + activation (GELU, ReLU, etc.) | `matmul_gelu.py` |
   | norm + matmul + scale | `rms_matmul_scale.py` |
   | matmul + bias + activation | `matmul_bias_relu.py` |
   | matmul + add (residual) | `matmul_add.py` |
   | matmul + GLU (SwiGLU/GeGLU/ReGLU) | `matmul_swiglu.py` |
   | matmul + add + normalization (multi-output) | `matmul_add_rmsnorm.py` |
   | FFN (dual matmul) | `ffn_silu.py` |
   | flash attention (Q@K→softmax→S@V) | `flash_attn_basic.py` |
   | conv2d (1x1 pointwise, kH=kW=1, stride=1, pad=0) | `conv2d_1x1.py` |
   | conv2d + bias (general kH×kW) | `conv2d_bias.py` |

   **No direct match** (complex/multi-stage operators like MLA, custom fusions):

   When no single example covers the full operator, use **decompose → match → compose**:
   1. **Decompose**: Run Step 0 (DAG analysis) to break the operator into individual stages (each stage = one Cube or Vector scope)
   2. **Match each stage**: Map each stage to the closest existing example's corresponding scope:
      - Cube stage doing matmul → any example's `scope('cube')` (e.g., from `matmul_gelu.py`)
      - Vector stage doing RMSNorm → `rms_matmul_scale.py`'s vector scope
      - Vector stage doing RoPE → `ascend_dsl_cv.py` §3.6
      - Vector stage doing activation → `matmul_gelu.py`'s vector scope
      - Vector stage doing cast only → Fixpipe pattern or simple `vcast` loop
   3. **Compose**: Chain the matched scopes in DAG order, adding workspace segments and cross-core events at each Cube↔Vector boundary. Use `ascend_dsl_cv.py` §3.1 for multi-scope layout patterns.

   **Example**: MLAPre (4C+4V) decomposes into:
   - C1 (matmul) → match `matmul_gelu.py` cube scope
   - V1 (RMSNorm) → match `rms_matmul_scale.py` vector scope
   - C2 (matmul) → match cube scope
   - V2 (split + RoPE) → match `ascend_dsl_cv.py` §3.6 for RoPE, simple cast loop for split
   - C3 (per-head matmul) → match cube scope + head-major layout rule (§0.2.1)
   - C4 (matmul) → match cube scope
   - V3 (cast) → simple `vcast` loop
   - V4 (RMSNorm + RoPE) → combine `rms_matmul_scale.py` vector scope + §3.6

4. Generate Ascend DSL code
5. Save to `output/{op_name}/{op_name}_dsl.py`
6. Continue to the next step in agent workflow

### Input Explain
- **[module_fn]**: a pure PyTorch functional implementation that contains matrix multiplication fused with other operations
- **[Model Definition]**: a `Model(nn.Module)` calling [module_fn]
- **[Configurations]**: hyper-parameters and input helper functions

### Fixpipe Optimization (Cube-Only Pattern)

When the Vector scope **only** performs `tl.vcast(dst, src)` for fp32→fp16 type conversion and no other computation (no GELU, RMSNorm, reduction, etc.), the NPU fixpipe hardware can perform this cast automatically as part of the Cube output path. In this case, generate a **Cube-only** DSL without any Vector scope.

#### Detection Criteria
- The functional PyTorch code's post-matmul processing is limited to `.half()` / `.to(torch.float16)` type cast
- No activation functions, normalization, or other element-wise operations after matmul

#### DSL Generation Rules for Fixpipe
1. **No `tl.scope('vector')` block** — omit entirely
2. **No `tl.cross_core_set` / `tl.cross_core_wait`** — no cross-core synchronization needed
3. **`DTYPE_C = tl.half`** — Cube output type is fp16 directly (not fp32)
4. **Cube writes to output tensor directly** — `tl.dot(...)` writes to the final output `D`, not a workspace
5. **Host does not allocate workspace** — no `torch.empty(...)` for intermediate buffers

> **Note**: Fixpipe is a conditional optimization. If the Vector scope contains any computation beyond a simple fp32→fp16 cast, use the standard CV dual-scope pattern described below.

---

### Step 0: Data Dependency Analysis (MANDATORY before DSL generation)

Before writing any DSL code, you MUST analyze the functional PyTorch code and construct a data dependency graph. This determines the scope layout, workspace allocation, synchronization, and UB buffer strategy.

#### 0.1 Construct the Data Flow DAG

Classify each operation in [module_fn] by execution unit:

| Operation Type | Execution Unit | Memory Level |
|---|---|---|
| MatMul / GEMM / Linear | **Cube** (AIC) | L0C accumulation |
| Conv2d (1x1, stride=1, pad=0) | **Cube** (AIC) | L0C accumulation (reshape to MatMul) |
| Conv2d (general kH×kW) | **Cube** (AIC) | L0C accumulation (im2col via Load3D + Mmad, use `tl.conv2d_dot()`) |
| Element-wise (Add/Mul/Exp/Sigmoid/ReLU/GELU/SiLU/Cast) | **Vector** (AIV) | UB |
| Reduction (ReduceSum/ReduceMax/Mean/Variance) | **Vector** (AIV) | UB |
| RoPE (rotary position embedding) | **Vector** (AIV) | UB (see `ascend_dsl_cv.py` §3.6) |
| Softmax (= ReduceMax + Sub + Exp + ReduceSum + Div) | **Vector** (AIV) | UB |
| Data movement (GM↔UB) | **Vector MTE** | UB↔GM |

For each operation node, annotate:
- Input tensor source (GM / workspace / UB)
- Output tensor destination (GM / workspace / UB)
- Data type (fp16 / fp32 / bf16 / int8 / int32)

Edge rules:
- If output crosses Cube↔Vector boundary → mark as **"needs workspace in GM"**
- If within same execution unit → data can stay in **UB or L0** (no workspace needed)

#### 0.2 Determine Scope Layout from DAG

From the DAG, determine how many `tl.scope('cube')` and `tl.scope('vector')` blocks are needed and their ordering:

| Fusion Pattern | DAG Structure | Scope Layout |
|---|---|---|
| MatMul + Activation | `[C] MM → ws → [V] Act → GM` | 1C + 1V |
| MatMul + Bias + Activation | `[C] MM → ws → [V] (bias + Act) → GM` | 1C + 1V |
| MatMul + Add (residual) | `[C] MM → ws → [V] (residual + Add) → GM` | 1C + 1V |
| MatMul + SwiGLU | `[C] MM → ws → [V] (split + gate) → GM` | 1C + 1V |
| MatMul + Add + RmsNorm | `[C] MM → ws → [V] (Add + Norm) → GM` | 1C + 1V, multi-output |
| Norm + MatMul + Scale | `[V] Norm → ws; [C] MM → ws; [V] Scale → GM` | 1V + 1C + 1V |
| FFN (MM1→Act→MM2) | `[C]→ws→[V]→ws→[C]→ws→[V]→GM` | 2C + 2V alternating |
| Flash Attention | `[C] Q@K→[V] softmax→[C] P@V→[V] rescale` per KV block | 2C + 2V per iteration |
| Conv2d (1x1, bias-only) | `[C] dot (reshape) → GM` (Fixpipe) | Cube-only |
| Conv2d (general, bias-only) | `[C] conv2d_dot → GM` (ConvBias, Fixpipe) | Cube-only |
| Conv2d + Activation | `[C] conv2d_dot → ws → [V] (bias + Act) → GM` | 1C + 1V |
| MLA Preprocess | See §0.2.1 below | 4C + 4V multi-stage |

##### 0.2.1 MLA Multi-Stage Scope Layout

For MLA-class operators (4+ Cube stages with interleaved Vector processing):

```
Data flow:
  [C1] token_x @ W_DQ → ws_cq_raw (fp32)
  [V1] RMSNorm(ws_cq_raw) → ws_cq (bf16)
  [C2] ws_cq @ W_UQ_QR → ws_qr (fp32)
  [C4] token_x @ W_DKV_KR → ws_dkv (fp32)     ← parallel with C2
  [V2] split(ws_qr) → ws_qc (bf16, head-major) + RoPE(q_r) → out_query_rope
  [C3] ws_qc @ W_UK → ws_qn (fp32, per-head)   ← depends on V2
  [V3] cast(ws_qn) → out_query
  [V4] RMSNorm(ckv) + RoPE(kr) → out_c_kv, out_k_rope
```

**Key layout rule for per-head matmul**: When V2 writes intermediate data (ws_qc) consumed by C3's per-head matmul, use **head-major layout** — head h's M rows are stored contiguously at `[h*M, (h+1)*M)`. This allows C3 to do standard `(M,D) @ (D,Hckv)` GEMM per head without strided access.

#### 0.3 Derive Workspace from DAG

For each edge that crosses Cube↔Vector boundary:
- **One workspace segment** per cross-boundary data transfer
- Size = output shape × sizeof(output_dtype)

Workspace mode selection:
- **Full mode**: `size = M × N × sizeof(dtype)` — default for most operators
- **Streaming double-buffer**: `size = L1_M × L1_N × cores × 2 × sizeof(dtype)` — when full is too large or pipeline overlap needed
- **Multi-segment**: concatenate separate segments — when multiple different-shaped intermediates needed

#### 0.4 Derive Cross-Core Events from DAG

Count the number of Cube↔Vector boundary crossings in the DAG:
- **1 crossing** → 1 event (e.g., matmul_gelu: `matmul_ready_id = 0`)
- **2 crossings** → 2 events (e.g., FFN: `mm1_done`, `act_done`)
- **N crossings** → N events for multi-stage operators (e.g., MLA: 6 events)

Event placement rule:
- **Set**: after producer's last write operation
- **Wait**: before consumer's first read operation

**Critical for multi-core**: `SetBlockDim` must equal `min(tileCountM, aic_core_num)`. Cores with no work must NOT be scheduled, otherwise they skip the matmul loop without firing CrossCoreSetFlag, causing paired AIV cores to deadlock.

#### 0.5 UB Buffer Planning (192KB constraint)

**Critical: UB total is only 192KB (196,608 bytes).**

For simple operators (total buffer need < 192KB):
- Allocate each buffer independently with `tl.alloc_ub()`

For complex operators (multiple stages exceed 192KB):
- **Stage-sequential reuse**: buffers from completed stages are reused by later stages
- **Peak UB = max(peak_stage_1, peak_stage_2, ..., peak_stage_n)** must fit in 176KB (192KB - 16KB system)

---

### Complexity Levels and Generation Strategy

#### Level 1: Simple CV (1 Cube + 1 Vector)

Single MatMul followed by single Vector post-processing. Use existing examples directly.
- **Examples**: matmul_gelu, matmul_relu, matmul_bias_relu, matmul_add
- **Workspace**: 1 segment (M×N×sizeof(fp32))
- **Events**: 1

**Code pattern**: see examples in `references/output_example/matmul_gelu.py` etc.

#### Level 1-Conv: Conv2d (Cube-only or 1 Cube + 1 Vector)

Conv2d operators. Two sub-patterns:

**1x1 Conv (kH=1, kW=1, stride=1, pad=0)**: Equivalent to matmul after reshape.
- Use `tl.dot()` with Fixpipe (Cube-only, no Vector scope).
- Host reshapes input `[N,Cin,H,W]` → `[N*H*W,Cin]`, weight `[Cout,Cin,1,1]` → `[Cin,Cout]`.
- **Example**: `conv2d_1x1.py`

**General Conv (kH>1 or kW>1 or stride>1 or pad>0)**: Use `tl.conv2d_dot()`.
- Maps to Catlass `BlockConv` (im2col via Load3D handled internally).
- If post-processing is bias-only: Cube-only via ConvBias (bias fused in Cube via BT buffer).
- If post-processing includes activation: Cube→workspace→Vector pattern (same as matmul+activation).
- Input format: NC1HWC0 (C0=16 for fp16). Weight format: FracZ (KDC1KHKWN1N0C0).
- **Example**: `conv2d_bias.py`

#### Level 2: CV with Complex Vector (1 Cube + 1 Vector, more complex)

Single MatMul, but Vector does more (split, reduction, multi-output, gate).
- **Examples**: matmul_swiglu, matmul_add_rmsnorm, rms_matmul_scale
- **Workspace**: 1-2 segments
- **Events**: 1

Specific patterns for SwiGLU, RmsNorm, bias+activation: see `references/output_example/` and `ascend_dsl_cv.py` §3.5.

#### Level 3: Multi-Cube CV (2+ Cube stages)

Multiple MatMul operations with Vector processing between them. **MUST draw DAG first (Step 0).**

- **FFN (MM1→Act→MM2)**: 2C + 2V. See `references/output_example/ffn_silu.py`.
  - Workspace: 3 segments. Events: 3.

- **Flash Attention (Q@K→softmax→P@V)**: 2C + 2V per KV block. See `references/output_example/flash_attn_basic.py`.
  - Iterative scope pattern with running max/sum.

- **MLA Preprocess (4C + 4V)**: See §0.2.1 above for DAG and layout rules.
  - Workspace: 6 segments. Events: 6.
  - RoPE implementation: see `ascend_dsl_cv.py` §3.6 (uses `tl.ub_copy` for swap halves + `tl.vmul_scalar` for partial negate).
  - Per-head matmul: use head-major workspace layout.

---

### Generation Requirements

Your task is to generate an **Ascend DSL (CV)** that replicates the computation in [module_fn], optimized for the input shape specified in Configurations.

#### Key Rules

1. **Dual Scope Structure**: Use `tl.scope('cube')` for matrix ops and `tl.scope('vector')` for element-wise/reduction ops.

2. **Layouts**: Define 2D layouts for all global tensors using `tl.make_layout(tl.make_shape(...), tl.make_stride(...))`.

3. **Matrix Compute**: Use `tl.dot(A_ptr, A_layout, B_ptr, B_layout, C_ptr, C_layout, actual_block_shape)` within `tl.scope('cube')`.

4. **Cross-Core Sync**: Use `tl.cross_core_set(event_id)` / `tl.cross_core_wait(event_id)` at each Cube↔Vector boundary.

5. **Workspace**: Host allocates workspace tensors for intermediates that cross Cube↔Vector boundaries.

6. **Tiling in Kernel**: Tiling constants (L1_M, L1_N, etc.) defined inside kernel. Host only passes problem sizes.

7. **Subcore Partitioning**: Vector scope may use `tl.get_num_sub_blocks()` / `tl.get_sub_block_id()` for parallel row processing.

8. **Vector compute patterns**: See `ascend_dsl_cv.py` §3.5 (activations) and §3.6 (RoPE) for standard implementations.

#### Host Function Requirements
- Read input tensor shapes and pass problem sizes into the kernel
- Allocate workspace tensors as needed
- Launch kernel with `kernel_name[core_num](args...)`

#### Kernel Function Requirements
- Define tiling constants at the top
- Define global layouts for all tensors
- Include a task partition comment block explaining core assignment
- Use one outer task loop: `for task in range(aicore_id, total, aicore_num)`
- Place `tl.scope('cube')` and `tl.scope('vector')` inside the task loop

Natural-language comments are mandatory and are part of the DSL.

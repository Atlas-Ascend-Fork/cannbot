# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

ASCEND_DSL_CV_KNOWLEDGE = r'''
### Ascend DSL (CV / Fused-Op) Specification

Ascend DSL is a low-level DSL used to orchestrate computation on Ascend NPUs, which provide
multiple **cube** units and **vector** units. The DSL models SIMD-style programming: you explicitly
manage tiling, on-chip buffers, vector operations, and data movement.

This specification describes how to write Ascend DSL pseudo-code for **CV-style fused kernels**.

Key characteristics:
- The kernel may contain **cube** and/or **vector** execution scopes.
- A kernel may have **multiple stages** inside a scope (multiple loops, multiple copy/compute segments).
- Tiling, layouts, and scheduling are defined in the **kernel**.
- one cube unit is associated with `tl.get_num_sub_blocks()` vector units**.


================================================================================
### 1. PROGRAM STRUCTURE

An Ascend DSL (CV/fused) program consists of:

1) **Host Function (lightweight)**
   - Sets problem sizes (e.g., `M,N,K`)
   - Allocates optional scratch tensors (e.g., **workspace**)
   - Launches the kernel

2) **Kernel Function (main body)**
   - Defines tiling constants
   - Defines global layouts
   - Adds a short task-partition comment at the top (how work is split across cores)
   - Uses manual scheduling and distributes work over cores
   - Uses `tl.scope('cube')` and/or `tl.scope('vector')`
   - Performs load/compute/store with explicit copy blocks
   - Uses cross-core events when a scope produces data consumed by another

--------------------------------------------------------------------------------
#### 1.1 Host Launch Rule

Host must launch kernel with:

    kernel_name[n_cores](args...)

Typical host responsibilities:
- read input tensor shapes and pass problem sizes (e.g., `M,N,K`) into the kernel
- allocate optional scratch tensors (e.g., `workspace`) only if the kernel needs them
- set `n_cores = tl.get_core_num()` — this queries the total block dim for CV fusion (maps to `CalcTschBlockDim(aivNum, aicNum, aivNum)` in AscendC tiling)

================================================================================
### 2. KERNEL REQUIREMENTS (CV/FUSED)

The kernel is responsible for **tiling, scheduling, layout, and synchronization**.

--------------------------------------------------------------------------------
#### 2.1 Tiling & DType Definition (Kernel)

Define tiling constants at the top of the kernel:
- `L1_M`, `L1_N`, `L1_K` (or similar)
- intermediate/output dtypes (e.g., `DTYPE_C = tl.float32`, `DTYPE_D = tl.half`)

--------------------------------------------------------------------------------
#### 2.2 Global Layouts (Kernel)

Define layouts for all global tensors that are accessed via offsets:

Required APIs:
- `tl.make_shape(dim0, dim1, ...)`
- `tl.make_stride(stride0, stride1, ...)`
- `tl.make_layout(shape, stride)`

Typical row-major 2D examples:
- `layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))`
- `layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))`
- `layout_c = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))`

Access rule:
- Use `layout.get_offset(coord=(row, col, ...))` to compute the base offset.

--------------------------------------------------------------------------------
#### 2.3 Task Partition + Manual Schedule (Kernel)

The kernel should describe and implement manual task mapping.

Required at kernel top (comment block):
- Explain the task axis split (for example, split `M` or `B*S` into `block_m` tasks).
- Explain core assignment rule (for example, stride assignment by `aicore_id`).
- Explain what cube/vector do inside one task.

Required scheduling pattern:
- Build task counts manually (example: `tile_count_m = tl.cdiv(M, L1_M)`).
- Use one outer task loop:
    for block_m in range(aicore_id, tile_count_m, aicore_num):
        with tl.scope('cube'):
            ...
        with tl.scope('vector'):
            ...

Guideline:
- When stages can be merged at the same task granularity, place them inside this one outer loop.
- If extra axes are needed (e.g., `block_n`), nest them inside the corresponding scope.

--------------------------------------------------------------------------------
#### 2.4 Scopes: Cube / Vector

Use `tl.scope(scope_name)` to separate phases:

- `with tl.scope('cube'):`:
  - heavy matrix operations (e.g., `tl.dot`)
  - may include one or more stages (multiple loops, multiple compute segments)
  - may read inputs from global memory and/or consume intermediates produced by other scopes (optional)
  - may write intermediate or final results to global memory (optional)
  - uses `tl.cross_core_set(event_id)` / `tl.cross_core_wait(event_id)` when needed

- `with tl.scope('vector'):`:
  - vector compute stages (e.g., normalization, activation, elementwise fusion)
  - may include one or more stages (multiple loops, multiple load/compute/store segments)
  - may read inputs from global memory and/or consume intermediates produced by other scopes (optional)
  - may write intermediate or final results to global memory (optional)
  - uses `tl.cross_core_set(event_id)` / `tl.cross_core_wait(event_id)` when needed

Rules:
- Each scope may contain one or more loops and one or more compute stages.
- UB allocations should typically happen in the scope that uses them (often vector).
- Preferred structure is one fused outer task loop with `scope('cube')` then `scope('vector')`.

--------------------------------------------------------------------------------
#### 2.5 Cross-Core Synchronization

When one scope produces data consumed by another (e.g., via global memory buffers):
- Producer scope must call:
    tl.cross_core_set(event_id)
  after finishing writes for the tile.

- Consumer scope must call:
    tl.cross_core_wait(event_id)
  before reading that tile.

Rules:
- `event_id` must be a small integer constant (or a kernel-local variable).
- The same `event_id` must be used consistently between producer and consumer.
- Set/wait must match the intended producer-consumer ordering per tile loop.

Per-stage sync for workspace double-buffering:
- When using multiple workspace stages (e.g., WORKSPACE_STAGES=2), use separate event IDs per stage.
- Pattern: `flag_aic_store[s]` and `flag_aiv_compute[s]` where `s` is the stage index.
- Cube waits for `flag_aiv_compute[s]` before writing to slot `s` (after pipeline is full).
- Vector waits for `flag_aic_store[s]` before reading from slot `s`.
- After processing, Vector signals `flag_aiv_compute[s]` to release the slot back to Cube.

--------------------------------------------------------------------------------
#### 2.6 UB Allocation (Kernel)

Allowed APIs:
- `tl.alloc_ub(size, dtype=...)`

Rules:
- UB buffers must be explicitly declared before first use.
- UB buffers used for copyin/copyout represent the data being transferred.
- UB allocation must appear **before the main per-tile loops**.
  Do not allocate UB buffers inside the per-tile loop body.

--------------------------------------------------------------------------------
#### 2.7 Copy / Compute / Store Blocks

All kernels must express memory movement and compute explicitly:

Copy-In:
    with tl.copyin():
        tl.load_2d(src_ptr, src_layout, dst_ub, dst_layout)

Compute:
    with tl.compute():
        ... vector ops / dot / casts ...

Copy-Out:
    with tl.copyout():
        tl.store_2d(dst_ptr, dst_layout, src_ub, src_layout)

Rules:
- Global -> UB loads must be inside `tl.copyin()`.
- UB -> global stores must be inside `tl.copyout()`.
- You may use multiple copy/compute blocks inside loops.

--------------------------------------------------------------------------------
#### 2.8 Supported APIs (Complete)

This section enumerates the APIs that are allowed in the DSL. The DSL is descriptive
and should be written with clear structure and short explanatory comments.

----------------------------------------
A) Scheduling / Control / Meta APIs
----------------------------------------
- `tl.program_id()`, `tl.num_programs()`
- `tl.get_num_sub_blocks()`, `tl.get_sub_block_id()`
- `tl.cdiv(a, b)`, `tl.min(a, b)`

Scheduler:
- Manual schedule with arithmetic on loop indices and tile sizes (preferred).
- `tl.cdiv(a, b)`, `tl.min(a, b)`
- `aicore_id = tl.program_id()`, `aicore_num = tl.num_programs()`

Scopes:
- `tl.scope('cube')`, `tl.scope('vector')`

Cross-core events (optional):
- `tl.cross_core_set(event_id)`
- `tl.cross_core_wait(event_id)`

----------------------------------------
B) Layout APIs
----------------------------------------
- `tl.make_shape(d0, d1, ...)`
- `tl.make_stride(s0, s1, ...)`
- `tl.make_layout(shape, stride)`
- `layout.get_offset(coord=(...))`
- `layout.stride(axis)` (used when building derived layouts for copy)

----------------------------------------
C) Memory Movement APIs
----------------------------------------
Copy blocks:
- `with tl.copyin(): ...`
- `with tl.copyout(): ...`

2D transfers:
- `tl.load_2d(src_ptr, src_layout, dst_ub, dst_layout)`
- `tl.store_2d(dst_ptr, dst_layout, src_ub, src_layout)`

1D transfers (for simple vector loads):
- `tl.load(src_ptr + offsets, dst_ub)`
- `tl.store(dst_ptr + offsets, src_ub)`

1D batch vector loading (for scale factor vectors):
- `tl.load_1d(src_ptr, dst_ub, count=N)` — load N contiguous elements from GM to UB
- Use this to batch-load Scale[N] or PerTokenScale[M] vectors instead of scalar `tl.extract_scalar()` per element.
- For quant matmul dequant epilogues: load Scale once per L1 tile, load PerTokenScale once per epilogue sub-tile.

Notes:
- Any global -> UB transfer must appear inside `tl.copyin()`.
- Any UB -> global transfer must appear inside `tl.copyout()`.

----------------------------------------
D) Matrix / Cube Compute APIs
----------------------------------------
Matrix op (GEMM):
- `tl.dot(A_ptr, A_layout, B_ptr, B_layout, C_ptr, C_layout, actual_block_shape)`
  - Writes matrix product into `C_ptr` (often `workspace`).
  - Maps to Catlass `BlockMmad` in lowering.

Convolution op (Conv2d):
- `tl.conv2d_dot(fmap_ptr, fmap_layout, weight_ptr, weight_layout, out_ptr, out_layout, conv_shape, conv_params)`
  - Performs 2D convolution via hardware im2col + matrix multiply (maps to Catlass `BlockConv`).
  - `fmap_ptr`: feature map in GM (NC1HWC0 format, C0=16 for fp16).
  - `weight_ptr`: convolution weights in GM (FracZ format: KDC1KHKWN1N0C0).
  - `out_ptr`: output tensor in GM (NC1HWC0 format) or workspace.
  - `conv_shape`: output tile shape `tl.make_conv_shape(batch, Ho_tile, Wo_tile, Cout_tile)`.
  - `conv_params`: convolution parameters from `tl.make_conv_params(...)`.
  - Hardware Load3D im2col is handled automatically inside BlockConv — no manual im2col needed.
  - Bias can be fused inside conv (passed via conv_params) — no separate Vector scope needed for bias-only.
  - Use `tl.dot()` instead for 1x1 conv (kH=kW=1, stride=1, pad=0) — reshape to matmul is simpler.

- `tl.make_conv_params(H, W, kH, kW, strideH, strideW, padH, padW, Cin, Cout, bias_ptr=None)`
  - Constructs convolution parameter struct.
  - H, W: input spatial dimensions.
  - kH, kW: kernel size.
  - strideH, strideW: stride.
  - padH, padW: zero-padding.
  - Cin, Cout: input/output channels.
  - bias_ptr: optional bias tensor pointer (1D, shape [Cout]).

----------------------------------------
E) Vector Compute APIs (Elementwise / Reduction)
----------------------------------------
Vector compute must be inside `with tl.compute():`.

-------------------------
Group 1: Reduction Ops
-------------------------
API Names:
- `reduce_sum`
- `reduce_max`
- `reduce_min`

Parameters:
- `dst_ub`     : destination buffer
- `src_ub`     : source buffer
- `shared_ub`  : temporary workspace (size == src_ub)

Reduction aliasing rules:
- `shared_ub` is a temporary workspace; its size equals `src_ub`.
- `dst_ub`, `src_ub`, `shared_ub` may be the same buffer.
- But `dst_ub` must **not** alias `src_ub` if `src_ub` values are needed later.

Example:
    tl.reduce_sum(dst_ub, src_ub, shared_ub)

-------------------------
Group 2: Unary Element-wise Ops
-------------------------
API Names:
- `vexp`, `vsqrt`, `vrsqrt`, `vabs`, `vreciprocal`
- `vtanh`, `vsin`, `vln`, `verf`

Parameters:
- `out_ub`
- `src_ub`
- `count` (optional, default = len(src_ub))

Example:
    tl.vexp(out_ub, x_ub, count=len(x_ub))

-------------------------
Group 3: Binary Element-wise Ops (Tensor-Tensor)
-------------------------
API Names:
- `vadd`, `vsub`, `vmul`, `vdiv`, `vmax`, `vmin`

Parameters:
- `dst_ub`
- `src_ub1`
- `src_ub2`
- `count` (optional, default = len(src_ub1))

Example:
    tl.vadd(out_ub, a_ub, b_ub, count=len(a_ub))

-------------------------
Group 4: Binary Element-wise Ops (Tensor-Scalar)
-------------------------
API Names:
- `vadd_scalar`, `vsub_scalar`, `vmul_scalar`
- `vdiv_scalar`, `vmax_scalar`
- `vclamp_max`, `vclamp_min`

Parameters:
- `dst_ub`
- `src_ub`
- `scalar_value`
- `count` (optional, default = len(src_ub))

Example:
    tl.vdiv_scalar(out_ub, x_ub, scalar, count=len(x_ub))

-------------------------
Group 5: Scalar Extraction
-------------------------
API Name:
- `extract_scalar`

Parameters:
- ub buffer or global pointer
- index

Rules:
- Used to convert a single element into a scalar value.
- Scalars may be used in subsequent compute ops.

Examples:
    scalar = tl.extract_scalar(ub, 0)
    scalar = tl.extract_scalar(global_ptr, index)

-------------------------
Group 6: Duplicate (Fill)
-------------------------
API Name:
- `duplicate`

Description:
- Fills a UB buffer with a scalar value.

Parameters:
- `dst_ub`
- `scalar_value`
- `count` (optional, default = len(dst_ub))

Example:
    tl.duplicate(dst_ub, 0.0, count=len(dst_ub))

-------------------------
Group 7: UB Buffer Copy (Offset)
-------------------------
API Name:
- `ub_copy`

Description:
- Copy data between UB buffers with offset support.
  Used for data rearrangement within UB (e.g., swap halves for RoPE,
  split/concat operations on sub-ranges of a buffer).
  Maps to AscendC `DataCopy(dst[dst_offset], src[src_offset], count)`.

Parameters:
- `dst_ub`     : destination UB buffer
- `dst_offset` : start element index in dst_ub (default 0)
- `src_ub`     : source UB buffer
- `src_offset` : start element index in src_ub (default 0)
- `count`      : number of elements to copy

Rules:
- src_ub and dst_ub should be different buffers (no self-aliasing with overlapping ranges).
- Both buffers should be allocated in the same TPosition (both VECCALC recommended).
- If src is in a different TPosition (e.g., VECIN queue), use `tl.vmul_scalar(dst, src, 1.0)`
  or `tl.vadd_scalar(dst, src, 0.0)` as a cross-position copy workaround.

Example (swap halves for RoPE):
    half = Dr // 2
    tl.ub_copy(ub_rot, 0, ub_x, half, half)        # rot[0:half] = x[half:Dr]
    tl.ub_copy(ub_rot, half, ub_x, 0, half)         # rot[half:Dr] = x[0:half]

----------------------------------------
F) Vector Helper Ops (Common in Fusion)
----------------------------------------
- `tl.vaxpy(dst, x, alpha=..., count=...)`
  - Descriptive semantics: update/add `alpha * x` into `dst` (LLM should keep consistent buffer meaning).
- `tl.vcast(dst, src, count=...)`
  - dtype conversion (e.g., fp32 -> fp16).
- `tl.set_scalar(ub, index, value)`
  - Write a scalar value into a UB buffer at the given index.

================================================================================
### General Rules
- DSL is descriptive (pseudo-code style). Use clear sections and short natural-language comments.
- Kernel should explicitly define:
  - tiling constants
  - layouts
  - task partition comment and loop distribution
  - scopes and (optional) cross-core synchronization
- Multiple stages are allowed; keep them clearly separated with comments.

================================================================================
### 3. EXTENDED PATTERNS (Multi-Cube, Multi-Stage)

This section describes patterns for complex CV operators that go beyond simple 1-Cube + 1-Vector.

--------------------------------------------------------------------------------
#### 3.1 Multi-Scope Layout (2+ Cube + 2+ Vector)

For operators like FFN (MatMul1 → Activation → MatMul2) or Flash Attention (Q@K → softmax → P@V):

**Sequential multi-scope within one task loop:**
```python
for block_m in range(aicore_id, tile_count_m, aicore_num):
    with tl.scope('cube'):    # Stage 1: First matmul
        tl.dot(...)
        tl.cross_core_set(event_0)

    with tl.scope('vector'):  # Stage 2: Activation/softmax
        tl.cross_core_wait(event_0)
        # ... compute ...
        tl.cross_core_set(event_1)

    with tl.scope('cube'):    # Stage 3: Second matmul
        tl.cross_core_wait(event_1)
        tl.dot(...)
        tl.cross_core_set(event_2)

    with tl.scope('vector'):  # Stage 4: Output cast/accumulate
        tl.cross_core_wait(event_2)
        # ... compute ...
```

**Iterative multi-scope (Flash Attention KV block loop):**
```python
for block_m in range(aicore_id, tile_count_m, aicore_num):
    for kv_b in range(kv_blocks):
        with tl.scope('cube'):     # Q @ K_b^T
            tl.dot(...)
            tl.cross_core_set(score_ready)
        with tl.scope('vector'):   # online softmax
            tl.cross_core_wait(score_ready)
            # ... softmax with running max/sum ...
            tl.cross_core_set(prob_ready)
        with tl.scope('cube'):     # P @ V_b
            tl.cross_core_wait(prob_ready)
            tl.dot(...)
            tl.cross_core_set(out_ready)
        with tl.scope('vector'):   # accumulate output
            tl.cross_core_wait(out_ready)
            # ... O += partial_out ...
            tl.cross_core_set(update_done)

    # Final normalize after all KV blocks
    with tl.scope('vector'):
        # O = O / running_sum
```

Rules:
- Each scope transition that crosses Cube↔Vector boundary needs its own event_id
- Events are small integer constants, incrementing from 0
- For iterative patterns (Flash Attention), events are reused across KV block iterations

--------------------------------------------------------------------------------
#### 3.2 Multi-Workspace Management

When multiple intermediates cross Cube↔Vector boundaries:

Host allocates separate workspace segments:
```python
workspace_mm1 = torch.empty(M * N1, dtype=torch.float32, device=X.device)  # MM1 output (fp32)
workspace_act = torch.empty(M * N1, dtype=torch.float16, device=X.device)  # Activation output (fp16)
workspace_mm2 = torch.empty(M * N2, dtype=torch.float32, device=X.device)  # MM2 output (fp32)
```

Rules:
- Each Cube→Vector data transfer needs its own workspace segment
- Workspace dtype matches the producer's output dtype (fp32 for matmul accumulator, fp16 for activation)
- For Flash Attention: also allocate running_max(M) and running_sum(M) as workspace

--------------------------------------------------------------------------------
#### 3.3 UB Buffer Reuse (192KB Constraint)

**Critical: Total UB is only 192KB (196,608 bytes).**

For simple operators (peak < 192KB): allocate all buffers independently.

For complex multi-stage operators (peak would exceed 192KB):

**Stage-sequential reuse**: allocate buffers once, reuse across stages.
```python
# These buffers are reused across Stage 2 (activation) and Stage 4 (output cast)
ub_in = tl.alloc_ub(compute_length, dtype=DTYPE_MM)       # fp32 input from workspace
ub_compute = tl.alloc_ub(compute_length, dtype=DTYPE_MM)   # fp32 compute temp
ub_out = tl.alloc_ub(compute_length, dtype=DTYPE_ACT)      # fp16 output

# Stage 2: ub_in = load(workspace_mm1), compute SiLU, ub_out = store(workspace_act)
# Stage 4: ub_in = load(workspace_mm2), compute Cast, ub_out = store(Y)
# Same physical UB, different logical data — safe because stages don't overlap
```

**Double-buffer via offset**: one allocation, two logical views.
```python
ub_buf = tl.alloc_ub(2 * tile_size, dtype=DTYPE)
# ping = ub_buf[0:tile_size], pong = ub_buf[tile_size:2*tile_size]
```

UB budget planning:
- Compute per-stage peak: sum of all simultaneously live buffers
- Take max across all stages: max_peak must fit in 176KB (192KB - 16KB system)
- If exceeded: reduce tile size or add sub-tiling

--------------------------------------------------------------------------------
#### 3.4 Supported Data Types

| DSL Type | AscendC Type | Size | Use Case |
|---|---|---|---|
| `tl.half` | `half` / `float16` | 2 bytes | Input/output, activation result |
| `tl.float32` | `float` | 4 bytes | Matmul accumulator, intermediate compute |
| `tl.bfloat16` | `bfloat16_t` | 2 bytes | Alternative to fp16, better dynamic range |
| `tl.int8` | `int8_t` | 1 byte | Quantized weights/activations |
| `tl.int32` | `int32_t` | 4 bytes | Int8 matmul accumulator |

Rules:
- Matmul accumulator (DTYPE_C) is always wider than inputs (fp32 for fp16 inputs, int32 for int8 inputs)
- L1_K = 256 for fp16, 512 for int8 (2× because int8 is 1 byte vs 2 bytes)
- L0_K = 64 for fp16, 128 for int8 (hardware-determined)

--------------------------------------------------------------------------------
#### 3.5 Common Activation Patterns

**GELU (tanh approximation):**
```python
# y = x / (1 + exp(NEG_SQRT_8_OVER_PI * (x^3 + TANH_FACTOR * x)))
NEG_COEFF = -1.595769121 * 0.044715
TANH_FACTOR = 1.0 / 0.044715
tl.vmul(t, x, x); tl.vmul(t, t, x)       # x^3
tl.vaxpy(t, x, alpha=TANH_FACTOR)          # x^3 + factor*x
tl.vmul_scalar(t, t, scalar_value=NEG_COEFF)
tl.vexp(t, t); tl.vadd_scalar(t, t, 1.0); tl.vdiv(y, x, t)
```

**SiLU (Swish):**
```python
# y = x / (1 + exp(-x))
tl.vmul_scalar(t, x, scalar_value=-1.0)
tl.vexp(t, t)
tl.vadd_scalar(t, t, scalar_value=1.0)
tl.vdiv(y, x, t)
```

**ReLU:**
```python
tl.vclamp_min(y, x, scalar_value=0.0, count=N)
```

**SwiGLU (split + SiLU + multiply):**
```python
# Input: (M, 2*N), Output: (M, N)
# left = input[:, :N], right = input[:, N:]
# output = SiLU(left) * right
# Use UB offset arithmetic to split
tl.vmul_scalar(neg, left, -1.0); tl.vexp(neg, neg)
tl.vadd_scalar(neg, neg, 1.0); tl.vdiv(silu, left, neg)
tl.vmul(output, silu, right)
```

**Online Softmax (for Flash Attention):**
```python
# Per-row, maintained across KV blocks:
new_max = tl.reduce_max(score_row)
running_max = max(old_max, new_max)
rescale = exp(old_max - running_max)
running_sum = running_sum * rescale + sum(exp(score_row - running_max))
prob_row = exp(score_row - running_max)
# Output accumulator rescaling:
O_row = O_row * rescale + prob_row @ V_block_row
# After all KV blocks: O_row = O_row / running_sum
```

--------------------------------------------------------------------------------
#### 3.6 RoPE (Rotary Position Embedding) Pattern

RoPE applies a rotation to pairs of elements using precomputed sin/cos values.

**Mathematical definition:**
```
rotate_half(x) = [-x[d/2:], x[:d/2]]
result = x * cos + rotate_half(x) * sin
```

**DSL implementation** uses `ub_copy` (Group 7) to swap halves, then `vmul_scalar` to negate:
```python
# Inputs:  ub_x (Dr floats), ub_cos (Dr floats), ub_sin (Dr floats)
# Output:  ub_result (Dr floats)
# Temp:    ub_rot (Dr floats), ub_xcos (Dr floats)
half_dr = Dr // 2

# Step 1: Build rotate_half(x) in ub_rot
#   ub_rot = [x[half_dr:Dr], x[0:half_dr]]  (swap halves)
tl.ub_copy(ub_rot, 0, ub_x, half_dr, half_dr)         # rot[:hDr] = x[hDr:]
tl.ub_copy(ub_rot, half_dr, ub_x, 0, half_dr)         # rot[hDr:] = x[:hDr]

# Step 2: Negate first half → rotate_half(x) = [-x[hDr:], x[:hDr]]
tl.vmul_scalar(ub_rot, ub_rot, scalar_value=-1.0, count=half_dr)

# Step 3: x * cos + rotate_half(x) * sin
tl.vmul(ub_xcos, ub_x, ub_cos, count=Dr)              # x * cos
tl.vmul(ub_rot, ub_rot, ub_sin, count=Dr)              # rotate_half(x) * sin
tl.vadd(ub_result, ub_xcos, ub_rot, count=Dr)          # result
```

**Important notes:**
- `ub_x` and `ub_rot` must be separate VECCALC buffers (not the same buffer).
- If `ub_x` is in VECIN (from a queue), first copy to VECCALC via
  `tl.vadd_scalar(ub_x_copy, ub_x, 0.0, count=Dr)`, then use `ub_x_copy` as source.
- `vmul_scalar` with `count=half_dr` may process up to the next hardware-aligned boundary.
  Ensure `ub_rot` has at least `Dr` elements allocated so the tail write does not corrupt other data.
- sin/cos are typically loaded from GM as bf16/fp16, then cast to fp32 before RoPE compute.

**Typical usage in a fused kernel (e.g., MLA Preprocess):**
```python
# Load x from workspace (fp32), sin/cos from GM (bf16 → fp32)
with tl.copyin():
    tl.load(ws_qr[gm_qr_offset + tl.arange(0, Dr)], ub_x)
    tl.load(rope_sin[gm_sin_offset + tl.arange(0, Dr)], ub_sin_bf16)
    tl.load(rope_cos[gm_cos_offset + tl.arange(0, Dr)], ub_cos_bf16)
with tl.compute():
    tl.vcast(ub_sin, ub_sin_bf16, count=Dr)
    tl.vcast(ub_cos, ub_cos_bf16, count=Dr)
    # ... RoPE steps 1-3 above ...
    tl.vcast(ub_out_bf16, ub_result, count=Dr)
with tl.copyout():
    tl.store(out_rope[gm_out_offset + tl.arange(0, Dr)], ub_out_bf16)
```

--------------------------------------------------------------------------------
#### 3.7 Conv2d Pattern

Conv2d on Ascend NPU is implemented as hardware im2col (Load3D) + matrix multiply (Mmad),
abstracted by Catlass `BlockConv`. The DSL uses `tl.conv2d_dot()` to express this.

**Two sub-cases:**

1. **1x1 Conv (kH=1, kW=1, stride=1, pad=0):** Equivalent to matmul. Reshape input
   `[N, Cin, H, W]` → `[N*H*W, Cin]`, weight `[Cout, Cin, 1, 1]` → `[Cin, Cout]`.
   Use standard `tl.dot()` + Fixpipe. No `tl.conv2d_dot()` needed.

2. **General Conv (kH>1 or kW>1 or stride>1 or pad>0):** Use `tl.conv2d_dot()`.
   Data format requirements:
   - Feature map: NC1HWC0 format (C0=16 for fp16, C0=32 for int8)
   - Weight: FracZ format (KDC1KHKWN1N0C0, N0=16)
   - Output: NC1HWC0 format

**GEMM equivalence:**
- M = batch * Ho * Wo (output spatial positions)
- K = Cin * kH * kW (unfolded input channels)
- N = Cout (output channels)
- Ho = (H + 2*padH - kH) / strideH + 1
- Wo = (W + 2*padW - kW) / strideW + 1

**Bias handling:**
- If post-conv processing is ONLY bias addition (no activation), use ConvBias pattern:
  bias is fused into the Cube via `conv_params.bias_ptr`. Output goes directly to GM.
  No Vector scope needed. This is the Cube-only / Fixpipe-like pattern for conv.
- If post-conv processing includes activation (ReLU, GELU, etc.), use Cube+Vector pattern:
  Cube writes to workspace, Vector reads workspace and applies bias + activation.

**DSL example (general conv2d + bias, Cube-only):**
```python
@ascend_kernel
def conv2d_bias_kernel(fmap, weight, bias, output, batch, Cin, H, W, Cout, kH, kW, sH, sW, pH, pW):
    # Tiling constants
    DTYPE_OUT = tl.half

    # Convolution parameters
    conv_params = tl.make_conv_params(
        H=H, W=W, kH=kH, kW=kW,
        strideH=sH, strideW=sW,
        padH=pH, padW=pW,
        Cin=Cin, Cout=Cout,
        bias_ptr=bias
    )

    Ho = (H + 2 * pH - kH) // sH + 1
    Wo = (W + 2 * pW - kW) // sW + 1

    # Layouts (NC1HWC0 for fmap/output, FracZ for weight)
    C0 = 16
    Cin1 = tl.cdiv(Cin, C0)
    Cout1 = tl.cdiv(Cout, C0)
    layout_fmap = tl.make_ndc1hwc0_layout(batch, 1, Cin1, H * W, C0)
    layout_weight = tl.make_fracz_layout(Cin1 * kH * kW, Cout1, C0)
    layout_out = tl.make_ndc1hwc0_layout(batch, 1, Cout1, Ho * Wo, C0)

    # Task partition: split output tiles across cores
    # BlockConv + ConvBias handles tiling, im2col, Mmad, bias, and output internally
    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()

    with tl.scope('cube'):
        conv_shape = tl.make_conv_shape(batch, Ho, Wo, Cout)
        tl.conv2d_dot(
            fmap, layout_fmap,
            weight, layout_weight,
            output, layout_out,
            conv_shape, conv_params
        )

def host_main(fmap, weight, bias, output):
    batch, Cin, H, W = fmap.shape
    Cout = weight.shape[0]
    _, _, kH, kW = weight.shape
    sH, sW = 1, 1
    pH, pW = 1, 1
    core_num = tl.get_core_num()
    conv2d_bias_kernel[core_num](
        fmap, weight, bias, output,
        batch, Cin, H, W, Cout, kH, kW, sH, sW, pH, pW
    )
```

**DSL example (1x1 conv, reshape to matmul + Fixpipe):**
```python
@ascend_kernel
def conv2d_1x1_kernel(A, B, D, M, N, K):
    # 1x1 conv is just matmul: input [N*H*W, Cin] @ weight [Cin, Cout]
    L1_M, L1_N = 128, 256
    DTYPE_C = tl.half  # Fixpipe: output fp16 directly

    layout_a = tl.make_layout(tl.make_shape(M, K), tl.make_stride(K, 1))
    layout_b = tl.make_layout(tl.make_shape(K, N), tl.make_stride(N, 1))
    layout_d = tl.make_layout(tl.make_shape(M, N), tl.make_stride(N, 1))

    tile_count_m = tl.cdiv(M, L1_M)
    tile_count_n = tl.cdiv(N, L1_N)
    total_tasks = tile_count_m * tile_count_n

    aicore_id = tl.program_id()
    aicore_num = tl.num_programs()

    for task_id in range(aicore_id, total_tasks, aicore_num):
        block_m = task_id // tile_count_n
        block_n = task_id % tile_count_n
        actual_m = tl.min(L1_M, M - block_m * L1_M)
        actual_n = tl.min(L1_N, N - block_n * L1_N)

        with tl.scope('cube'):
            actual_block_shape = tl.make_shape(actual_m, actual_n, K)
            coord_a = (block_m * L1_M, 0)
            coord_b = (0, block_n * L1_N)
            coord_d = (block_m * L1_M, block_n * L1_N)
            with tl.compute():
                tl.dot(A[layout_a.get_offset(coord=coord_a)], layout_a,
                       B[layout_b.get_offset(coord=coord_b)], layout_b,
                       D[layout_d.get_offset(coord=coord_d)], layout_d,
                       actual_block_shape)

def host_main(fmap, weight, output):
    N, Cin, H, W = fmap.shape
    Cout = weight.shape[0]
    # Reshape: fmap [N,Cin,H,W] → A [N*H*W, Cin], weight [Cout,Cin,1,1] → B [Cin, Cout]
    M = N * H * W
    K = Cin
    N_out = Cout
    A = fmap.permute(0, 2, 3, 1).reshape(M, K).contiguous()
    B = weight.squeeze(-1).squeeze(-1).t().contiguous()
    D = torch.empty(M, N_out, dtype=torch.float16, device=fmap.device)
    core_num = tl.get_core_num()
    conv2d_1x1_kernel[core_num](A, B, D, M, N_out, K)
    # Reshape output: [M, Cout] → [N, Cout, H, W]
    return D.reshape(N, H, W, Cout).permute(0, 3, 1, 2)
```
'''

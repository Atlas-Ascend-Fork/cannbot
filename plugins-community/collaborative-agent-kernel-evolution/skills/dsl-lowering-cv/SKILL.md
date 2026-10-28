---
name: dsl-lowering-cv
disable-model-invocation: true
description: Lower CV (Cube+Vector) DSL to AscendC via 5 passes, compile each pass, and auto-fix errors using built-in correction examples and Catlass references.
subagent:
  enabled: true
  agent_type: general
  mode: per-pass
  reason: "每个 pass 使用独立 agent 避免上下文膨胀，支持按复杂度分配模型。"
  pass_config:
    tiling_pass:        { model: sonnet, timeout: 300,  max_iterations: 8 }
    kernel_config_pass: { model: sonnet, timeout: 300,  max_iterations: 8 }
    cube_pass:          { model: opus,   timeout: 600,  max_iterations: 12 }
    vector_pass:        { model: opus,   timeout: 600,  max_iterations: 12 }
    entry_pass:         { model: sonnet, timeout: 180,  max_iterations: 5 }
---


## What I do

Translate a CV (Cube+Vector) fused operator DSL into AscendC code through five passes: `tiling_pass`, `kernel_config_pass`, `cube_pass`, `vector_pass`, and `entry_pass`.
The input AscendC code may already include modifications from earlier passes. Apply **only** the transformation described in the current pass.

Read `output/{op_name}/env.json` before choosing Catlass SoC, L0/L1/UB budgets, and AIC/AIV dispatch assumptions; treat `null` fields as unknown.

## Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│  Pass 1   tiling_pass                                               │
│           Host Tiling + Workspace + OpDef                           │
│           → compile → error? → error_correction / retry (≤3x)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  Pass 2   kernel_config_pass                                        │
│           Includes / Types / Constants / MmadDispatchPolicy         │
│           → compile → error? → error_correction / retry (≤3x)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  Pass 3   cube_pass  (KernelCube class — runs on AIC cores)         │
│           Init() + Process() with BlockMmad / Fixpipe               │
│           → compile → error? → error_correction / retry (≤3x)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  Pass 4   vector_pass  (KernelVector class — runs on AIV cores)     │
│           Init() + Process() with vector compute + CopyOut          │
│           → compile → error? → error_correction / retry (≤3x)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  Pass 5   entry_pass                                                │
│           Dispatch entry — ASCEND_IS_AIC ? KernelCube : KernelVector│
│           → compile → error? → error_correction / retry (≤3x)      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  Done     All 5 passes compiled; record patterns in run notes       │
└─────────────────────────────────────────────────────────────────────┘
```

### Sub-Agent Strategy: Per-Pass Dispatch

每个 pass 必须由**独立子 agent** 执行，cake 主 agent 串行调度。

**优势**：
- **上下文隔离**：每个 agent 只看当前代码 + 对应 pass 指引，避免 5 pass 累积导致上下文爆炸
- **错误隔离**：Pass 3 的修复历史不污染 Pass 4 的生成质量
- **模型按需分配**：简单 pass 用 sonnet 节省成本和时间，复杂 pass 用 opus 提高质量

#### 模型分配

| Pass | 模型 | Timeout | 理由 |
|------|------|---------|------|
| tiling_pass | sonnet | 5min | 固定模式，从 DSL host 函数提取维度和 workspace |
| kernel_config_pass | sonnet | 5min | 类型映射 + includes，规则明确 |
| cube_pass | **opus** | 10min | BlockMmad 调用、layout 构造、sync 放置，错误率最高 |
| vector_pass | **opus** | 10min | 复杂计算逻辑（softmax/RmsNorm/SwiGLU），UB 管理 |
| entry_pass | sonnet | 3min | 固定 AIC/AIV dispatch 模板 |

#### 调度协议

cake 主 agent 按 pass 顺序串行调用本 skill，框架根据 frontmatter `pass_config` 自动为每个 pass 分配独立 agent 和模型：

1. cake 主 agent 完成 Pass 0 分析后，依次进入 Pass 1-5
2. 每个 pass 自动启动独立 agent，agent 读取本 SKILL.md 中对应 pass 段落 + reference example 执行生成
3. agent 完成后运行 `build.sh` 编译，失败最多重试 3 次
4. 编译成功 → 自动进入下一 pass；耗尽重试 → 上报 cake 主 agent 决策（升级模型重试或跳过）
5. pass 之间仅通过**文件系统**传递状态——下一个 agent 读取上一个 agent 写入的文件，无需传递上下文

#### 输入/输出契约

| Pass | 输入 | 输出 |
|------|------|------|
| tiling_pass | DSL 文件 + op_desc.json | `op_host/{op_name}_custom_tiling.h` + host .cpp |
| kernel_config_pass | DSL 文件 + tiling.h | `op_kernel/{op_name}_custom.cpp`（headers + types + constants） |
| cube_pass | DSL 文件 + 当前 .cpp | .cpp 追加 KernelCube class |
| vector_pass | DSL 文件 + 当前 .cpp | .cpp 追加 KernelVector class |
| entry_pass | 当前 .cpp（含两个 class） | .cpp 追加 entry function |

### Pass 0: Data Flow Analysis (MANDATORY before lowering)

> **前置分析**：决策逻辑（DAG 构建、scope 推导、事件计数、workspace 模式选择、UB 约束）见 `dsl-baseline-generation-cv` Step 0 §0.1-0.5。本节仅补充 **AscendC 实现层映射**。

#### 0.1 同步 API 映射

每条 Cube↔Vector 边对应一对 sync 调用：
- Cube→Vector: Cube `AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(eventId)` / Vector `AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(eventId)`
- Vector→Cube: Vector `AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(eventId)` / Cube `AscendC::CrossCoreWaitFlag<0x2, PIPE_MTE3>(eventId)`

**事件 ID 映射表**：

| DSL Pattern | Events | AscendC Constants |
|---|---|---|
| 1C + 1V | 1 | `matmulReady = 0` |
| 1V + 1C + 1V | 1 (cube→vector2) | rms_matmul_scale |
| NC + NV alternating | N | FFN: `mm1Done=0, actDone=1, mm2Done=2` |
| Double-buffered workspace | Per-stage arrays | `flagAicStore[s] = BASE + s`, `flagAivCompute[s] = BASE + s` |

**双缓冲 sync 规则**（`WORKSPACE_STAGES = 2`）：
- Cube 维护 `stageUsed` 计数，pipeline 满时等待 Vector
- Cube 主循环后需 **cleanup loop** 排空剩余 stage
- Vector 用 `PIPE_MTE3` signal（最后操作是 MTE3 copy-out）

#### 0.2 Workspace 在 Kernel Init 中的分配

决策树（full / streaming / multi-segment）见 baseline §0.3。AscendC 实现模式：

```
IF single workspace (M*N*sizeof):   → Tiling: M*N*sizeof + sysWorkspaceSize
ELIF streaming (L1_M*L1_N*cores*STAGES): → Tiling: streaming size + sysWorkspaceSize
ELIF multi-segment:                 → Tiling: sum all + sysWorkspaceSize; Init 按 offset 切分
```

```cpp
// Multi-segment Init example
gmWs1.SetGlobalBuffer((__gm__ ElementC*)workspace);
gmWs2.SetGlobalBuffer((__gm__ ElementC*)(workspace + ws1ByteSize));
gmWs3.SetGlobalBuffer((__gm__ ElementD*)(workspace + ws1ByteSize + ws2ByteSize));
```

#### 0.3 UB Buffer 实现策略

UB 约束（192KB，可用 ~176KB）见 baseline §0.5。本节补充 AscendC buffer 类型和 reuse 机制：

**Buffer 类型映射**：`tl.load` → `TQue<VECIN>`，`tl.store` → `TQue<VECOUT>`，中间计算 → `TBuf<VECCALC>`

**Reuse 机制**：

| Mechanism | Code Pattern | When to Use |
|---|---|---|
| **GetWithOffset** | `buf.GetWithOffset<T>(count, byteOffset)` | 同物理 buffer 多逻辑视图（ping-pong） |
| **Stage-sequential reuse** | Stage 2 复用 Stage 1 的 TBuf | 阶段不重叠，数据已消费 |
| **No explicit free** | 不在阶段间调 FreeBuffer | 所有生产代码的模式 |

**Buffer 尺寸公式**：
```
2D tile:       (L1_M / num_sub) × L1_N × sizeof(dtype)
Epilogue tile: EPILOGUE_TILE_M × L1_N × sizeof(dtype)
1D row:        row_len × sizeof(dtype)
Reduction:     compute_length × sizeof(float)
```

**生产算子 UB 预算参考**：

| Operator | Peak UB | Strategy |
|---|---|---|
| matmul_gelu | ~96KB | 3 independent buffers |
| quant_matmul | ~120KB | 8 buffers (data + scales + broadcast) |
| rms_matmul_scale | ~48KB | Stage-sequential reuse |
| FFN | ~64KB/stage | Stage-sequential reuse |
| Flash Attention | ~128KB | GetWithOffset double-buffer |

#### 0.4 Multi-Cube Lowering Strategy

For operators with 2+ `tl.scope('cube')` blocks (FFN, Flash Attention, MLA):

**Option A: Multiple KernelCube methods** (preferred for sequential matmuls)
```cpp
class KernelCube {
    void ProcessMM1() { /* first matmul */ }
    void ProcessMM2() { /* second matmul */ }
};
// Entry calls ProcessMM1() then ProcessMM2() with sync between
```

**Option B: Multiple BlockMmad instances** (preferred for independent matmuls)
```cpp
class KernelCube {
    BlockMmad1 blockMmad1;  // Q @ K^T
    BlockMmad2 blockMmad2;  // P @ V
    void Process() {
        blockMmad1(...);
        CrossCoreSetFlag(bmm1DoneId);
        CrossCoreWaitFlag(softmaxDoneId);
        blockMmad2(...);
        CrossCoreSetFlag(bmm2DoneId);
    }
};
```

**Option C: Single KernelCube with inner loop** (for iterative patterns like Flash Attention)
```cpp
class KernelCube {
    void Process() {
        for (kvBlock = 0; kvBlock < kvBlocks; ++kvBlock) {
            blockMmad1(...);  // Q @ K_b^T
            CrossCoreSetFlag(scoreReadyId);
            CrossCoreWaitFlag(probReadyId);
            blockMmad2(...);  // P_b @ V_b
            CrossCoreSetFlag(outReadyId);
            CrossCoreWaitFlag(updateDoneId);
        }
    }
};
```

1. Read the operator DSL file `output/{op_name}/{op_name}_dsl.py` and the directory created by the previous AscendC project generation step

2. **Perform Pass 0 analysis** (data flow, sync, workspace, UB buffers) as described above

3. Based on the operator DSL file, sequentially execute five transformation passes. After each pass generates AscendC code, invoke the `build.sh` script in the AscendC project to perform compilation. If a compilation error occurs, refer to the repair examples in `references/error_correction/` for guidance.

Select lowering examples based on operator complexity:
   - **Level 1 (1C+1V, per-task scheduling)**: `references/lowering_examples/matmul_gelu/` (element-wise activation), `matmul_bias_relu/` (bias broadcast + ReLU), `matmul_add/` (residual add), `matmul_swiglu/` (split-gate SwiGLU with 2N width)
   - **Level 2 (per-block_m + row reduction)**: `references/lowering_examples/rms_matmul_scale/` (V+C+V pattern), `matmul_add_rmsnorm/` (dual output, two-pass row reduction)
   - **Level 3 (multi-Cube, multi-stage)**: `references/lowering_examples/ffn_silu/` (2C+2V sequential, 3 workspace segments), `flash_attn_basic/` (iterative KV-block loop, 4 events per iteration, online softmax)
   - **Quant**: `references/lowering_examples/quant_matmul/` (int8 with double-buffered workspace)
   - **Conv2d (1x1)**: `references/lowering_examples/conv2d_1x1/` (Fixpipe, reshape to matmul, uses BlockMmad)
   - **Conv2d (general)**: `references/lowering_examples/conv2d_bias/` (ConvBias pattern, uses Catlass BlockConv)

### CV-Specific Requirements

CV operators use **two separate kernel classes** (KernelCube and KernelVector) that run on different core types (AIC and AIV). The entry function dispatches between them. A single workspace buffer in global memory is shared between both.

#### int8 Quantized MatMul

- **Tile shapes**: `L1Shape<128, 256, 512>`, `L0Shape<128, 256, 128>` — K dimensions 2x vs fp16 (1 byte/element)
- **DispatchPolicy**: `MmadAtlasA2Pingpong<false>` (enableUnitFlag=false for int8)
- **Accumulation**: `ElementC = int32_t`, double-buffered streaming workspace
- Complete 5-pass examples: `references/lowering_examples/quant_matmul/`

### CV 通用技巧速查

| 技巧 | 适用场景 | 参考 |
|------|---------|------|
| **流式双缓冲 Workspace** | full workspace 内存过大时，`L1_M × L1_N × cores × 2` | Pass 0 §0.2 streaming 模式 + `quant_matmul/` 示例 |
| **2D Tile Epilogue** | tile-based vector 后处理（`CopyGm2Ub` / `CopyUb2Gm`） | `matmul_gelu/`、`matmul_add/` vector 示例 |
| **Tile Broadcast** | scale/bias 向量广播乘/加 | 见下表 |

**Tile Broadcast 操作**：

| 操作 | 适用场景 | API |
|------|---------|-----|
| Row broadcast multiply | Scale[N] 乘以每行 | `TileRowBroadcastMul` |
| Column broadcast multiply | PerTokenScale[M] 乘以每列 | `TileOneBlkColumnBroadcastMul` |
| Brcb expand | (M,1) 展开为 (M,blk) | `TileBroadcastOneBlk` |
| Bias broadcast add | bias[N] 加到每行 | `for row: Add(dst, bias, N)` |

### Fixpipe 优化（Cube 直出模式）

检测条件见 `dsl-baseline-generation-cv` Fixpipe 章节。当 DSL 无 Vector scope 时，Cube 通过 fix-pipeline 硬件直接输出目标 dtype，跳过 Vector epilogue。

#### Per-Pass Changes for Fixpipe

| Pass | Change |
|------|--------|
| Pass 1 (tiling) | 不调 `GetWorkspaceSizes`，无 workspace。`CalcTschBlockDim(aicCoreNum, aicCoreNum, 0)`（Cube-only）|
| Pass 2 (kernel_config) | `ElementC` = 目标 dtype (half/bfloat16_t)。删除 ElementD/DType/LayoutD、cross-core 常量、epilogue headers |
| Pass 3 (cube) | `gmC` 指向最终输出 `y`，不是 workspace。删除 `CrossCoreSetFlag` |
| Pass 4 (vector) | **跳过** — 不生成 KernelVector |
| Pass 5 (entry) | 只有 `if ASCEND_IS_AIC` 分支，Init 直接接收输出 `y` |

#### Fixpipe kernel_config Example
```cpp
using ElementA = half;
using ElementB = half;
using ElementC = half;  // fixpipe: Cube outputs target dtype directly
// Also valid: using ElementC = bfloat16_t; for bf16 direct output
using LayoutA = layout::RowMajor;
using LayoutB = layout::RowMajor;
using LayoutC = layout::RowMajor;
// No ElementD, LayoutD, DType — no Vector scope
// No cross-core event constants
```

#### Fixpipe Entry Example
```cpp
extern "C" __global__ __aicore__
void op_custom(GM_ADDR x, GM_ADDR w, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling) {
    GET_TILING_DATA(t, tiling);
    if ASCEND_IS_AIC {
        KernelCube opCube;
        opCube.Init(x, w, y, t.M, t.N, t.K);  // y directly, not workspace
        opCube.Process();
    }
    // No ASCEND_IS_AIV branch — no KernelVector
}
```

> **Note**: Fixpipe is conditional. If the DSL contains `tl.scope('vector')`, use the standard 5-pass CV lowering below.

### Conv2d Lowering Strategy

When the DSL uses `tl.conv2d_dot()`, the lowering uses **Catlass `BlockConv`** instead of `BlockMmad`. BlockConv handles Load3D im2col internally — no manual Load3D code needed.

#### Conv2d Detection

- DSL contains `tl.conv2d_dot(...)` → use BlockConv lowering (see `conv2d_bias/` examples)
- DSL contains `tl.dot(...)` with conv2d reshape in host → use standard BlockMmad lowering (see `conv2d_1x1/` examples)

#### BlockConv vs BlockMmad Mapping

| DSL API | Catlass Abstraction | Dispatch Policy | Layout (A) | Layout (B) |
|---|---|---|---|---|
| `tl.dot()` | `BlockMmad` | `MmadAtlasA2Pingpong` | `RowMajor` | `RowMajor`/`ColumnMajor` |
| `tl.conv2d_dot()` | `BlockConv` | `ConvAtlasA2Pingpong` | `NDC1HWC0` | `KDC1KHKWN1N0C0` |

#### Per-Pass Changes for Conv2d (vs standard matmul)

| Pass | Matmul (BlockMmad) | Conv2d (BlockConv) |
|------|--------------------|--------------------|
| Pass 1 (tiling) | M, N, K from 2D shapes | batch, Cin, H, W, Cout, kH, kW, stride, pad, Ho, Wo, Cin1, Cout1 |
| Pass 2 (kernel_config) | `block_mmad.hpp`, `MmadAtlasA2Pingpong`, `GemmShape` | `block_conv.hpp`, `ConvAtlasA2Pingpong`, `ConvFmapL1Shape`, `ConvFilterL1Shape`, `ConvL0Shape`, `ConvCoreShape` |
| Pass 3 (cube) | Manual task loop + `blockMmad(...)` | `ConvKernel::operator()<AscendC::AIC>(params)` (handles task loop internally) |
| Pass 4 (vector) | Standard epilogue | ConvBias: skip (bias in Cube). Conv+Activation: same as matmul epilogue |
| Pass 5 (entry) | AIC + AIV dispatch | ConvBias: AIC-only. Conv+Activation: AIC + AIV dispatch |

#### Conv2d Data Format Requirements

- **Feature map**: NC1HWC0 format. C0=16 for fp16, C0=32 for int8. `Cin1 = ceil(Cin / C0)`.
- **Weight**: FracZ format (KDC1KHKWN1N0C0). `N0=16`, `N1 = ceil(Cout / N0)`.
- **Output**: NC1HWC0 format. `Cout1 = ceil(Cout / C0)`.
- **Bias**: 1D VectorLayout `[Cout]`.
- **Host responsibility**: Convert NCHW input to NC1HWC0, convert weight to FracZ format before kernel launch.

#### Conv2d as Conv3d

Conv2d uses Conv3d infrastructure with depth=1: `Di=1, Kd=1, Do=1, strideD=1, dilationD=1, padHead=0`. The `Conv3dParams` struct handles both 2D and 3D convolution.

#### Conv2d Lowering Examples

- **1x1 Conv (Fixpipe, matmul reshape)**: `references/lowering_examples/conv2d_1x1/` — 5 pass examples
- **General Conv + Bias (ConvBias)**: `references/lowering_examples/conv2d_bias/` — 5 pass examples
- **Reference code**: `catlass-master/examples/24_conv_bias/conv_bias.cpp` for complete BlockConv usage

### Pass 1: `tiling_pass` (Host Tiling + Workspace + OpDef)

"""
Move tiling logic from DSL host function to AscendC host-side tiling code.

#### 1.1 Define a Tiling Struct
Create a tiling data structure with fields for:
- Problem dimensions (M, N, K) extracted from input shapes
- Attributes (e.g., eps) if any

**Key difference from Vector-only**: Do NOT move kernel-internal tiling constants (L1_M, L1_N) to host. These stay in the kernel.

#### 1.2 Compute and Set Tiling Parameters
- Extract dimensions from input shapes via `context->GetInputShape()`
- For multi-dimensional inputs (e.g., [B,S,N,D]), compute derived dimensions (M=B*S, K=N*D)
- Set `context->SetBlockDim()` using the context-aware platform API with `CalcTschBlockDim`:
  ```cpp
  auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
  uint32_t aicCoreNum = ascendcPlatform.GetCoreNumAic();
  uint32_t aivCoreNum = ascendcPlatform.GetCoreNumAiv();
  // For CV fusion (both cube+vector used), sliceNum = aivCoreNum
  context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aivCoreNum, aicCoreNum, aivCoreNum));
  // For fixpipe (cube-only, no Vector scope):
  // context->SetBlockDim(ascendcPlatform.CalcTschBlockDim(aicCoreNum, aicCoreNum, 0));
  ```
  **Note**: `PlatformAscendCManager::GetInstance()` is valid in **Kernel Launch** (direct-call) scenarios without a gert context, and `SetBlockDim(aicCoreNum)` works correctly on 910B2 because AIV cores are grouped with AIC cores in the same block. Using `CalcTschBlockDim` is the CANN-recommended pattern for portability across hardware generations where the AIC/AIV grouping may differ.

#### 1.3 Set Attributes
If DSL uses attributes, extract them via `context->GetAttrs()->GetAttrPointer<T>(index)`.

#### 1.4 Set Workspace Sizes
Compute total workspace based on DSL host allocations:
- If DSL has `workspace = torch.empty(M*N, dtype=torch.float32)` → workspace_bytes = M*N*sizeof(float)
- If DSL has multiple workspaces, sum them: `mm_bytes + inv_bytes + sysWorkspaceSize`
- Always add `ascendcPlatform.GetLibApiWorkSpaceSize()` for system workspace
"""

1.1 Refer to the lowering examples in `references/lowering_examples/` for tiling pass examples.

> ⚠️ **Pass 1 完成后：UB 预算检查（Atlas A2 硬性约束）**
>
> 完成 tiling 参数计算后，验证每个 AIV 子核的所有 InitBuffer 大小之和满足 Atlas A2 UB 上限（每核 192KB）：
> ```
> sum(所有 pipe.InitBuffer 的 size 参数，per AIV 核) ≤ 192 × 1024 字节
> ```
> 常见超限场景：inQueueA(64KB) + inQueueB(64KB) + outQueueD(32KB) + tmpBuf(128KB) = 288KB > 192KB
> 若超限：**自动缩减 L1_N 或 computeLength**，直到满足约束，再继续后续 pass。


### Pass 2: `kernel_config_pass` (Includes/Types/Constants)

"""
Generate the Catlass header includes, type aliases, and constants at the top of the kernel file.

#### 2.1 Generate Includes
Required Catlass headers:
```cpp
#include "kernel_operator.h"
#include "lib/matmul_intf.h"
#include "catlass/arch/arch.hpp"
#include "catlass/catlass.hpp"
#include "catlass/gemm/block/block_mmad.hpp"
#include "catlass/gemm/dispatch_policy.hpp"
#include "catlass/gemm/gemm_type.hpp"
#include "catlass/layout/layout.hpp"
#include "catlass/arch/resource.hpp"
#include "catlass/gemm_coord.hpp"
#include "catlass/matrix_coord.hpp"
```

Additional headers if DSL uses scheduler: `catlass/gemm/block/block_swizzle.hpp`
Additional headers if using 2D copy helpers: `catlass/epilogue/tile/copy_gm_to_ub.hpp`, `catlass/epilogue/tile/copy_ub_to_gm.hpp`

#### 2.2 Define Type Aliases
Map DSL types to Catlass types:
- `ArchTag = Arch::AtlasA2`
- `LayoutA/B/C/D` based on DSL layout strides (RowMajor if stride is (cols, 1))
- `ElementA/B/C/D` based on DSL dtypes
- `L1Shape = GemmShape<L1_M, L1_N, L1_K>` (L1_K defaults to 256 for fp16, 512 for int8)
- `L0Shape = GemmShape<L1_M, L1_N, L0_K>` (L0_K = 64 for fp16, 128 for int8 — hardware-determined)
- `BlockMmad` combining DispatchPolicy + L1Shape + L0Shape + element types

#### 2.3 Select MmadDispatchPolicy

Choose the Mmad DispatchPolicy based on operator type:

**Standard fp16 matmul** (element-wise epilogue like GELU, SiLU, ReLU, bias+add, etc.):
```cpp
constexpr bool enableUnitFlag = true;
using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<enableUnitFlag>;
```

**int8 quant matmul** (Cube→Vector workspace pipeline with dequant epilogue):
```cpp
// enableUnitFlag must be false for int8
using MmadDispatchPolicy = Gemm::MmadAtlasA2Pingpong<false>;
```

Selection summary:
| DispatchPolicy | When to Use |
|---|---|
| `MmadAtlasA2Pingpong<true>` | Standard fp16 matmul + element-wise epilogue |
| `MmadAtlasA2Pingpong<false>` | int8 quant matmul (manual kernel) |
| `MmadAtlasA2Preload<unitFlag, shuffleK>` | Optimized fp16 matmul with preload |
| `MmadAtlasA2PreloadAsyncWithCallback<...>` | Catlass device-level API only (not for manual kernels) |

#### 2.4 Define Constants and Multi-Stage Parameters
- Cross-core event IDs:
  - **Standard CV**: `constexpr uint32_t matmulReady = 0;` (single event)
  - **Quant matmul with workspace double-buffering**: Per-stage flag arrays:
    ```cpp
    constexpr uint32_t WORKSPACE_STAGES = 2;
    constexpr uint32_t FLAG_AIC_STORE_BASE = 0;
    constexpr uint32_t FLAG_AIV_COMPUTE_BASE = 1;
    ```
- Vector-specific tile sizes: `constexpr uint32_t REDUCE_TILE_K = 1024;` (if needed)
- Epilogue tile shape (for quant matmul):
  ```cpp
  constexpr uint32_t EPILOGUE_TILE_M = 32;
  using EpilogueTileShape = MatrixShape<EPILOGUE_TILE_M, L1Shape::N>;
  ```
- Tile broadcast type definitions (for quant matmul dequant):
  ```cpp
  using ComputeType = Gemm::GemmType<float, layout::RowMajor>;
  using TileRowBroadMul = Epilogue::Tile::TileRowBroadcastMul<ArchTag, ComputeType, EpilogueTileShape>;
  using TileBrcbOneBlk = Epilogue::Tile::TileBroadcastOneBlk<ArchTag, ComputeType, EPILOGUE_TILE_M>;
  using TileColBroadMul = Epilogue::Tile::TileOneBlkColumnBroadcastMul<ArchTag, ComputeType, EpilogueTileShape>;
  ```

#### 2.5 Optional: BlockScheduler
Only if DSL uses `tl.make_scheduler(...)`:
```cpp
using BlockScheduler = Gemm::Block::GemmIdentityBlockSwizzle<swizzle_offset, swizzle_direction>;
```
"""

2.1 Refer to the kernel config examples in `references/lowering_examples/` for this pass.

#### Multi-Cube kernel_config Extension
When the DSL has 2+ `tl.scope('cube')` blocks (e.g., FFN, Flash Attention):
- Define **separate type aliases** for each matmul if they differ in element types or shapes:
  ```cpp
  // MatMul1: X @ W1
  using ElementA1 = half; using ElementB1 = half;
  using L1Shape1 = GemmShape<128, 256, 256>;
  using BlockMmad1 = ...;

  // MatMul2: activated @ W2
  using ElementA2 = half; using ElementB2 = half;
  using L1Shape2 = GemmShape<128, 256, 256>;
  using BlockMmad2 = ...;
  ```
- If both matmuls have same types, a single set of type aliases suffices
- Define **separate cross-core event constants** for each stage transition:
  ```cpp
  constexpr uint32_t MM1_DONE = 0;
  constexpr uint32_t ACT_DONE = 1;
  constexpr uint32_t MM2_DONE = 2;
  ```


### Pass 3: `cube_pass` (KernelCube Class)

"""
Implement the `KernelCube` class with `Init()` and `Process()` methods.

#### 3.1 Init()
- Store problem dimensions (M, N, K) as member variables
- Configure `GlobalTensor` for input matrices and workspace
- If using scheduler: initialize `BlockScheduler`
- If using manual scheduling: compute `tile_count_m`, `tile_count_n`

#### 3.2 Process()
- Create `Arch::Resource<ArchTag> resource` and `BlockMmad blockMmad(resource)`
- Construct layout objects: `LayoutA layoutA(M, K)`, etc.
- Main loop: iterate over tiles with stride scheduling
- For each tile: compute offsets, call `blockMmad(...)` with correct arguments
- Signal completion: `AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(eventId)` at correct position

#### 3.3 Member Variables
- `GlobalTensor<ElementA/B/C>` for input matrices and workspace output
- Dimension variables and tile counts
- `BlockScheduler` if used

#### Key Mapping Rules
| DSL | AscendC |
|---|---|
| `tl.dot(A, layoutA, B, layoutB, C, layoutC, shape)` | `blockMmad(gmA[offset], layoutA, gmB[offset], layoutB, gmC[offset], layoutC, shape)` |
| `tl.cross_core_set(id)` | `AscendC::CrossCoreSetFlag<0x2, PIPE_FIX>(id)` |
| `layout.get_offset(coord=(r,c))` | `layout.GetOffset(MatrixCoord{r, c})` |

#### DSL → Sync Event Count Mapping

The number of `CrossCoreSetFlag` calls equals the number of **cross-core dependency edges** in the DSL (i.e., each Cube output that a Vector scope reads). Use this rule to verify event wiring:

| DSL Pattern | AscendC Signal Count |
|---|---|
| 1 `tl.scope('cube')` → 1 `tl.scope('vector')` | 1 `CrossCoreSetFlag` + 1 `CrossCoreWaitFlag` |
| N Cube scopes → same Vector (N sequential deps) | N `SetFlag` (IDs 0..N-1) + N `WaitFlag` |
| Grouped matmul: expert_i Cube scope → expert_i Vector scope | 1 SetFlag per expert group; total = `num_experts` if sequential, or 1 if pipelined with WORKSPACE_STAGES |

> **Rule**: Every workspace write by Cube must have a corresponding `CrossCoreSetFlag` immediately after the `blockMmad` call. Every workspace read by Vector must have a corresponding `CrossCoreWaitFlag` before the data movement. Missing any SetFlag/WaitFlag pair → AIV hangs waiting for data that was never signaled (→ H22).
"""

3.1 Refer to the cube pass examples in `references/lowering_examples/` for this pass.

#### Multi-Cube Process Extension

For 2+ matmul operators, choose implementation pattern per Pass 0 §0.4:
- **Option A (separate methods)**: `ProcessMM1()` / `ProcessMM2()` with sync between — see `references/lowering_examples/ffn_silu/ffn_silu_cube_example.md`
- **Option B (inner loop)**: Single `Process()` with per-iteration sync — see `references/lowering_examples/flash_attn_basic/flash_attn_basic_cube_example.md`

Each `blockMmad(...)` call must be followed by `CrossCoreSetFlag<0x2, PIPE_FIX>(eventId)`. Each workspace read must be preceded by `CrossCoreWaitFlag`.


### Pass 4: `vector_pass` (KernelVector Class)

"""
Implement the `KernelVector` class with `Init()`, `Process()`, and helper methods.

#### 4.1 Init()
- Store dimensions and attributes
- Configure subcore indices: `aicoreIndex = GetBlockIdx() / GetSubBlockNum()`, `subcoreIndex = GetSubBlockIdx()`
- Set up GlobalTensors (including workspace partitioning)
- Initialize pipe buffers:
  - `TQue<VECIN>` for CopyIn data
  - `TQue<VECOUT>` for CopyOut data
  - `TBuf<VECCALC>` for temporary compute buffers

#### 4.2 Process()
- Main loop with stride scheduling (using `aicoreIndex`, not `GetBlockIdx()`)
- Cross-core wait: `AscendC::CrossCoreWaitFlag<0x2, PIPE_FIX>(eventId)`
- Subcore work partitioning and boundary checks
- Call CopyIn/Compute/CopyOut helper methods

#### 4.3 Helper Methods
Implement CopyIn, Compute, CopyOut methods following DSL logic:

| DSL API | AscendC API |
|---|---|
| `tl.vmul(dst, a, b, count=N)` | `AscendC::Mul(dst, a, b, N)` |
| `tl.vadd(dst, a, b, count=N)` | `AscendC::Add(dst, a, b, N)` |
| `tl.vsub(dst, a, b, count=N)` | `AscendC::Sub(dst, a, b, N)` |
| `tl.vdiv(dst, a, b, count=N)` | `AscendC::Div(dst, a, b, N)` |
| `tl.vexp(dst, src, count=N)` | `AscendC::Exp(dst, src, N)` |
| `tl.vsqrt(dst, src, count=N)` | `AscendC::Sqrt(dst, src, N)` |
| `tl.vrsqrt(dst, src, count=N)` | `AscendC::Rsqrt(dst, src, N)` |
| `tl.vtanh(dst, src, count=N)` | `AscendC::Tanh(dst, src, N)` |
| `tl.vadd_scalar(dst, src, v)` | `AscendC::Adds(dst, src, v, N)` |
| `tl.vmul_scalar(dst, src, v)` | `AscendC::Muls(dst, src, v, N)` |
| `tl.vcast(dst, src, count=N)` | `AscendC::Cast(dst, src, RoundMode::CAST_NONE, N)` |
| `tl.vaxpy(dst, x, alpha=a)` | `AscendC::Axpy(dst, x, a, N)` |
| `tl.reduce_sum(dst, src, ws)` | `AscendC::ReduceSum(dst, src, ws, N)` |
| `tl.extract_scalar(ub, 0)` | `ub.GetValue(0)` |
| `tl.duplicate(dst, val, count=N)` | `AscendC::Duplicate(dst, val, N)` |

#### 4.4 Data Movement
For 2D tile copy (from Catlass helpers):
```cpp
using CopyGmToUb = Epilogue::Tile::CopyGm2Ub<ArchTag, CType>;
using CopyUbToGm = Epilogue::Tile::CopyUb2Gm<ArchTag, DType>;
```

For 1D row copy (simpler pattern):
```cpp
AscendC::DataCopyPad(localTensor, gmTensor[offset],
                     AscendC::DataCopyExtParams(1, len * sizeof(T), 0, 0, 0),
                     AscendC::DataCopyPadExtParams<T>(false, 0, 0, 0));
```
"""

4.1 Refer to the vector pass examples in `references/lowering_examples/` for this pass.
4.2 Refer to the existing knowledge of AscendC API in `references/ascend_api/`.

#### Multi-Stage Vector Extension

For operators with multiple Vector stages (FFN, Flash Attention, MLA), use **stage-sequential buffer reuse** — same `TQue`/`TBuf` declared at class level, reused across stages (192KB UB constraint).

| Vector Pattern | Reference Example |
|---|---|
| Stage-sequential buffer reuse (2+ stages) | `references/lowering_examples/ffn_silu/ffn_silu_vector_example.md` |
| Online Softmax (running max/sum across KV blocks) | `references/lowering_examples/flash_attn_basic/flash_attn_basic_vector_example.md` |
| Bias broadcast add (load once, add per row) | `references/lowering_examples/matmul_bias_relu/matmul_bias_relu_vector_example.md` |
| SwiGLU split-gate-multiply | `references/lowering_examples/matmul_swiglu/matmul_swiglu_vector_example.md` |
| RmsNorm row reduction | `references/lowering_examples/rms_matmul_scale/rms_matmul_scale_vector_example.md` |
| Dual output (residual + norm) | `references/lowering_examples/matmul_add_rmsnorm/matmul_add_rmsnorm_vector_example.md` |


### Pass 5: `entry_pass` (Kernel Entry Dispatch)

"""
Generate the `extern "C"` kernel entry function with AIC/AIV dispatch.

#### 5.1 Function Signature
```cpp
extern "C" __global__ __aicore__
void {op_name}_custom(GM_ADDR input1, GM_ADDR input2, ..., GM_ADDR output, GM_ADDR workspace, GM_ADDR tiling)
```

#### 5.2 Tiling Data Load
```cpp
GET_TILING_DATA(t, tiling);
```

#### 5.3 AIC/AIV Dispatch
```cpp
if ASCEND_IS_AIC {
    KernelCube opCube;
    opCube.Init(/* input GM_ADDRs + workspace + tiling scalars */);
    opCube.Process();
} else if ASCEND_IS_AIV {
    KernelVector opVector;
    opVector.Init(/* relevant GM_ADDRs + workspace + tiling scalars + attributes */);
    opVector.Process();
}
```

#### Rules
- Use `ASCEND_IS_AIC` / `ASCEND_IS_AIV` macros (no parentheses)
- KernelCube receives: input tensors, workspace, dimension scalars from tiling
- KernelVector receives: workspace, output tensor (+ optionally input for pre-processing), dimension scalars, attributes
- Parameter order in entry function: inputs → outputs → workspace → tiling
"""

5.1 Refer to the entry pass examples in `references/lowering_examples/` for this pass.

#### Multi-Stage Entry Dispatch

For operators with multiple Cube+Vector stages, entry calls separate Process methods per stage:

```cpp
// FFN: 2 Cube stages + 2 Vector stages, alternating
extern "C" __global__ __aicore__
void ffn_silu_custom(GM_ADDR x, GM_ADDR w1, GM_ADDR w2, GM_ADDR y,
                     GM_ADDR workspace, GM_ADDR tiling) {
    GET_TILING_DATA(t, tiling);
    if ASCEND_IS_AIC {
        KernelCube opCube;
        opCube.Init(x, w1, w2, workspace, t.M, t.N1, t.N2, t.K);
        opCube.ProcessMM1();   // Stage 1: X @ W1 → ws1
        opCube.ProcessMM2();   // Stage 3: ws2 @ W2 → ws3 (waits for ACT_DONE internally)
    } else if ASCEND_IS_AIV {
        KernelVector opVector;
        opVector.Init(workspace, y, t.M, t.N1, t.N2, t.K);
        opVector.ProcessActivation();  // Stage 2: SiLU(ws1) → ws2
        opVector.ProcessOutputCast();  // Stage 4: Cast(ws3) → y
    }
}
```

For iterative patterns (Flash Attention), see `references/lowering_examples/flash_attn_basic/flash_attn_basic_entry_example.md`.

> ⚠️ **Pass 5 完成后：渐进验证协议（强制，满足以下任一条件时）**
>
> **触发条件**：kernel 代码超过 200 行，或 phase 数（Cube phase + Vector phase 对数）> 3
>
> **禁止行为**：直接全量测试。
>
> **强制流程**（Phase 对逐步验证）：
> ```
> Step 1: 仅 Phase 1（第一个 Cube phase）— KernelVector 直接输出 workspace 原始值验证搬运
> Step 2: Phase 1 + Phase 2（第一对 Cube+Vector）— 验证跨核同步与第一段 Vector 计算
> Step 3: 每新增一对 Phase，单独验证一次
> Step 4: 全量验证
> ```
>
> **精度失败快速定位规律**：
> - `heads 0..K 正确，K+1+ 错误` → 循环内 buffer race（TQue 缺 EnQue/DeQue）
> - `所有 head 全错` → barrier 完全缺失或 CrossCore 同步错误
> - `特定输出全错，其他正常` → 辅助数据（gamma/sin/cos）加载无专用队列

6. Continue to the next step in agent workflow


## Note

- Apply **only** the transformation described in each pass.
- Follow the logic strictly as defined in the AscendDSL code. Do **not** introduce extra logic.
- Maintain the original code formatting and structure.
- The AscendC code generated by each pass overwrites the existing files directly in the AscendC project.
- In case of compilation failure, attempt up to **three** rounds of automatic repair per pass.
- Refer to `references/error_correction/` and `references/common_pitfalls.md` for error recovery guidance.
- Provide clear status messages after each pass transformation and after each compilation attempt.
- **OPP 安装缓存注意**：修改 kernel 代码后必须重新安装 OPP 包（`bash install_opp.sh`）。若 OPP `.tar.gz` 包的文件名未变化，部分环境会跳过重装，导致 kernel 仍使用旧版本 `.o` 文件。验证方法：检查安装日志确认文件 hash 变化，或强制删除旧缓存后重安装。

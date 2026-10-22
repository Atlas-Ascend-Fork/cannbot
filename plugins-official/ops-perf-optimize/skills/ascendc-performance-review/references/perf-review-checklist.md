# 静态代码检视检查点索引（性能优化点分析）

status: ready

本文件是 AscendC 性能静态检视（`ascendc-performance-review`）的检查点索引真源；通用与 A5 检查点的知识点内容放在 [`perf-review-knowledge/`](perf-review-knowledge/) 下，每个知识点一个文件。arch22 MatMul/FlashAttention 专项编号归入性能最佳实践库对应算子族的主题分册。检视 Agent 不得自拟检查点。

当前版本范围：通用架构与平台事实、tiling 切分、SIMD-MemBase 数据流、MemBase 矢量计算、RegBase/VF、SIMT、标量与头开销，以及 **arch22 MatMul/FlashAttention 专项检查点**。除已登记的 arch22 MatMul/FA 外，其他 Cube/CV 混合通路仍需目标专项知识，不能从 A5 卡片自动外推。 该静态检查点范围不排除对 Cube/MatMul 的族级分析；融合算子内嵌 MM 仍按 MatMul 族规则分析，不能因本清单缺少 Cube 检查点就推导 AIV 替换。

知识来源与抓取口径：cann-samples@6e6260c8（2026-08-24，全部 dav-3510 实测样例，第一优先证据源）；华为官方《Ascend C 最佳实践》（CANN 商用版 9.0.0，机制类补充，部分收益数字仅 A2 平台）；cann/ops-nn 与 ops-transformer 在库 A5(arch35) 纯 Vector 算子 tiling 源码对照分析（2026-08-27，11 个算子，dav-3510，结构判定为主、收益数字未单独上板的条目标 draft）；A5 UB bank 上板微基准实测（2026-08-27，Ascend950PR_9579，bank_probe：1R1W 无感、2R 错位 32B 约 +2%、16KB 对齐无惩罚，供 PRC-MEM-009）；arch22 MatMul 证据来自 asc-devkit 的 `dav-2201` Matmul 样例，arch22 FA 证据来自 ops-transformer FIA 的 `op_host/op_kernel/arch22` 源码。后两类当前完成源码/样例级验证，未把 A2 收益写成 A3 已上板结论。

## 使用方式

1. 检视 Agent 先读本索引，得到全部检查点 ID 与适用范围；
2. 对适用范围命中当前算子、`status=ready` 的每个检查点，**完整读取**其链接的知识点文件或主题分册后再排查源码；
3. finding 必须引用检查点 ID，证据形态以对应条目的证据要求为准；
4. 对应条目的**误报边界**（含证伪知识）与命中条件同等重要，报出前必须逐条核对；
5. **凡结论依赖 `#if` 架构宏取值的（不限于 PRC-ARCH-001），一律先按 PRC-ARCH-001 的打表命令取证目标 SoC 的宏取值，禁止从宏名反推平台**；未打表就断言某分支在目标平台不生效的，属证据不足，不得报出，也不得作为其它 finding 的前提。
6. **平台参数（核数 / UB / L2）先看代码怎么取的，再谈数值**：按 PRC-ARCH-002 确认 host 是否从平台接口获取、取到的值是否真正参与切分表达式——写死或"取了不用"本身就是 finding。检视时目标平台的真实取值（运行时 `acl.get_soc_name()` / `GetCoreNumAiv()`，或对应 SocVersion 的 ini）写进报告元信息段，**仅用于核对代码算出的数**，不单独构成 finding；同代芯片核数并不唯一（950 有 8/16/56/64/72 五档），样例仓与最佳实践文档里的数字是示意值，不可代入。**环境取不到平台数值时注明"不可得"即可，不得据此标 blocker 或跳过任何检查点**——ARCH-002 / MEM-011 / MEM-012 的命中形态均为结构判定。
7. arch22（A2/A3）目标先完整读取 [arch22 检视适用性矩阵](skill:ascendc-performance-best-practices) `reference/common/arch22/perf_review_applicability.md`，按矩阵加载通用卡片，再加载本索引的 `PRC-MM-*` / `PRC-FA-*`；A5 目标不得加载这七条 arch22 专项卡片。A2 证据不能表述为 A3 已验证，缺少 A3 实测时写明 `A3_not_run`。

## 目录约定

```text
perf-review-knowledge/
├── _template.md              # 知识点文件模板（新增知识点从它复制）
└── <类别>/
    ├── <ID>-<slug>.md        # 知识点：说明 + 错误写法 + 正确写法 + 识别方法
    └── code/                 # 可选：过长或可编译的正反例源码，md 内引用
```

arch22 专项编号依目标库的 MatMul、FlashAttention 族级指南进入对应主题分册；适用性矩阵放在通用 arch22 目录，不复制现有通用卡片。

- `ID` 格式：`PRC-<类别缩写>-<三位序号>`，一经分配不复用；
- 知识点文件自带 `status: draft|ready`，只有 `ready` 条目进入检视；`draft` 表示证据不足（如收益数字来自其他平台未在目标架构验证）。

## 检查点索引

### ARCH——架构与平台事实（前置：决定其余检查点读到哪条分支、代入哪些数）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-ARCH-001 | 架构门控把目标平台关在快路之外 | 多架构共编的 kernel/公共头 | [arch/PRC-ARCH-001](perf-review-knowledge/arch/PRC-ARCH-001-arch-macro-gated-path.md) | ready |
| PRC-ARCH-002 | 平台参数必须从接口获取并真正参与切分 | host/tiling 侧为主；MEM-011/012 的前置 | [arch/PRC-ARCH-002](perf-review-knowledge/arch/PRC-ARCH-002-platform-constant-evidence.md) | ready |

### MEM——访存与数据流（SIMD-MemBase）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-MEM-001 | 共享只读参数循环外预加载 | 通用 | [mem/PRC-MEM-001](perf-review-knowledge/mem/PRC-MEM-001-shared-param-preload.md) | ready |
| PRC-MEM-002 | 行间独立任务多核切分 | 通用 | [mem/PRC-MEM-002](perf-review-knowledge/mem/PRC-MEM-002-multicore-row-split.md) | ready |
| PRC-MEM-003 | DoubleBuffer 使能与时机 | 通用 | [mem/PRC-MEM-003](perf-review-knowledge/mem/PRC-MEM-003-double-buffer.md) | ready |
| PRC-MEM-004 | 缓冲深度 bufferNum 自适应加深 | 通用 | [mem/PRC-MEM-004](perf-review-knowledge/mem/PRC-MEM-004-buffer-depth-adaptive.md) | ready |
| PRC-MEM-005 | 小 DMA 合并为大搬运 | 通用 | [mem/PRC-MEM-005](perf-review-knowledge/mem/PRC-MEM-005-merge-small-dma.md) | ready |
| PRC-MEM-006 | 纯搬运路径 TQueBind 复用 VECIN/VECOUT | 通用 | [mem/PRC-MEM-006](perf-review-knowledge/mem/PRC-MEM-006-tquebind-passthrough.md) | ready |
| PRC-MEM-007 | 时间不重叠操作共享临时 Buffer | 通用 | [mem/PRC-MEM-007](perf-review-knowledge/mem/PRC-MEM-007-shared-temp-buffer.md) | ready |
| PRC-MEM-008 | GM 地址 512B 对齐 | 收益数字仅 A2，dav-3510 待验证 | [mem/PRC-MEM-008](perf-review-knowledge/mem/PRC-MEM-008-gm-512b-align.md) | draft |
| PRC-MEM-009 | UB bank 冲突规避 | 220x 静态判定；dav-3510 口径已对齐且冲突影响已上板量化（大幅弱化，静态判定降级为建议） | [mem/PRC-MEM-009](perf-review-knowledge/mem/PRC-MEM-009-ub-bank-conflict.md) | ready |
| PRC-MEM-010 | 超 L2 容量数据分片 | 通用（容量按平台代入） | [mem/PRC-MEM-010](perf-review-knowledge/mem/PRC-MEM-010-l2-capacity-split.md) | ready |
| PRC-MEM-011 | 核间负载均衡、切分维度与模板选路判据 | 通用；tiling/host 侧为主 | [mem/PRC-MEM-011](perf-review-knowledge/mem/PRC-MEM-011-core-balance-and-split-dim.md) | ready |
| PRC-MEM-012 | UB 切分吃满（ubFactor 建模求解） | 通用；tiling 侧为主 | [mem/PRC-MEM-012](perf-review-knowledge/mem/PRC-MEM-012-ub-factor-solve.md) | ready |
| PRC-MEM-013 | 每核最小负载门限与调度核数收敛 | 通用；tiling/host 侧为主，elementwise 类高发 | [mem/PRC-MEM-013](perf-review-knowledge/mem/PRC-MEM-013-percore-min-load-gate.md) | ready |
| PRC-MEM-014 | 切分因子对齐单位选型与字节/元素口径 | 通用；tiling 侧；性能差值待上板量化 | [mem/PRC-MEM-014](perf-review-knowledge/mem/PRC-MEM-014-align-unit-consistency.md) | draft |
| PRC-MEM-015 | 同步原语选型：队列优先、PIPE_ALL 热路径红线 | 通用；kernel 侧 | [mem/PRC-MEM-015](perf-review-knowledge/mem/PRC-MEM-015-sync-primitive-selection.md) | ready |

### MM——arch22 MatMul（A2/A3 专项）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-MM-001 | MatMul 多级 Ping-Pong 与事件闭环 | arch22 MatMul/BatchMatMul/GroupMatMul；kernel 侧 | [MatMul 流水设计](skill:ascendc-performance-best-practices) `reference/matmul/arch22/pipeline_design.md#prc-mm-001` | ready |
| PRC-MM-002 | 大包搬运、紧迫侧优先与预加载门禁 | arch22 MatMul；kernel/tiling 侧 | [MatMul 流水设计](skill:ascendc-performance-best-practices) `reference/matmul/arch22/pipeline_design.md#prc-mm-002` | ready |
| PRC-MM-003 | 先 M/N 填核、欠并行再 Split-K | arch22 MatMul；tiling/kernel 侧 | [MatMul 复用与切分](skill:ascendc-performance-best-practices) `reference/matmul/arch22/reuse_and_split_design.md#prc-mm-003` | ready |
| PRC-MM-004 | L0/L1 驻留与 L2 分片复用 | arch22 MatMul/BatchMatMul；tiling/kernel 侧 | [MatMul 复用与切分](skill:ascendc-performance-best-practices) `reference/matmul/arch22/reuse_and_split_design.md#prc-mm-004` | ready |

### FA——arch22 FlashAttention（A2/A3 专项）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-FA-001 | S2/M 切分与 workspace 联合求解 | arch22 FlashAttention/FIA；host/tiling 侧 | [FA Tiling 与流水](skill:ascendc-performance-best-practices) `reference/flash_attention/arch22/tiling_pipeline_design.md#prc-fa-001` | ready |
| PRC-FA-002 | 多级 buffer 深度与事件 ID 共同闭合 | arch22 FlashAttention/FIA；kernel 侧 | [FA Tiling 与流水](skill:ascendc-performance-best-practices) `reference/flash_attention/arch22/tiling_pipeline_design.md#prc-fa-002` | ready |
| PRC-FA-003 | 启动与热循环 Scalar 减载 | arch22 FlashAttention/FIA；kernel 侧 | [FA Scalar 与启动开销](skill:ascendc-performance-best-practices) `reference/flash_attention/arch22/scalar_overhead_design.md#prc-fa-003` | ready |

### VEC——MemBase 矢量计算

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-VEC-001 | UB 融合连续矢量计算 | 通用；dav-3510 优先考虑 PRC-VF-001 | [vec/PRC-VEC-001](perf-review-knowledge/vec/PRC-VEC-001-ub-fused-vector-chain.md) | ready |
| PRC-VEC-002 | Counter 模式替代 Normal mask | 支持 Counter 模式的架构 | [vec/PRC-VEC-002](perf-review-knowledge/vec/PRC-VEC-002-counter-mode-mask.md) | ready |
| PRC-VEC-003 | 归约用低延迟指令与二分累加 | 通用；RegBase 版见 PRC-VF-007 | [vec/PRC-VEC-003](perf-review-knowledge/vec/PRC-VEC-003-low-latency-reduce.md) | ready |

### VF——RegBase 寄存器计算（dav-3510 专属，A2/A3 不支持）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-VF-001 | 热计算链 VF 融合（MemBase→RegBase） | dav-3510 | [vf/PRC-VF-001](perf-review-knowledge/vf/PRC-VF-001-hot-chain-vf-fusion.md) | ready |
| PRC-VF-002 | VF 内单发指令与 Membar 最小化 | dav-3510 | [vf/PRC-VF-002](perf-review-knowledge/vf/PRC-VF-002-single-issue-membar-minimize.md) | ready |
| PRC-VF-003 | 按依赖拆分 VF 循环利于双发 | dav-3510 | [vf/PRC-VF-003](perf-review-knowledge/vf/PRC-VF-003-loop-split-dual-issue.md) | ready |
| PRC-VF-004 | 循环展开与 Hardware Loop 条件 | dav-3510 | [vf/PRC-VF-004](perf-review-knowledge/vf/PRC-VF-004-unroll-hwloop.md) | ready |
| PRC-VF-005 | VF 循环内常量外提 | dav-3510 | [vf/PRC-VF-005](perf-review-knowledge/vf/PRC-VF-005-const-hoist.md) | ready |
| PRC-VF-006 | asc_vf_call 屏障语义与跨趟数据可见性 | dav-3510 | [vf/PRC-VF-006](perf-review-knowledge/vf/PRC-VF-006-vf-call-barrier-semantics.md) | ready |
| PRC-VF-007 | 归约结构优化（多累加器/二分折叠） | dav-3510 | [vf/PRC-VF-007](perf-review-knowledge/vf/PRC-VF-007-reduce-multi-acc-binary-fold.md) | ready |
| PRC-VF-008 | broadcast 循环序与最内层长度 | dav-3510 | [vf/PRC-VF-008](perf-review-knowledge/vf/PRC-VF-008-broadcast-loop-order.md) | ready |
| PRC-VF-009 | Reg Load/Store 分布模式选型 | dav-3510 | [vf/PRC-VF-009](perf-review-knowledge/vf/PRC-VF-009-load-store-dist-selection.md) | ready |
| PRC-VF-010 | VF 合法性约束（正确性前置检查，含运行期 if 红线） | dav-3510 | [vf/PRC-VF-010](perf-review-knowledge/vf/PRC-VF-010-vf-legality-constraints.md) | ready |
| PRC-VF-011 | 地址寄存器（AReg）外提与偏移写法 | dav-3510 | [vf/PRC-VF-011](perf-review-knowledge/vf/PRC-VF-011-areg-address-offset.md) | ready |

### SIMT（dav-3510）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-SIMT-001 | 离散访存/分支逻辑选 SIMT 与选路边界 | dav-3510 | [simt/PRC-SIMT-001](perf-review-knowledge/simt/PRC-SIMT-001-simt-selection-boundary.md) | ready |
| PRC-SIMT-002 | 串行扫描改 grid-stride 多线程并行 | dav-3510 | [simt/PRC-SIMT-002](perf-review-knowledge/simt/PRC-SIMT-002-grid-stride-parallel.md) | ready |
| PRC-SIMT-003 | SIMT 写冲突处理（原子加分级归约/分组单写者） | dav-3510 | [simt/PRC-SIMT-003](perf-review-knowledge/simt/PRC-SIMT-003-write-conflict-handling.md) | ready |
| PRC-SIMT-004 | launch_bounds 寄存器分析与 GridDim 扫描 | dav-3510 | [simt/PRC-SIMT-004](perf-review-knowledge/simt/PRC-SIMT-004-launch-bounds-griddim-tuning.md) | ready |
| PRC-SIMT-005 | 二维线程布局与 UintDiv 整数除法优化 | dav-3510 | [simt/PRC-SIMT-005](perf-review-knowledge/simt/PRC-SIMT-005-2d-thread-layout-uintdiv.md) | ready |
| PRC-SIMT-006 | 串行依赖扫描拆无依赖判据并行 | dav-3510 | [simt/PRC-SIMT-006](perf-review-knowledge/simt/PRC-SIMT-006-serial-scan-predicate-split.md) | ready |

### SCA——标量与头开销（机制通用）

| ID | 名称 | 适用范围 | 知识点文件 | status |
|---|---|---|---|---|
| PRC-SCA-001 | icache 预取消除取指断流 | 通用 | [sca/PRC-SCA-001](perf-review-knowledge/sca/PRC-SCA-001-icache-prefetch.md) | ready |
| PRC-SCA-002 | 编译期已知布局用静态 LocalTensor | 通用 | [sca/PRC-SCA-002](perf-review-knowledge/sca/PRC-SCA-002-static-localtensor.md) | ready |
| PRC-SCA-003 | 热路径成员变量局部化 | 通用 | [sca/PRC-SCA-003](perf-review-knowledge/sca/PRC-SCA-003-localize-member-vars.md) | ready |
| PRC-SCA-004 | TilingData 直读与结构瘦身 | 通用 | [sca/PRC-SCA-004](perf-review-knowledge/sca/PRC-SCA-004-tilingdata-direct-read.md) | ready |
| PRC-SCA-005 | 指针链与结构体布局 | 通用 | [sca/PRC-SCA-005](perf-review-knowledge/sca/PRC-SCA-005-pointer-chain-struct-layout.md) | ready |
| PRC-SCA-006 | 循环主尾块分离 | 通用 | [sca/PRC-SCA-006](perf-review-knowledge/sca/PRC-SCA-006-loop-prologue-epilogue-split.md) | ready |
| PRC-SCA-007 | 显式 for 循环替代隐式状态机 | 通用 | [sca/PRC-SCA-007](perf-review-knowledge/sca/PRC-SCA-007-explicit-for-loop.md) | ready |
| PRC-SCA-008 | TPipe 避免在业务类内创建初始化 | 通用 | [sca/PRC-SCA-008](perf-review-knowledge/sca/PRC-SCA-008-tpipe-outside-class.md) | ready |
| PRC-SCA-009 | 缩减 Tensor ShapeInfo 维度 | 通用 | [sca/PRC-SCA-009](perf-review-knowledge/sca/PRC-SCA-009-shrink-shapeinfo-dim.md) | ready |

统计：53 条（ready 51 / draft 2）。

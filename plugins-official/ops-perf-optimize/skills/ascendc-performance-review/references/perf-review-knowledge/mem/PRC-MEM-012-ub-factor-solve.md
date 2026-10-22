---
id: PRC-MEM-012
name: UB 切分吃满（ubFactor 建模求解）
category: MEM
applies_to: 机制通用（各代 AI Core）；tiling 侧为主，kernel 侧看 InitBuffer 与写死容量常量；需先按 PRC-ARCH-002 取证 UB 容量；性能数字来自 dav-3510（rms_norm_quant 单步 1.11x）
status: ready
---

# PRC-MEM-012：UB 切分吃满（ubFactor 建模求解）

## 知识点

`ubFactor`（单轮处理的行数/元素数）决定 DMA 合并度与主循环次数：UB 空着等于每轮少搬几行，DMA 发起次数和随之而来的 scalar 头开销都按比例上升。正确做法是把 UB 按与 ubFactor 的关系拆成固定部分和线性部分，解出最大可行值：

```text
UB_total = fixedSize + ubFactor × linearCoef
```

`fixedSize` 收共享只读参数、归约临时区等与 ubFactor 无关的部分（见 PRC-MEM-001），`linearCoef` 收各输入/输出队列按 ubFactor 线性增长的部分（含缓冲深度倍数，见 PRC-MEM-003/004）。rms_norm_quant 用 `calcMaxUbFactor` 建模后单步 **1.11x**（Task Duration 54.3→49.0 us），`aiv_scalar_ratio` 20.0%→9.4%，SCALAR 指令 **-55.9%**、MTE2 发起次数 **-71.2%**、MTE3 **-72.4%**。

反面是把 ubFactor 或 buffer 总量写成与平台无关的魔数常量：此时 UB 容量一变（换代、换档位）就恒定浪费，且浪费量不会在任何日志里体现。

方程本身对不上 `InitBuffer` 清单时，错法有两个方向：**漏项使解偏大 → 超支越界**，多计使解偏小 → 恒定浪费。两个同源风险形态（均有在库实证）：一是**方程漏项**——某 buffer（常见是标量 scratch、归约临时区这类小块）没进任何一侧，当解出的因子恰好吃满容量时，漏掉的那块就是越界量，且注释常自称"保守估计"掩盖问题；二是**零显式预留 + 公式恰好整除**——预算基数直接用平台容量全额，某些 dtype/shape 组合下分母恰好整除，实配零余量，运行时框架的任何隐含头开销即越界。因此方程求解必须（a）以"预算 = ΣInitBuffer 逐项对账"为唯一口径，（b）显式留出安全余量（量级按平台标定，不给固定字节数）。

## 错误写法

```cpp
// 反例①：按另一代平台的 UB 容量写死缓冲区总量，注释自证
static constexpr int32_t MAXBUFFER = 195584;   // (192 - 1) * 1024 byte
Ppipe->InitBuffer(unitBuf, MAXBUFFER);
// 目标平台 UB = 253952 B 时，恒有 58368 B（23%）闲置，与 shape 无关
```

```cpp
// 反例②：ubFactor 是按 dtype/分支枚举的常量表，与平台 UB、与实际 buffer 组成都无关联
constexpr uint32_t UB_FACTOR_B16 = 12288;
constexpr uint32_t UB_FACTOR_B32 = 10240;
constexpr uint32_t UB_FACTOR_B16_WITH_BETA = 11264;
// 这些常量还同时决定"是否切列"的分支阈值，容量假设错会连带路由错
```

## 正确写法

```cpp
// 正例（rms_norm_quant_story/src/5_ub_utilization.asc 的 calcMaxUbFactor）
int64_t fixedSize  = rAlign * (sizeof(dataType) + sizeof(float)) + BLOCK_BYTES;
int64_t linearCoef = rAlign * (sizeof(dataType) * BUF_NUM + sizeof(outputType) * BUF_NUM)
                   + sizeof(float);
int64_t maxUbFactor = (ubSize - fixedSize) / linearCoef;   // ubSize 由平台接口取
// kernel: DataCopyExtParams.blockCount = ubFactor;  一次 DMA 搬 ubFactor 行
```

## 识别方法

**先判结构，再用数值取证。**

前置：按 PRC-ARCH-002 确认 UB 容量确实从 `GetCoreMemSize(CoreMemType::UB, ...)` 取得，且该值真正流到了 ubFactor 的求解式。若 UB 是写死的、或"取了不用"（ubFactor 实际由魔数表决定），先报 PRC-ARCH-002——那是"数从哪来"的问题，本条谈的是"数怎么用"。

1. **看 ubFactor 的来源形式**（结构判定）：由 `ubSize` 参与的方程解出 → 正确写法确认；来自按 dtype/分支枚举的常量表或单个魔数 → 命中候选。
2. **看 UB 方程是否覆盖全部 buffer**（结构判定）：把 `InitBuffer` 清单逐项归入 `fixedSize`（与 ubFactor 无关）或 `linearCoef`（随 ubFactor 线性增长，含缓冲深度倍数）。有 buffer 两边都没算进去，说明方程解出的"最大值"其实是错的，同样命中——漏项方向决定后果：漏计使解偏大是**超支越界**，多计使解偏小是恒定浪费；归类时同时核对方程是否留有显式预留（零预留且分母可能整除平台容量的，按超支风险报）。
3. **看主循环次数**：单核数据一次装得下、无分块主循环的，不论 UB 占用率多低都不报。
4. **数值只用于取证与排序**：命中后才代入用例集 shape 算实际占用字节与闲置字节，用于写证据和排优先级。**平台 UB 容量不可得时照常出结论**——写死常量与魔数表本身即命中形态，闲置量注明"待代入平台容量后量化"即可，不得因缺数值跳过本条。

kernel 侧另看写死的缓冲总量（`InitBuffer` 的字面量常数），它绕过 host 的平台参数——这类同时命中 PRC-ARCH-002 形态①，两条都要出，本条负责给出闲置量。

误报边界（以下三条均有实测证伪支撑，报出前逐条核对）：

- **与核间均衡冲突时不报本条，改报 PRC-MEM-011**：吃满 UB 会压小分组数，`ceil(分组数/核数)` 的阶跃反而抬高关键路径。实测 `R=8192、coreNum=48` 时吃满 UB 取 `rUbFactor=256` 的关键路径 256，而 `176` 只要 176（**慢 45%**）；该模板改均衡择优后 A5 **-9.1%**。关键路径对 ubFactor 非单调，"越大越好"不成立。
- **瓶颈在搬运时抬 ubFactor 无效**：同一模板把 rUbFactor 从 100 抬到 128/144，性能落在 **2~3% 噪声带内**，真瓶颈在上一阶段的 MTE2 搬运。所以只在"DMA 发起次数或 scalar 占比是候选瓶颈"时报，不能见到 UB 有余量就报。
- **吃满 UB 挤掉双缓冲是反向劣化**：缓冲深度 <2 时不得为抬 ubFactor 牺牲 ping-pong，见 PRC-MEM-004 的优先边界。
- 单核数据量本就一次装得下（无分块主循环）的不报；
- 写死常量但恰等于目标平台真值的不报（见 PRC-ARCH-002 的同名边界）。

## 证据要求

finding 必须给出：

- UB 容量在代码中的来源（按 PRC-ARCH-002：接口调用处的文件:行号，及它流到 ubFactor 求解式的追值链）；
- ubFactor / 缓冲总量来源处的文件:行号与摘录，并说明它是解出来的还是查表来的；
- `InitBuffer` 清单的归类结果（各项归 fixedSize 还是 linearCoef），以及有无遗漏项；
- UB 占用率估算式：各 buffer 与 ubFactor 的关系式、代入具体 shape 后的占用字节与闲置字节；
- 主循环次数量级，以及"DMA 发起次数或 scalar 占比是候选瓶颈"的依据；
- 与 PRC-MEM-011 / PRC-MEM-004 的冲突排除计算。

## 参考

- 在库对照（dav-3510，2026-08-27 源码分析，仅作例证）：optim 类（slot 成本表漏计标量 scratch、双缓冲路径超支的反例）、posembedding 类（零预留且恰好整除吃满的反例）、activation 类（显式预留 + 预算与 InitBuffer 逐字节咬合的正例）。
- cann-samples：`Samples/2_Performance/rms_norm_quant_story/src/4_double_buffer.asc → 5_ub_utilization.asc`（1.11x，`calcMaxUbFactor` 建模）；`Samples/2_Performance/moe_init_routing_story/src/4_ub_utilization.asc`。
- 关联知识点：PRC-MEM-005（合并大搬运，本条是其容量前提）、PRC-MEM-001（fixedSize 的组成）、PRC-MEM-004（缓冲深度优先边界）、PRC-MEM-011（冲突时优先；ubFactor 的求解域应是其形态④合轴归一化后的规范 pattern）、PRC-ARCH-002（UB 容量取证）。

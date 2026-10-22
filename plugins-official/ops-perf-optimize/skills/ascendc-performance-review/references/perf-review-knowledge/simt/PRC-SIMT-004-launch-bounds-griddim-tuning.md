---
id: PRC-SIMT-004
name: launch_bounds 寄存器分析与 GridDim 扫描调优
category: SIMT
applies_to: dav-3510（Ascend 950PR/950DT）kernel 侧；SIMT kernel 的线程数/Block 数配置
status: ready
---

# PRC-SIMT-004：launch_bounds 寄存器分析与 GridDim 扫描调优

## 知识点

SIMT 的 BlockDim（线程数）与 GridDim（Block 数）不是越大越好。线程数上限受寄存器总量约束：线程越多每线程可用寄存器越少，超限即 spill 到栈，访存反噬计算。用编译选项 `--cce-res-usage` 查看每线程寄存器/栈用量，以**零 spill 为界**选 `__launch_bounds__`：simt_histogram 实测 512 线程时 64 reg/线程零溢出，1024 线程达寄存器上限，2048 线程 spill 128B——故定 `__launch_bounds__(512)`。GridDim 则做离散扫描（2/4/8/16/32/64）找拐点：过小喂不满核，过大调度开销反超（该例拐点 32，即 16384 线程、每线程约 15 次 float4 load；64 时反而变慢）。Case 2→3 仅调这两个配置就 258.7→40.5us（**6.4x**）。

调优前先定量验证瓶颈假设：同 story 的 Case 1→2 把读改成 float4 向量化（load 指令 -75%），耗时 255.8→258.7us、total_cycles 不变——**计算 bound 下访存向量化无效**，但这个"无效实验"恰好证明了瓶颈在 Vector 计算侧而非 GM 访存，为后续调配置提供了依据。检视时若建议访存类改动，必须先有"瓶颈确在访存"的证据。

## 错误写法

```cpp
// 反例：默认拉满 1024 线程且不做寄存器分析，GridDim 沿用外部传入值不扫描
// simt_histogram_story/src/1_basic_simt.asc:25,105（cann-samples@6e6260c8）
__global__ void simt_histogram_basic_simt_kernel(...)   // 无 __launch_bounds__
...
simt_histogram_basic_simt_kernel<<<blocks, SIMT_THREADS_PER_BLOCK, 0, stream>>>(  // 1024 线程/Block
    x, min, max, y, totalLength, bins);
```

## 正确写法

```cpp
// 正例：--cce-res-usage 定零 spill 线程数 512，GridDim 扫描定 32
// simt_histogram_story/src/3_advanced_tuning.asc:23-27,137（cann-samples@6e6260c8）
constexpr uint32_t CASE3_THREADS = 512;   // __launch_bounds__ 调优结果（64 reg/线程零溢出）
constexpr uint32_t CASE3_BLOCKS = 32;     // GridDim 扫描拐点（64 时调度开销反超）
__global__ __launch_bounds__(CASE3_THREADS) void simt_histogram_advanced_kernel(...)
...
simt_histogram_advanced_kernel<<<CASE3_BLOCKS, CASE3_THREADS, 0, stream>>>(...);
```

## 识别方法

- 看什么：SIMT kernel 声明处有无 `__launch_bounds__`/`LAUNCH_BOUND`；启动配置是硬编码拉满（1024/2048）还是有调优注释/常量；kernel 体的寄存器压力信号（大量局部变量、深层展开、`float4` 等宽类型）。
- 命中条件：kernel 无 `__launch_bounds__` 且线程数取上限值，同时 kernel 体寄存器压力明显（可要求跑 `--cce-res-usage` 佐证 spill）；或 GridDim 取值无任何扫描/推导依据且明显偏离"每线程有足量工作"的量级。
- 误报边界：①`--cce-res-usage` 显示满线程也零 spill 时，1024/2048 线程本身没错，别仅凭"没写 launch_bounds"报问题；②GridDim 拐点依 shape 而变，静态检视只能报"缺扫描依据"，不能断言某个具体值错；③访存向量化（float4）建议必须先证瓶颈在访存——计算 bound 下该改动无效（上文实测），反之瓶颈在 GM 时它才有意义。

## 证据要求

- 命中处 文件:行号 与摘录（kernel 声明与 `<<< >>>` 启动配置）。
- 寄存器证据：`--cce-res-usage` 输出的每线程寄存器/栈/spill 数值（无法编译时明示"待实测"并降级为建议项）。
- 配置建议必须附验证方式：线程数给零 spill 边界，GridDim 给待扫描的取值序列；不给未实测的"最优值"。

## 参考

- cann-samples：`Samples/2_Performance/simt_histogram_story/src/2_mem_optimized.asc` vs `3_advanced_tuning.asc`（6.4x；float4 证伪实验在 1 vs 2）
- 关联：并行范式 PRC-SIMT-002；选路前提 PRC-SIMT-001（Block≤2048 线程、一 AIV 一 Block 等约束）

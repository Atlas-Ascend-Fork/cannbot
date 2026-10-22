---
id: PRC-MEM-002
name: 行间独立任务多核切分
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel+tiling 侧；行间（或元素间）无依赖的算子直接切行，排序/直方图类需配归并或原子加；性能数字来自 dav-3510（rms_norm_quant 59.8x cannsim；moe_init_routing 28.3x）
status: ready
---

# PRC-MEM-002：行间独立任务多核切分

## 知识点

行间无依赖的算子只用 1 个核等于放弃几十倍的并行算力。按行均分到全部 Vector 核（blockIdx 偏移 + 尾核处理余数），各流水 ratio 不变、总时间近似除以核数。rms_norm_quant 4096 行分 64 核后单步 59.8x（并行效率 93.4%）。行间有全局依赖的阶段也常可改写为"局部+归并"形态：moe_init_routing 的排序改各核局部 VBS + 多核 VMS 归并（轮间 SyncAll），直方图改各核分片统计后 `SetAtomicAdd` 累加到 GM，整体 28.3x（排序分不满核，效率 44%）。

## 错误写法

```cpp
// 反例（摘自 rms_norm_quant_story/src/1_preload_gamma.asc）：
// GM 基址不带 blockIdx 偏移，host 侧 <<<1, ...>>> 只起 1 核
xGm_.SetGlobalBuffer(x);
yGm_.SetGlobalBuffer(y);
for (int64_t loop = 0; loop < tilingData_->a; loop++) { ... }  // 单核跑完全部 a 行
```

## 正确写法

```cpp
// 正例（摘自 rms_norm_quant_story/src/2_multi_core.asc）：blockIdx 偏移 + 尾核
if (blockIdx_ == AscendC::GetBlockNum() - 1) {
    curblockFactor_ = tilingData_->blockTail;
} else {
    curblockFactor_ = tilingData_->blockFactor;
}
xGm_.SetGlobalBuffer(x + blockIdx_ * tilingData_->blockFactor * tilingData_->r);
yGm_.SetGlobalBuffer(y + blockIdx_ * tilingData_->blockFactor * tilingData_->r);
// host: coreNum = ascendcPlatform->GetCoreNumAiv(); blockFactor = CeilDiv(a, coreNum);
```

排序/直方图类参照 `moe_init_routing_story/src/1_multi_core.asc`：局部 `Sort` + 多核归并；直方图 `SetAtomicAdd<int32_t>()` + `DataCopyPad` 累加 + `SetAtomicNone()`。

## 识别方法

在被检视源码中看：

1. kernel 内 `GetBlockIdx()` 是否参与 GM 地址偏移或行范围计算；`SetGlobalBuffer` 基址无 blockIdx 项且循环上界为全量 shape，命中。
2. host/tiling 侧 blockDim 是否为 1 或远小于平台核数（对照 `GetCoreNumAiv()`）；tiling 无 blockFactor/blockTail 类字段是单核实现的旁证。
3. 有全局依赖的阶段（排序/计数）是否整体退化为单核串行——看是否存在"局部结果 + SyncAll/原子加归并"结构。

误报边界：知识点中的"64 核"是 cannsim 按 ini 推导的仿真配置核数，实机核数以 `GetCoreNumAiv()` 运行时值为准，按 PRC-ARCH-002 取证（同代 950 的 `vector_core_cnt` 有 8/16/56/64/72 五种档位），不得把 64 当平台核数写进 finding；数据量小于"每核至少一个基本处理单元"时分核收益有限且核启动头开销占比上升（微秒级小算子），不强报；核间有真依赖且无法改写为归并形态的阶段（如强顺序状态机）不报；已分核但负载不均、切分维度太粗或模板选路判据与填核程度无关的，属 PRC-MEM-011，不属本条。

## 证据要求

finding 必须给出：

- `SetGlobalBuffer`/循环上界处的文件:行号与摘录，证明无 blockIdx 参与；
- 启动核数的证据（host 调用处 blockDim 或 tiling 字段）；
- 行间独立性的判定依据（计算链中无跨行读写），排序/直方图类需说明可行的归并/原子加改写。

## 参考

- cann-samples：`Samples/2_Performance/rms_norm_quant_story/src/1_preload_gamma.asc → 2_multi_core.asc`（59.8x）；`Samples/2_Performance/moe_init_routing_story/src/0_native.asc → 1_multi_core.asc`（28.3x，VBS+VMS/AtomicAdd）。
- 官方核间负载均衡：`atlas_ascendc_best_practices_10_0035`。
- 关联知识点：PRC-MEM-011（分核之后的关键路径是否贴近理想值）、PRC-ARCH-002（核数取证）。

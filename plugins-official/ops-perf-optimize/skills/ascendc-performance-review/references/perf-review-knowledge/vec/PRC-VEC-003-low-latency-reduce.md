---
id: PRC-VEC-003
name: 归约用低延迟指令与二分累加
category: VEC
applies_to: 机制通用（各代 AI Core）；kernel 侧 MemBase；官方数字未标注平台（shape=30000 二分 1.41x、shape=256 混合 1.54x）；二分累加的精度收益在 dav-3510 RegBase 实证（rms_norm_quant Step6）；RegBase/VF 的归约写法见 PRC-VF-007
status: ready
---

# PRC-VEC-003：归约用低延迟指令与二分累加

## 知识点

`WholeReduceSum` 单指令延迟是 `Add` 的 2~5 倍，大数据量下循环调用 WholeReduceSum 让高延迟指令串成关键路径。两种改法：①二分累加——数据递归分半用低延迟 Add 成对折叠，剩余 ≤256B 时一次 WholeReduceSum 收尾（shape=30000：172 vs 242 cycles，1.41x）；②按 shape 选指令组合——如 shape=256 fp32 用"一次 BlockReduceSum + 一次 WholeReduceSum"（8.44 vs 13us，1.54x）。二分折叠同时是精度优化：累加误差从 O(nε) 降到约 O(logn·ε)（pairwise summation），rms_norm_quant Step6 在 dav-3510 上性能持平、纯精度收益，说明该写法可无代价默认采用。

## 错误写法

```cpp
// 反例（依官方文档 10_0031 示例重构）：大数据量循环调用高延迟归约指令
for (int32_t i = 0; i < loops; i++) {   // 每轮一条 WholeReduceSum，延迟 2~5 倍于 Add
    AscendC::WholeReduceSum(tmpLocal[i], srcLocal[i * repeatElems], mask, 1, 1, 1, repStride);
}
AscendC::WholeReduceSum(dstLocal, tmpLocal, loops, 1, 1, 1, repStride);
```

## 正确写法

```cpp
// 正例（依官方文档 10_0031 示例重构）：折半 Add 累加，尾部一次收尾
int32_t curCount = totalCount;
while (curCount > TAIL_COUNT) {          // TAIL_COUNT: 剩余 <=256B 时停
    int32_t half = curCount / 2;
    AscendC::Add(srcLocal, srcLocal, srcLocal[curCount - half], half);  // 前段 += 后 half 个
    curCount -= half;   // 奇数长度时前段比后段多 1 个元素，保留在活跃区，不丢元素
}
AscendC::WholeReduceSum(dstLocal, srcLocal, curCount, 1, 1, 1, repStride);
```

RegBase 版二分折叠（VF 内 `Reg::Add` 成对折叠 + `Reg::Reduce<Reg::ReduceType::SUM>` 收尾）见 `rms_norm_quant_story/src/6_binary_sum.asc` 与 PRC-VF-007。

## 识别方法

在被检视源码中看：

1. 循环内调用 `WholeReduceSum`/`BlockReduceSum` 且循环次数随 shape 增大（归约元素数 ≫ 单 repeat 容量），命中形态①。
2. 单次小 shape 归约（如 256 元素）用多次同种归约指令级联，而非 Block+Whole 混合，命中形态②。
3. 精度敏感算子（norm 类的平方和）中的线性累加链（`acc = acc + x[i]` 或逐段 ReduceSum 再相加）——即使性能持平也可按精度收益报（引 rms Step6）。

误报边界：二分折叠写法必须处理奇数长度（`curCount/2` 直接当新长度会丢中间元素，需按"后半取 floor、前段保留余 1"折叠）——检视他人的二分实现时按此核对，给整改建议时不得给出仅对 2 的幂正确的模板；归约元素数小到一条 WholeReduceSum 直接覆盖（≤单 repeat）时无可优化，不报；max/min 类归约无精度收益维度，仅按延迟收益评估；二分 Add 需要可原位折叠的连续 buffer，源数据不可写且无 tmp 空间时改写成本计入判断；官方数字未标注平台，dav-3510 上引用时注明出处口径；RegBase/VF 代码中的归约不按本条报，转 PRC-VF-007。

## 证据要求

finding 必须给出：

- 归约调用处文件:行号与摘录、归约总元素数与循环次数的推导；
- 指令选择依据：当前写法的归约指令序列 vs 建议组合；
- 精度维度（如适用）：说明输出 dtype 与累加长度 n，线性链误差量级估算。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0031`（低延迟指令优化归约，含二分与混合两方案数据）。
- cann-samples：`Samples/2_Performance/rms_norm_quant_story/src/5_ub_utilization.asc → 6_binary_sum.asc`（二分累加兼提精度，dav-3510）。
- 关联知识点：PRC-VF-007（RegBase 归约：多累加器/二分折叠/MERGING mask 等）。

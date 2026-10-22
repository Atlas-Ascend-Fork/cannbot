---
id: PRC-VEC-002
name: Counter 模式替代 Normal mask
category: VEC
applies_to: 机制通用（支持 Counter 模式的各代 AI Core）；kernel 侧 MemBase 基础 API（0 级接口手写主尾块的场景）；官方数据为流水图定性（Scalar/Vector 双降）
status: ready
---

# PRC-VEC-002：Counter 模式替代 Normal mask

## 知识点

Normal 模式下调用 0 级向量接口要手动算主块 repeatTimes、单独处理尾块并反复 `SetVectorMask` 设置逐 bit 掩码——这些主尾块判断、mask 拼装全是 Scalar 指令，随循环放大，且尾块单独一次调用打断 Vector 连发。Counter 模式（`SetMaskCount()` + `SetVectorMask<T, MaskMode::COUNTER>(总元素数)`）按总元素数计数，硬件自动处理不满一个 repeat 的尾部，repeatTimes 固定填 1，主尾块逻辑整段消失。官方 0030 流水图显示 Scalar 与 Vector 执行时间双降。

## 错误写法

```cpp
// 反例（依官方文档 10_0030 示例重构）：手动主尾块 + 反复设逐 bit mask
AscendC::SetMaskNorm();
uint64_t mask[2] = {UINT64_MAX, UINT64_MAX};
AscendC::SetVectorMask<half>(mask[1], mask[0]);
Add(dst, src0, src1, MASK_PLACEHOLDER, repeatTimes, params);   // 主块
if (tailCount > 0) {   // 尾块单独算 mask；half 尾块最多 127 元素，高低 64bit 两段都要拼
    uint64_t tailMask[2] = {
        tailCount >= 64 ? UINT64_MAX : (1ULL << tailCount) - 1,
        tailCount >= 64 ? (1ULL << (tailCount - 64)) - 1 : 0};
    AscendC::SetVectorMask<half>(tailMask[1], tailMask[0]);
    Add(dstTail, src0Tail, src1Tail, MASK_PLACEHOLDER, 1, params);
}
```

## 正确写法

```cpp
// 正例（依官方文档 10_0030 示例重构）：按总数计数，无主尾块分离
AscendC::SetMaskCount();
AscendC::SetVectorMask<half, AscendC::MaskMode::COUNTER>(totalCount);
Add(dst, src0, src1, MASK_PLACEHOLDER, 1, params);   // repeatTimes 固定 1
AscendC::SetMaskNorm();                              // 用完恢复默认模式
```

## 识别方法

在被检视源码中看：

1. 0 级向量接口调用点周边：出现"主块循环 + 尾块 if 分支"结构，且尾块分支内重新计算/设置 mask（`SetVectorMask` 逐 bit 形式、`(1ULL << n) - 1` 拼掩码），命中。
2. 循环体内反复调用 `SetVectorMask`（每轮元素数不同而重设）——Counter 模式一次设置即可覆盖，命中。
3. 只针对手写 0 级接口：2 级接口（直接传 count 的 `Add(dst,src0,src1,count)`）内部已处理主尾块，不存在本问题。

误报边界：使用 2 级/高阶接口的代码不报；算法上确需逐 repeat 不同 mask 的场景（如 mask 本身是数据依赖的 select 掩码）不适用 Counter 模式，不报；Counter 模式设置后未恢复 Normal 会影响后续依赖 Normal 语义的调用——检视改法时要求配对恢复，但"未用 Counter"本身按本条报；主尾块只执行一次（非循环内）时 Scalar 开销可忽略，降级提示。

## 证据要求

finding 必须给出：

- 主尾块分离与 mask 拼装处的文件:行号与摘录；
- 该结构的执行频率（在几层循环内）；
- 排除依据：确认 mask 无数据依赖、接口为 0 级形式（带 repeatTimes/mask 参数）。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0030`（Vector 算子灵活运用 Counter 模式）。
- 关联知识点：dav-3510 RegBase 下对应的尾块手段是 `UpdateMask`/MaskReg（见 PRC-VF 系列），不走本条。

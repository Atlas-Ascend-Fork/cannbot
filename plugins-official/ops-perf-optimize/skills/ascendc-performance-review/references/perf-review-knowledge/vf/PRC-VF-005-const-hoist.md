---
id: PRC-VF-005
name: VF 循环内常量外提
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；VF 内循环使用标量常量的代码
status: ready
---

# PRC-VF-005：VF 循环内常量外提

## 知识点

VF 循环体内用 `Muls/Adds` 这类"向量×标量"指令时，标量常量每轮都要走标量通路参与发射（体现在 aiv_scalar_time）；把不变常量在循环外一次 `Reg::Duplicate` 进 RegTensor，循环内改用纯向量版 `Mul/Add`，标量开销只付一次。配套纪律：外提后循环体内地址必须保持 `base + i * step` 的简单线性形式——引入循环外递增指针或复杂地址表达式会破坏 Hardware Loop 识别与 unroll（PRC-VF-004），得不偿失。注意收益权衡：每个外提常量占一个 RegTensor，与展开份数共同消耗寄存器预算。

## 错误写法

```cpp
// 反例：COEFF_C/D/E 三个常量每轮经 Adds/Muls 标量通路重复参与
// 来源：cann-samples@6e6260c8 2_Performance/gelu_eltwise_regbase_story/src/3_unroll.asc:50-60
#pragma unroll 6
for (uint16_t i = 0; i < loopNum; ++i) {
    mask = AscendC::Reg::UpdateMask<float>(nElt);
    AscendC::Reg::LoadAlign(yReg, yAddr + i * oneRepeatSize);
    AscendC::Reg::Adds(yReg, yReg, COEFF_C, mask);   // 标量常量每轮参与
    AscendC::Reg::Mul(yReg, yReg, yReg, mask);
    AscendC::Reg::Muls(yReg, yReg, COEFF_D, mask);   // 同上
    AscendC::Reg::Adds(yReg, yReg, COEFF_E, mask);   // 同上
    // ...
}
```

## 正确写法

```cpp
// 正例：循环外一次 Duplicate，循环内改纯向量 Add/Mul；地址仍是 base + i*step
// 来源：同目录 4_scalar_tuning.asc:36-66
mask = AscendC::Reg::CreateMask<float>();
AscendC::Reg::Duplicate(cReg, COEFF_C, mask);
AscendC::Reg::Duplicate(dReg, COEFF_D, mask);
AscendC::Reg::Duplicate(eReg, COEFF_E, mask);
#pragma unroll 6
for (uint16_t i = 0; i < loopNum; ++i) {
    mask = AscendC::Reg::UpdateMask<float>(nElt);
    AscendC::Reg::LoadAlign(yReg, yAddr + i * oneRepeatSize);
    AscendC::Reg::Add(yReg, yReg, cReg, mask);
    AscendC::Reg::Mul(yReg, yReg, yReg, mask);
    AscendC::Reg::Mul(yReg, yReg, dReg, mask);
    AscendC::Reg::Add(yReg, yReg, eReg, mask);
    // ...
}
```

## 识别方法

- 看什么：VF 热循环体内的 `Muls/Adds/Duplicate` 等携带标量立即数/标量变量的指令；该标量在循环内是否不变。
- 命中条件：同一不变标量在循环体内被 ≥2 条指令使用，或单条使用但循环次数大且已确认 scalar 侧是瓶颈（aiv_scalar_time 占比高）。
- 误报边界：①每轮变化的标量（如按行读入的系数）不能外提；②寄存器已紧张（大展开份数 + 多 RegTensor）时外提可能触发 spill，需连同预算一起评估；③注意 4_scalar_tuning.asc 中 `Muls(yReg, yReg, COEFF_A, mask)` 这类只出现一次且不在最热段的常量并未全部外提——外提所有常量不是目标，标量瓶颈才是；④外提建议若要求改变地址形式（如指针自增替代 base+i*step），反而破坏 HWLoop/unroll，属于错误建议。

## 证据要求

- 命中循环的文件:行号与摘录，列出可外提的常量及其使用次数。
- 给出外提后新增 RegTensor 数量与当前寄存器占用的估算。
- 有 profiling 时给 aiv_scalar_time 前后对比；无则注明为结构级判断。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/gelu_eltwise_regbase_story/src/3_unroll.asc vs 4_scalar_tuning.asc`
- 关联：PRC-VF-004（地址形式与 HWLoop）、PRC-VF-008（broadcast 场景的寄存器复用是另一种"外提"）

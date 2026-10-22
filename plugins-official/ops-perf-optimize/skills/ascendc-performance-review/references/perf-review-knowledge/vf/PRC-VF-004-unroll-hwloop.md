---
id: PRC-VF-004
name: 循环展开与 Hardware Loop 条件
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；VF 内循环
status: ready
---

# PRC-VF-004：循环展开与 Hardware Loop 条件

## 知识点

`#pragma unroll N` 让一次迭代产出多组无依赖指令供双发配对，前提是循环能被编译器识别为 Hardware Loop：迭代变量 `uint16_t`、从 0 起步、步长 1、体内无运行期 if/break/continue、嵌套 ≤4 层；不满足时存在退化为 Software Loop 的风险（标量跳转 + Aux Scalar 指令维持语义，README 口径是"可能退化、取决于编译器优化能力"，确证退化要看仿真流水的 VLOOPv2/RV_SJUMPI），退化后 unroll 也难生效。展开份数经验值 4/6/8 逐个试，过大撑爆寄存器引发 spill 反而回退。两个已证伪的场景（不要建议展开）：归约循环——`#pragma unroll` 只复制循环体，所有 op 仍串在同一累加器上，编译器不重排浮点归约序，simd_vf 四组（max/sum × ar/ra）实测均≈baseline；elementwise 短链——throughput-bound，发射已打满，手写 ×4 展开与 pragma 均无收益（625 vs 646/640 cycles）。

## 错误写法

```cpp
// 反例 1：循环头不满足 HWLoop 条件（uint32_t 迭代变量 / 运行期 if），unroll 难生效
for (uint32_t i = start; i < loopNum; i += 2) {      // 非 uint16_t、非 0 起步、非 1 步长
    if (hasTail && i == loopNum - 1) { /* ... */ }   // 运行期分支进入循环体
}
// 反例 2：对归约循环加 pragma unroll——所有 Add 仍串在同一 acc，实测无收益
#pragma unroll 4
for (uint16_t i = 0; i < d0; i++) { AscendC::Reg::Add(acc, acc, in, mask); }
```

## 正确写法

```cpp
// 正例：标准 HWLoop 形态 + pragma unroll 6（依赖已按 PRC-VF-003 拆短）
// 来源：cann-samples@6e6260c8 2_Performance/gelu_eltwise_regbase_story/src/3_unroll.asc:35-48
#pragma unroll 6
for (uint16_t i = 0; i < loopNum; ++i) {             // uint16_t、0 起步、步长 1、体内无 if
    mask = AscendC::Reg::UpdateMask<float>(nGelu);   // 尾块用 MaskReg，不用运行期 if
    AscendC::Reg::LoadAlign(xReg, xAddr + i * oneRepeatSize);  // 地址保持 base + i*step
    // ... 计算链
    AscendC::Reg::StoreAlign(yAddr + i * oneRepeatSize, yReg, mask);
}
```

## 识别方法

- 看什么：VF 内循环头形态（迭代变量类型/起始/步长）、体内控制流（if/continue/while/尾块 if）、`#pragma unroll` 的有无与作用对象。
- 命中条件（两类 finding）：①循环头或体内控制流破坏 HWLoop 条件（对照 simd_vf_constraints README 的退化写法表：BadU32IterVF、BadRuntimeIfVF、BadContinueVF、TailRuntimeIfVF、5 层嵌套等）；②长依赖已拆短的 elementwise 循环无展开且实测/结构上 latency 未藏满。
- 误报边界：①归约循环加 pragma unroll 无效——正确手段是多累加器（PRC-VF-007），不要报"缺 unroll"；②elementwise throughput-bound 不必展开，"没加 unroll"本身不是 finding，需先有 latency-bound 证据；③`if constexpr` 与 `Compares+Select` 是合法写法不算控制流违规；④建议展开时必须同时评估寄存器预算（RegTensor 数 × 展开份数），撑爆寄存器会 spill 回退——不给预算分析的展开建议不可采信。

## 证据要求

- 命中循环的文件:行号与循环头/控制流摘录，指明违反的具体 HWLoop 要素。
- finding ② 需说明该循环为 latency-bound 的依据（依赖链形态或 profiling），并给出展开份数与寄存器预算估算。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/gelu_eltwise_regbase_story/src/2_loop_split.asc vs 3_unroll.asc`
- `Samples/1_Features/hardware_features/simd_vf_constraints/README.md`（HWLoop 要素表/退化写法表/不允许写法表）+ `src/hwloop.asc`（Good/Bad 成对样例）
- 证伪数据：`Samples/2_Performance/simd_vf_story/`（reduce \*_pragma 四组≈baseline；elemwise 625 vs 646/640 cycles）
- 关联：PRC-VF-003（先拆依赖再展开）、PRC-VF-007（归约的正确展开=多累加器）

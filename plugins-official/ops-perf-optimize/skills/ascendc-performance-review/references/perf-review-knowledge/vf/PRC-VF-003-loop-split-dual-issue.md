---
id: PRC-VF-003
name: 按依赖拆分 VF 循环利于双发
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；单循环体内计算链很长的 VF
status: ready
---

# PRC-VF-003：按依赖拆分 VF 循环利于双发

## 知识点

把十几步计算全塞进一个 VF 循环体时，整条链是一条串行依赖（每条指令的输入是上一条的输出），双发射找不到可配对的独立指令。按依赖关系把长链拆成两段循环（段间经一次 UB 中转），每段链短、相邻迭代的指令更易交错配对双发。代价是多一对 Store/Load（UB 往返一次），当链长明显超过双发窗口时净收益为正。这与 PRC-VF-001"应融尽融"不矛盾：融合消的是 MemBase 的逐步 UB 往返与屏障；拆分是在已融合的 VF 内部，以一次 UB 中转换取两段各自的双发机会。

## 错误写法

```cpp
// 反例：GELU 8 步 + Eltwise 5 步共 13 步串行依赖塞在一个循环体，双发用不上
// 来源：cann-samples@6e6260c8 2_Performance/gelu_eltwise_regbase_story/src/1_vf_fused.asc:32-49
for (uint16_t i = 0; i < loopNum; ++i) {
    mask = AscendC::Reg::UpdateMask<float>(n);
    AscendC::Reg::LoadAlign(xReg, xAddr + i * oneRepeatSize);
    AscendC::Reg::Mul(yReg, xReg, xReg, mask);     // 每条指令都依赖上一条的 yReg
    // ... Mul/Muls/Add/Exp/Adds/Div（GELU 段）
    AscendC::Reg::Adds(yReg, yReg, COEFF_C, mask); // 紧接 Eltwise 段，链不断
    // ... Mul/Muls/Adds/Exp
    AscendC::Reg::StoreAlign(yAddr + i * oneRepeatSize, yReg, mask);
}
```

## 正确写法

```cpp
// 正例：按依赖拆两段循环，段间经 yAddr 过一次 UB；每段链短，迭代间指令易配对双发
// 来源：同目录 2_loop_split.asc:35-58
for (uint16_t i = 0; i < loopNum; ++i) {          // 段 1：GELU（8 条）
    mask = AscendC::Reg::UpdateMask<float>(nGelu);
    AscendC::Reg::LoadAlign(xReg, xAddr + i * oneRepeatSize);
    // ... GELU 链
    AscendC::Reg::StoreAlign(yAddr + i * oneRepeatSize, yReg, mask);
}
for (uint16_t i = 0; i < loopNum; ++i) {          // 段 2：Eltwise（5 条）
    mask = AscendC::Reg::UpdateMask<float>(nElt);
    AscendC::Reg::LoadAlign(yReg, yAddr + i * oneRepeatSize);
    // ... Eltwise 链
    AscendC::Reg::StoreAlign(yAddr + i * oneRepeatSize, yReg, mask);
}
```

## 识别方法

- 看什么：单个 VF 循环体的指令数与依赖形态——数循环体内 Reg 计算指令条数，检查是否几乎全部单链串行（每条的源=上一条的目的寄存器）。
- 命中条件：循环体 ≥10 条计算指令且为单条依赖链，无第二条独立链可与之交错；拆分点处语义可经 UB 中转。
- 误报边界：①循环体本身已有 2 条以上独立链（如双行并行、双累加器）时双发已有配对来源，拆分无益；②elementwise 短链（throughput-bound）不命中——发射已打满（simd_vf elemwise 实测 625 vs 646 cycles，展开/重排均无收益）；③拆分引入的 UB 中转有 store→load 保序问题：注意官方样例本身两段循环在同一 VF 内同址 store→load 且无 LocalMemBar，这与 simd_vf_constraints 的保序要求（PRC-VF-010 约束④、PRC-VF-006）存在未解释的张力——给整改建议时用更稳妥的形态（拆成两个 asc_vf_call 靠调用边界同步，或直调形态补 LocalMemBar），不要以"循环分开即免保序"为依据放行被检代码；④注意与 UpdateMask 消耗计数配套：两段各自维护独立的剩余计数（nGelu/nElt），共用一个会算错 mask。

## 证据要求

- 命中 VF 的文件:行号、循环体指令数与依赖链形态描述（哪条指令依赖哪条）。
- 说明建议的拆分点与中转 buffer；确认第二段的 Load 与第一段的 Store 地址一致。
- 有 profiling 时给拆分前后 VF 段 IPC/PUSHQ cycles 对比。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/gelu_eltwise_regbase_story/src/1_vf_fused.asc vs 2_loop_split.asc`
- 关联：PRC-VF-004（拆分后再展开）、PRC-VF-007（归约场景的多链改写）

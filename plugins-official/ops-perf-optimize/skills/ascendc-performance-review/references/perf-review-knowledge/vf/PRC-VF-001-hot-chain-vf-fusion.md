---
id: PRC-VF-001
name: 热计算链 VF 融合（MemBase→RegBase）
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 无 VF/RegBase 能力；kernel 侧；多步 elementwise/norm 类计算链
status: ready
---

# PRC-VF-001：热计算链 VF 融合（MemBase→RegBase）

## 知识点

MemBase 标准 API 每步计算都要走 UB→寄存器→UB 往返，且步间需 `PipeBarrier<PIPE_V>` 排空流水；一条 8 步 GeLU 链要 7 次中间写回 + 8 个屏障。改为 `__simd_vf__` + RegTensor 后中间值驻留向量寄存器、仅最终结果落 UB，消除中间搬运与流水排空。实测：GeLU 69.2→25.3us（2.74x，vector_function）；RmsNormQuant 单步 1.35x、总指令 -54.3%、IPC 1.10→1.34（rms_norm_quant Step3）。迁移纪律（kv_rms_norm story）：外层数据流（host/tiling/TQue/DataCopyPad/double-buffer）不动，只把最热计算链下沉进 VF，复用同源 golden 校验，出错可二分定位在数据流还是 VF body。

## 错误写法

```cpp
// 反例：每步标准 API 一次 UB 往返 + 一个 PipeBarrier（8 步链共 8 个屏障）
// 来源：cann-samples@6e6260c8 1_Features/hardware_features/vector_function/gelu_without_vf.asc:28-42
AscendC::Mul(xCube, xLocal, xLocal, n);
AscendC::PipeBarrier<PIPE_V>();
AscendC::Mul(xCube, xCube, xLocal, n);
AscendC::Muls(tLocal, xLocal, TANH_APPROX_FACTOR, n);
AscendC::PipeBarrier<PIPE_V>();
AscendC::Add(xCube, xCube, tLocal, n);
AscendC::PipeBarrier<PIPE_V>();
// ... Exp/Adds/Div 各接一个 PipeBarrier
```

## 正确写法

```cpp
// 正例：整链收进一个 __simd_vf__，中间值全在 RegTensor，一次 Load 一次 Store
// 来源：同目录 gelu_with_vf.asc:23-46
__simd_vf__ inline void gelu_vf(__ubuf__ float *xAddr, __ubuf__ float *yAddr, uint32_t n, uint32_t loopNum)
{
    AscendC::Reg::RegTensor<float> xReg, yReg, cubeReg, tReg;
    for (uint16_t i = 0; i < loopNum; ++i) {
        pMask = AscendC::Reg::UpdateMask<float>(count);
        AscendC::Reg::LoadAlign<float, AscendC::Reg::LoadDist::DIST_NORM>(xReg, xAddr + i * vectorLength);
        AscendC::Reg::Mul(cubeReg, xReg, xReg, pMask);   // 后续 Mul/Muls/Add/Exp/Div 全在寄存器间
        // ...
        AscendC::Reg::StoreAlign<float, AscendC::Reg::StoreDist::DIST_NORM_B32>(yAddr + i * vectorLength, yReg, pMask);
    }
}
// 调用：asc_vf_call<gelu_vf>(xAddr, yAddr, n, loopNum);
```

## 识别方法

- 看什么：kernel 内连续 3 步以上的 `AscendC::Mul/Add/Exp/...`（LocalTensor 版）链，步间有 `PipeBarrier<PIPE_V>` 或经 TBuf 中间张量传递；且目标架构为 dav-3510。
- 命中条件：链上各步逐元素、无跨行依赖（或依赖可用 PRC-VF-007 的归约范式表达）；中间张量只被链内消费。
- 误报边界：①目标含 A2/A3 多架构编译时，VF 只能作为 3510 分支，不能替换公共路径；②链极短（1-2 步）时 UB 往返占比小，收益有限，不作为 finding；③已有 VF 实现但外层数据流也被重写的 PR，不要求"必须整体重写"——正确路线恰是外层不动、热链下沉（kv story）；④中间张量还被 VF 外其他消费者读取时不能直接删（需先确认无别的引用）。

## 证据要求

- 命中链的文件:行号与摘录（连续标准 API 调用 + PipeBarrier/中间 LocalTensor）。
- 说明链长（步数）与中间往返次数，指出中间张量仅链内消费的依据。
- 给出对应 VF 化后的结构建议（Load 一次→寄存器串联→Store 一次），并注明保留外层数据流。

## 参考

- cann-samples@6e6260c8：`Samples/1_Features/hardware_features/vector_function/`（gelu_without_vf.asc vs gelu_with_vf.asc，2.74x）
- `Samples/2_Performance/rms_norm_quant_story/src/2_multi_core.asc vs 3_vf.asc`（1.35x，IPC 1.10→1.34）
- `Samples/2_Performance/kv_rms_norm_rope_cache_story/`（membase/ vs regbase/，迁移边界法）
- 关联：PRC-VF-002（融合三原则）、PRC-VF-010（VF 合法性前置检查）

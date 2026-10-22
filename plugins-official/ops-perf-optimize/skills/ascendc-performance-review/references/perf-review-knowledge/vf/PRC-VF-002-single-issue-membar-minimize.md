---
id: PRC-VF-002
name: VF 内单发指令与 Membar 最小化
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；已使用 __simd_vf__ 的代码
status: ready
---

# PRC-VF-002：VF 内单发指令与 Membar 最小化

## 知识点

VF 的收益来自向量指令双发射流水打满；三类东西会拉低 VF 内 IPC（kv_rms_norm story 融合三原则）：①融合不彻底——VF 内融合指令越少，UB↔寄存器交互越多；②单发指令——Reduce 类、非对齐访存、Interleave/Deinterleave 只能单发，还常与前后指令形成依赖；③Membar——`LocalMemBar` 打断 VF 内流水。实证：同一算子内 RmsNorm VF（含 ReduceSum 单发指令 + 循环间依赖）IPC≈1.15，而纯 elementwise 的 Rope VF IPC≈1.36（cannsim RVEC 指令打点估算）。单发指令无法完全避免（归约语义必须用），检视要点是"是否被不必要地放进热循环内"。

## 错误写法

```cpp
// 反例（模式示意）：把 ReduceSum/非对齐 Store 放进每轮都执行的热循环体内，
// 每轮都插入一条单发指令，打断双发配对
for (uint16_t i = 0; i < dvLoop; ++i) {
    AscendC::Reg::Add(acc, acc, square, mask);
    AscendC::Reg::Reduce<AscendC::Reg::ReduceType::SUM>(acc, acc, fullMask);   // 每轮归约：单发 + 串行依赖
}
```

## 正确写法

```cpp
// 正例：热循环内只做可双发的 lane 级累加，ReduceSum 移到循环外只执行一次
// 来源：cann-samples@6e6260c8 2_Performance/kv_rms_norm_rope_cache_story/regbase/full_load.asc:79-88
for (uint16_t i = 0; i < dvLoop; ++i) {
    mask = AscendC::Reg::UpdateMask<float>(remaining);
    AscendC::Reg::LoadAlign<T, AscendC::Reg::LoadDist::DIST_UNPACK_B16>(xB16, x + row * dv + i * VL_FP32_SIZE);
    AscendC::Reg::Cast<float, T, CAST_B16_TO_B32>(xFp32, xB16, mask);
    AscendC::Reg::Mul(square, xFp32, xFp32, mask);
    AscendC::Reg::Add(reduceSum, reduceSum, square, mask);  // lane 级累加，可双发
}
AscendC::Reg::Reduce<AscendC::Reg::ReduceType::SUM>(reduceSum, reduceSum, fullMask);    // 跨 lane 归约仅一次
```

## 识别方法

- 看什么：`__simd_vf__` 函数体内的 `Reg::Reduce<Reg::ReduceType::SUM>/ReduceMax`、`LoadUnAlign/StoreUnAlign`、`Interleave/Deinterleave`、`LocalMemBar` 出现的位置——是在最内层热循环内还是循环外/每行一次。
- 命中条件：单发指令位于按 VL 切分的最内层循环体内，且语义上可移到循环外（如先 lane 级累加再一次跨 lane 归约）；或 LocalMemBar 用于可以靠寄存器传值消除的 store→load。
- 误报边界：①每行一次的 ReduceSum（行归约语义所需）是正确用法，不是 finding——RmsNormVF 的 IPC 1.15 已是该语义下的合理写法；②asc_vf_call 内 LocalMemBar 在大合并 VF 场景有死锁实例（证据源两侧冲突，见 PRC-VF-006），"经 UB 分趟 + 分属不同 asc_vf_call"是稳妥形态，不能反过来要求"合并进一个 VF 少一次屏障"；③非对齐访存若数据布局天然非对齐（单标量流式输出），StoreUnAlign 是标准写法（见 PRC-VF-010）。

## 证据要求

- 命中的 VF 函数名、文件:行号，摘录单发指令所在循环层级。
- 论证可外提：指出等价改写（lane 累加 + 循环外归约）且语义不变。
- 有 profiling 时给 VF 段 IPC 或 RVEC 指令占比；无则注明为结构级判断。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/kv_rms_norm_rope_cache_story/README.md`（融合三原则，L148-150；IPC 1.15 vs 1.36 实证，L351）
- 关联：PRC-VF-001（融合边界）、PRC-VF-006（asc_vf_call 屏障/LocalMemBar 兼容性）、PRC-VF-007（归约结构）

---
id: PRC-VF-007
name: 归约结构优化（多累加器/二分折叠）
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；VF 内含归约循环的代码
status: ready
---

# PRC-VF-007：归约结构优化（多累加器/二分折叠）

## 知识点

归约循环 `acc = op(acc, x)` 是循环携带依赖，latency-bound：每条 op 要等上一条写回，暴露 L-1 拍空泡，双发完全用不上。两个结构改写：①**多累加器**——开 4 路独立累加器轮流吃数据、末尾合并，指令数几乎不变、纯藏延迟；收益∝串行步数：simd_vf 实测 ra 轴（78 步）sum +51.9%（757→364 cycles）、max +29.8%，ar 轴（仅 4 步）只 +15%；②**二分折叠**（sum 类专属）——成对折叠同时减串行步数、减指令量（RV_VADD 312→234）、还提精度（pairwise summation），ar 轴实测 ≈2x（792→384），胜 unroll；样例仓仅对 sum 提供了二分折叠对照（README 给 max 的理由是"精确选元素"的校验口径选择）；max 语义严格可结合、成对 vmax 折叠逐位精确，机制上同样合法——见到别人的 max 二分实现不要否定，只是无实测数字、不强制推荐。softmax 上的变体：even/odd 拆 2 链 -3.7%；搬到本就独立的 row0/row1 双累加器 -6.3%（严格更优）。边界：双发已饱和后再加链数反回退（softmax 4 链实测 +5%）。

## 错误写法

```cpp
// 反例：单累加器串行依赖，每条 Add 等上一条，空泡藏不住
// 来源：cann-samples@6e6260c8 2_Performance/simd_vf_story/reduce/src/reduce_sum_ra_baseline.asc
for (uint16_t i = 0; i < static_cast<uint16_t>(d0); i++) {
    AscendC::Reg::LoadAlign<float, AscendC::Reg::LoadDist::DIST_NORM>(inReg, xAddr + i * d1Pad + c * VL_B32);
    AscendC::Reg::Add(accReg, accReg, inReg, mask);   // acc 串行依赖链，长度 = d0
}
```

## 正确写法

```cpp
// 正例：4 路独立累加器互填空泡，末尾 3 条 Add 合并（+51.9%）
// 来源：同目录 reduce_sum_ra_unroll.asc
for (uint16_t g = 0; g < groups; g++) {              // 每轮 4 行 → 4 个独立累加器
    AscendC::Reg::LoadAlign<float, AscendC::Reg::LoadDist::DIST_NORM>(in0, xAddr + (r + 0) * d1Pad + c * VL_B32);
    // ... in1/in2/in3
    AscendC::Reg::Add(acc0, acc0, in0, mask);
    AscendC::Reg::Add(acc1, acc1, in1, mask);
    AscendC::Reg::Add(acc2, acc2, in2, mask);
    AscendC::Reg::Add(acc3, acc3, in3, mask);
}
AscendC::Reg::Add(acc0, acc0, acc1, mask);           // 合并
AscendC::Reg::Add(acc2, acc2, acc3, mask);
AscendC::Reg::Add(acc0, acc0, acc2, mask);
// sum 类另可二分折叠：reduce_sum_ar_binary.asc（块两两 Add → ReduceSum，≈2x 且提精度）
```

## 识别方法

- 看什么：VF 内形如 `op(acc, acc, x)` 的循环携带依赖；数循环的串行步数（迭代次数），确认累加器只有一个。
- 命中条件：单累加器且串行步数较大（参考：78 步收益 +51.9%，4 步仅 +15%——步数个位数时收益有限，可降级为建议）；sum 语义优先建议二分折叠；max/min 建议多累加器（有实测背书），已写成二分折叠的不按本条报。
- 误报边界：①已有 ≥2 条独立链（多行并行/双累加器）且怀疑双发已饱和时，再加链数会回退（softmax 4 链 +5%）——不要机械建议"再加到 4 路"；②`#pragma unroll` 不是本条的修复手段（对归约无效，见 PRC-VF-004）；③改写涉及浮点求和顺序变化，输出容差极严的场景需确认精度口径（二分折叠实际提精度，多累加器改变求和序但通常无害）；④尾部不足一组的行须有独立收尾循环（unroll 版的尾部 0~3 行处理），漏掉是正确性 bug。

## 证据要求

- 命中循环的文件:行号与摘录，给出串行步数估算（迭代次数×每轮 op 数）。
- 说明建议链数（默认 4）及其寄存器成本（累加器+载入寄存器各×链数）。
- 已有多链的代码要求先证明未饱和（IPC/PUSHQ 数据）再建议加链。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/simd_vf_story/reduce/src/`（baseline/unroll/binary/pragma 全对照）
- `Samples/2_Performance/softmax_regbase_story/src/2_binary_fold.asc、3_multi_row.asc`（变体与 4 链回退边界）
- `Samples/2_Performance/rms_norm_quant_story/src/6_binary_sum.asc`（二分累加精度收益）
- 关联：PRC-VF-004（pragma 对归约无效）、PRC-VF-010（末块 MERGING mask/StoreUnAlign 约定）

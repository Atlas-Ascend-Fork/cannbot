---
id: PRC-VF-008
name: broadcast 循环序与最内层长度
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；向量×低维张量（bias/scale/逐行标量）广播计算
status: ready
---

# PRC-VF-008：broadcast 循环序与最内层长度

## 知识点

broadcast 类计算（y[m,n] = x[m,n] op a[·]）的 VF 写法按广播轴分三个范式（simd_vf broadcast，cannsim 计 PUSHQ cycles）：①**尾轴广播**（a[m] 逐行标量）：反模式是外层标量循环逐行 asc_vf_call + `GetValue` 传参（每行付一次 call 开销）；正解是行循环收进单 VF、行内 `DIST_BRC_B32` 广播读 a[j]——VF count 17→1、PUSHQ 1247→356；②**首轴广播**（a[n] 跨行复用）：循环序 n→m（每个 n 块载一次 aReg 供所有行用）优于 m→n（重复读 aReg）——PUSHQ 839→275 vs 442；③**中间轴广播**：两步收循环后，最优序还要看最内层循环长度——b 轴很短（如 b=3）时"复用 aReg 优先"的 n→b 反而输给"主数据连续 + 内层够长"的 b→n；m→b→n 全场最优（1168→593）。核心判据：**广播寄存器复用要让位于最内层循环长度**——内层太短则 HWLoop 摊销与访存连续性收益吃不满。

## 错误写法

```cpp
// 反例：VF 外逐行循环 + GetValue 传标量，每行一次 asc_vf_call（VF count=m）
// 来源：cann-samples@6e6260c8 2_Performance/simd_vf_story/broadcast/src/tail_axis_1_naive_getvalue.asc:65-68
for (uint32_t j = 0; j < tiling.m; ++j) {
    asc_vf_call<ComputeVF>(xAddr + j * nAligned, yAddr + j * nAligned, n, vfLoopN,
        aLocal.GetValue(j));   // 标量走 Main Scalar → PB 传参，每行付一次
}
```

## 正确写法

```cpp
// 正例：行循环收进单 VF，行内 DIST_BRC_B32 广播（VF count 17→1，PUSHQ 1247→356）
// 来源：同目录 tail_axis_2_distbrc.asc
for (uint16_t j = 0; j < vfLoopM; ++j) {
    remain = n;
    AscendC::Reg::LoadAlign<float, AscendC::Reg::LoadDist::DIST_BRC_B32>(aReg, aAddr + j);
    for (uint16_t i = 0; i < vfLoopN; ++i) {
        mask = AscendC::Reg::UpdateMask<float>(remain);
        AscendC::Reg::LoadAlign<float>(xReg, xAddr + j * nElemsAligned + i * VL_B32);
        AscendC::Reg::Add<float>(yReg, xReg, aReg, mask);
        AscendC::Reg::StoreAlign<float>(yAddr + j * nElemsAligned + i * VL_B32, yReg, mask);
    }
}
// 首轴广播正解（n→m 序，外层载 aReg 内层复用）：head_axis_2_vfloop_nm.asc
```

## 识别方法

- 看什么：①VF 外的标量 for 循环内逐次 `asc_vf_call`，且差异仅是行偏移/一个 `GetValue` 标量；②首轴/中间轴广播场景的循环嵌套顺序——广播源 aReg 的 Load 在哪一层、最内层循环的迭代次数。
- 命中条件：①逐行 asc_vf_call 且行数不小（几十次以上），可收进单 VF——结构性 finding；②aReg 在最内层被重复 Load，且外提后不缩短最内层有效长度、不劣化主数据访问连续性（外提代价见知识点③的反例）——结构性 finding；③循环序类问题（含"为复用 aReg 把很短的轴放最内层"）只作为建议级 finding，必须附"依 shape 而定、建议 A/B 实测"，不下结构性结论。
- 误报边界：①逐行 asc_vf_call 若因每行间需要 UB 可见性同步（PRC-VF-006 的分趟场景）则是必要结构，不能收进单 VF；②循环嵌套 >4 层收循环会破坏 HWLoop（PRC-VF-004），收进 VF 前先数层数；③"m→b→n vs m→n→b"这类次优序差异（593 vs 710）属于调优建议级别，不同 shape 下最优序会变，无实测不要下强结论——只有 naive 逐行 call 与内层重复 Load 这两类是结构性 finding。

## 证据要求

- 命中的文件:行号与摘录（asc_vf_call 所在循环/aReg Load 所在层级）。
- 给出行数/各轴长度（从 tiling 或 shape 推导），说明最内层长度是否足够。
- 循环序类建议须注明"依 shape 而定，建议 A/B 实测"，除非有 profiling 数据。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/simd_vf_story/broadcast/src/`（tail_axis 1→2、head_axis 1→2→3、mid_axis 1→5 全对照，README 附 PUSHQ 数据）
- 关联：PRC-VF-005（常量外提）、PRC-VF-009（DIST_BRC 选型）、PRC-VF-006（分趟必要性）

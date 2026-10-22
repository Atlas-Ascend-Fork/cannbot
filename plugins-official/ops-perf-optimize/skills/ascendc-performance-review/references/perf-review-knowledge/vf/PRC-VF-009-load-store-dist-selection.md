---
id: PRC-VF-009
name: Reg Load/Store 分布模式选型
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；VF 内 UB↔寄存器搬运
status: ready
---

# PRC-VF-009：Reg Load/Store 分布模式选型

## 知识点

VF 内 UB↔寄存器一跳的 Load/Store 有分布模式（dist）可选，选错模式要么多付重排指令，要么直接错数据。选型决策树（reg_data_movement 指南）：elemwise 原样进出→`DIST_NORM`（缺省）；变位宽 Cast（b16 存储、fp32 计算）→搬入 `DIST_UNPACK_B16` / 搬出 `DIST_PACK_B32`，且 **mask 必须按计算时的宽类型生成**（`UpdateMask<float>` 而非 `<half>`，否则开出不存在的 lane 静默错数）；标量广播进→`DIST_BRC_B32`；归约标量出→`DIST_FIRST_ELEMENT_B32` 配 `MaskPattern::VL1`；非连续/离散→`DATA_BLOCK_COPY` + Gather。两条硬规则：①Load 不带 mask（多读的无效 lane 被后续计算 mask 屏蔽），②**Store 必须带 mask**——总量不是 lane 数整数倍时，末轮不带 mask 会把垃圾 lane 写穿输出 buffer（尾块脏写，正确性 bug）。寻址模式与 mask 是与 dist 正交的维度，每种搬运都要配。

## 错误写法

```cpp
// 反例 1：StoreAlign 不带尾块 mask——N=150 非 64 整数倍，末轮 42 个垃圾 lane 脏写 z[150..]
AscendC::Reg::StoreAlign<float, AscendC::Reg::StoreDist::DIST_NORM>(
    zAddr + i * VL, vregC, fullMask);          // 应传 UpdateMask 递减出的尾 mask
// 反例 2：UNPACK 场景 mask 按窄类型生成——half 128 lane，实际按 fp32 64 lane 计算
mask = AscendC::Reg::UpdateMask<half>(count);  // 应为 UpdateMask<float>
```

## 正确写法

```cpp
// 正例：UpdateMask 递减尾块，Load 无 mask、Store 带 mask
// 来源：cann-samples@6e6260c8 1_Features/memory_optimization/reg_data_movement/src/scene1_dist_norm.asc
for (uint16_t i = 0; i < loopNum; i++) {
    mask = AscendC::Reg::UpdateMask<T>(count);   // 开前 count 个 lane，count 原地递减
    AscendC::Reg::LoadAlign<T, AscendC::Reg::LoadDist::DIST_NORM>(vregA, xAddr + i * VL); // 搬入无 mask
    AscendC::Reg::LoadAlign<T, AscendC::Reg::LoadDist::DIST_NORM>(vregB, yAddr + i * VL);
    AscendC::Reg::Add(vregC, vregA, vregB, mask);
    AscendC::Reg::StoreAlign<T, AscendC::Reg::StoreDist::DIST_NORM>(zAddr + i * VL, vregC, mask); // 搬出带 mask
}
// 归约标量出：StoreAlign<float, DIST_FIRST_ELEMENT_B32>(yAddr + i, vregSum, maskVL1)，
// 偏移按元素步进（+i 而非 +i*VL）——scene4_first_element.asc
```

## 识别方法

- 看什么：VF 内每条 `LoadAlign/StoreAlign/DataCopy` 的 dist 模板参数、mask 实参、地址步进；对照数据流形态（原样/变位宽/广播/标量出/离散）。
- 命中条件：①Store 用 ALL/CreateMask 全开 mask 且总量非 lane 整数倍（尾块脏写）；②UNPACK/PACK 场景 mask 类型与计算宽类型不一致；③FIRST_ELEMENT 输出偏移按 `i*VL` 步进（应按元素）；④用标量循环 GetValue/逐元素拼装实现本可用 BRC/UNPACK/DATA_BLOCK_COPY 一条指令完成的搬运（多付指令）。
- 误报边界：①总量保证是 VL 整数倍（如 tiling 强制对齐）时全开 mask 的 Store 合法——要先查 shape/tiling 约束再报脏写；②尾块脏写若写的是本核私有 padding 区且下游不读，功能上无害，降级为规范性问题；③Load 带 mask 不是错误（只是多余），不作为 finding。

## 证据要求

- 命中指令的文件:行号与摘录，注明 dist/mask/步进三要素中违反的那个。
- 脏写类 finding 须给出"总量非 lane 整数倍"的推导（shape、dtype、VL）与越界写入的目标区域归属。
- 选型不优类 finding 给出替代 dist 模式与省掉的指令。

## 参考

- cann-samples@6e6260c8：`Samples/1_Features/memory_optimization/reg_data_movement/Reg数据搬运场景选型指南.md`（决策树+10 场景样例 scene1~scene10）
- 关联：PRC-VF-008（BRC 使用场景）、PRC-VF-010（StoreUnAlign 成对冲刷、MERGING mask）

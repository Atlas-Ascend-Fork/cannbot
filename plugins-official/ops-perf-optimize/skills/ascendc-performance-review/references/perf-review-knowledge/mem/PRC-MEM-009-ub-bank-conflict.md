---
id: PRC-MEM-009
name: UB bank 冲突规避
category: MEM
applies_to: 分架构：220x/DAV_2201（16 bank group × 3 bank，UB 192KB，静态判定）；dav-3510/A5（拓扑 8 bank group × 2 bank × 16KB 已与平台 ini 互证对齐，上板实测冲突影响大幅弱化，bank 对齐类静态判定降级为建议）；kernel 侧
status: ready
---

# PRC-MEM-009：UB bank 冲突规避

## 知识点

UB 物理上由多个 bank 组成，一个指令周期内多条访问落在同一 bank 需排队，分读写冲突、写写冲突、读读冲突三类，冲突使本可单周期完成的访存串行化。布局与影响按架构分：

- **220x/DAV_2201**：16 个 bank group × 3 bank（UB 192KB，48 bank × 4KB）。规避手段是规划 buffer 起始地址，让同一条 Vector 指令的多个操作数（src0/src1/dst）落在不同 bank（group）。官方页为概述性质，无正反例代码与量化数据；地址→bank 映射公式为官方示例推导（相邻 32B 行按 bank 总数轮询），以芯片手册为准。
- **dav-3510/A5**：拓扑为 8 bank group × 2 bank × 16KB（硬件 256KB，每行 32B，双读口设计——两读同 group 不同 bank 不冲突）。**上板微基准实测（2026-08-27，Ascend950PR_9579）表明冲突影响被结构性弱化**：1R1W 路径对操作数地址关系完全不敏感；2R1W 仅在两源基址错开一个 32B block 时约 +2%（实测命中点为 32B 与 4KB+32B 两个错位；"≡ 32B (mod 4KB)"是据此与各无感对齐点外推的形态式，64B/96B/2KB+32B 等中间错位未逐点验证），同址与 512B/4KB/16KB/64KB 对齐均无感；未观察到 16KB 整数倍对齐惩罚——冲突粒度远细于 16KB bank 连续块，按 32B block / 4KB 亚 bank 级工作。机制上 A5 为 RegBase，Vector 计算在寄存器完成、UB 主要是 MTE 中转站，指令级 UB 访问频率低；bank 冲突对 memory-bound 算子端到端趋近 0，仅 compute-bound 可见 1-2% 量级。

A5 上的结论性判据：**不再为 16KB group/bank 对齐投入 tiling/布局精力**；buffer 32B 对齐（编译器默认保证）+ 大 buffer 相互隔开 512B/4KB 即可，优化预算转向 MTE 搬运吞吐与对齐口径（PRC-MEM-008/014）。

### 口径对齐（dav-3510，2026-08-27 上板复核 + ini 互证）

早期复核记录的 ini 与官方 0025 页"对不上"已解除——两个口径是同一物理的两层抽象：

```text
# 平台 ini（Ascend950PR_9579.ini，68 个档位取值一致）
ub_size=253952        # 平台报告值 = 硬件 256KB − 8KB 保留，与 GetCoreMemSize(UB) 一致
ubbank_size=4096      # 亚 bank 4KB
ubbank_num=16         # 16 bank × 16KB = 256KB（bank 视角）
ubsubbank_num=64      # 64 亚 bank × 4KB = 256KB（亚 bank 视角）
ubbank_group_num=8    # 8 group × 2 bank × 16KB = 256KB（官方 0025 页视角）
```

`8 group × 2 bank × 16KB` = `16 bank × 16KB` = `64 subbank × 4KB` = 256KB，三种验算自洽；官方页的「bank」对应 ini 的 16KB bank，`ubbank_size=4096` 计的是 subbank 层。具体地址→bank 的逐行映射公式仍未反推（实测热点散布、无 16KB 周期），以芯片手册为准，但实测表明其粒度不支撑"16KB 连续 bank"的静态判定。

### 上板实测摘要（bank_probe 微基准，Ascend950PR_9579/dav-3510，2026-08-27）

方法：UB 内手工布位两块 16KB fp32 源（x@0 固定、y 偏移可调）+ 固定远置 dst，排除重叠干扰；`Add`(2R1W) 与 `Muls`(1R1W) 大重复次数纯 UB 循环，host acl event 计时、多轮取 min。

| y 相对 x | Add (2R1W) | Muls (1R1W) |
|---|---|---|
| 同址 | 基线 | 基线 |
| 错位 32B / 4KB+32B | **约 +2%** | 基线（无感） |
| 512B / 4KB / 16KB / 48KB / 64KB 对齐 | 基线 | 基线 |

未覆盖（不得外推）：DataCopy/MTE2/MTE3 批量并发访问 UB 的 bank 行为、>2 读同 group、多核并发、fp32 以外 dtype；错位取值仅采样表中各点，"≡ 32B (mod 4KB)"形态式是外推，未逐点扫描中间错位。

## 错误写法

```cpp
// 反例（220x，按官方 0025 机制描述构造）：src0 与 src1 的 UB 偏移相差
// 恰为 bank group 映射周期的整数倍，二元指令的两路读每拍落同一 bank 排队
pipe.InitBuffer(src0Buf_, bufSize);  // 偏移 0
pipe.InitBuffer(src1Buf_, bufSize);  // 偏移恰好与 src0Buf_ 同 bank 映射
pipe.InitBuffer(dstBuf_, bufSize);
AscendC::Add(dst, src0, src1, count); // src0/src1 同 bank -> 读读冲突
// 注意区分冲突类别：读读冲突在 dav-3510 双读口下有"同 group 不同 bank"豁免，读写/写写没有
```

A5 反例（示意，构造自 220x 习惯平移）：为 16KB bank/group 对齐做防御性布局——大块 padding 或把本可吃满的 ubFactor 压小（对照 PRC-MEM-012）。实测 A5 冲突代价仅 32B 错位形态的 ~2%，16KB 对齐 pad 属负收益。

```cpp
// 反例（A5）：为凑 16KB bank 对齐牺牲 UB 吃满与切分粒度
ubFactor = FloorAlign(ubFactor, UB_BANK_GROUP_BYTES);  // 16KB 级对齐，UB 容量白扔
pipe.InitBuffer(padBuf_, PAD_TO_BANK_GROUP);           // 大块 padding 仅服务于 bank 对齐
```

## 正确写法

```cpp
// 正例（220x）：调整 buffer 申请顺序/插入 padding，错开各操作数的 bank 归属；
// 具体地址→bank 映射按目标架构的 bank 布局计算（220x 见 applies_to）
pipe.InitBuffer(srcBuf_, bufSize);
pipe.InitBuffer(padBuf_, BANK_OFFSET_PAD);   // 错位 padding
pipe.InitBuffer(dstBuf_, bufSize);
```

```cpp
// 正例（A5）：32B 对齐（编译器默认保证），大 buffer 间以 512B/4KB 隔离即可；
// 不为 bank 做 16KB pad，预算转向 MTE 搬运吞吐与对齐口径（PRC-MEM-014）
ubFactor = FloorAlign(FloorDiv(usableUbSize, ubBytesPerElement), alignElements);
```

## 识别方法

在被检视源码中看：

1. 先分架构（见 applies_to）。220x：按 InitBuffer 申请顺序累加各 buffer 的 UB 偏移，对高频 Vector 指令核对其多路操作数地址按架构映射是否落同一 bank（group）；重点模式是两块大小恰为映射周期整数倍的 buffer 相邻申请、被同一条二元/三元指令同时访问。
2. dav-3510/A5：**bank 对齐类静态判定不立 finding**——逐行映射公式未定且实测影响 ≤2%。仅当同时满足 ①kernel compute-bound（profiling 或搬运/计算比推断）②高频二元指令两源基址差落在实测命中形态（32B 或 4KB+32B 错位；通式 ≡ 32B (mod 4KB) 为外推，见知识点采样说明） ③改法零代价（调整 buffer 申请顺序即可错开）时，降级为"建议 A/B 验证"。
3. 反向检查（A5 专属）：发现为 bank/group 对齐引入的 16KB 级 padding 或被压小的 ubFactor，按负收益防御提出回退建议，并与 PRC-MEM-012（UB 吃满）联动。

误报边界：220x 静态推导没把握时不单独立 finding，降级为"建议 A/B 验证"；dav-3510 双读口下"两读同 group 不同 bank"不冲突，勿按 220x 规则误报；A5 上对"未做 16KB bank 对齐"的布局不得报缺陷；冲突指令不在热路径的不报。

## 证据要求

finding 必须给出：

- 各 buffer 偏移的完整推导（InitBuffer 顺序与大小累加表）；220x 需给出所用架构 bank 映射规则的出处；
- 命中指令的文件:行号与摘录及其执行频率；A5 需给出 compute-bound 依据与错位形态（≡ 32B (mod 4KB)）的地址推算；
- A5 的 bank 相关建议一律附 A/B 上板验证方案（与 bank_probe 同构的微基准或等价 profiling 对照）；若无法静态确证，降级为"建议 A/B 验证"而非缺陷结论。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0025`（概述页，无代码与量化数据；220x 与 "Atlas 350"（=DAV_3510）布局均出自此页）。
- 交叉印证：`ops/ascendc-performance-best-practices` skill 中，arch22 使用 `reference/common/arch22/ub_bank_conflict.md` 的映射与示例，arch35 使用 `reference/common/arch35/ub_resident_design.md` §2.2 的 bank 规则。
- 上板实测（2026-08-27，Ascend950PR_9579，CANN 9.2.0）：bank_probe 微基准——UB 手工布位（`LocalTensor(TPosition, addr, len)` + `GetPhyAddr` 校验）+ Add/Muls 对照，host acl event 多轮取 min，数据见上文摘要表；ini 证据：`Ascend950PR_9579.ini`（`ubbank_group_num=8` / `ubbank_num=16` / `ubsubbank_num=64` / `ubbank_size=4096` / `ub_size=253952`）。
- 升级 ready 的依据：dav-3510 口径已对齐（ini 互证）且冲突影响已上板量化（1R1W 无感 / 2R 错位 32B 约 +2%）；220x 部分仍以官方机制描述 + 芯片手册为准。

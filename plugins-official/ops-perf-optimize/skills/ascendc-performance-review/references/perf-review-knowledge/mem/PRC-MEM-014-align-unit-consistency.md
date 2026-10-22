---
id: PRC-MEM-014
name: 切分因子对齐单位选型与字节/元素口径
category: MEM
applies_to: 机制通用（各代 AI Core）；对齐宽度一律按平台接口取值（ubBlock/vReg/cacheline），不代入固定字节数；tiling 侧为主；口径混用是结构性缺陷，性能差值未上板量化 → draft
status: draft
---

# PRC-MEM-014：切分因子对齐单位选型与字节/元素口径

## 知识点

tiling 里有三档对齐单位，各管一件事，宽度全部来自平台接口（按 PRC-ARCH-002 取证，不写死数值）：

- **ubBlock（`GetUbBlockSize()`）**：DMA 搬运的最低对齐，UB 内 buffer 起址与 DataCopy 块长的底线；
- **vReg（`GetVRegSize()`）**：`ubFactor` 对齐到 vReg 宽度的**元素**整数倍，每轮向量计算才能整寄存器覆盖、无跨 reg 掐头去尾，尾 mask 处理退化为仅末轮一次；
- **cacheline（`GetCacheLineSize()`）**：核级 `blockFactor` 对齐到 cacheline 的元素整数倍，各核起始 GM 地址天然对齐，MTE 无碎片事务（GM 侧对齐收益见 PRC-MEM-008）。

推荐组合：`ubFactor` 对齐 `max(ubBlock, vReg)` 的元素数；`blockFactor` 对齐 cacheline 的元素数（或其整数倍）。

两种命中形态：

- **形态① 字节常量当元素数用（口径错）**：平台接口返回的对齐宽度是**字节**语义；直接拿它当元素数做 `CeilAlign(x, 宽度)`，实际对齐强度变成 `宽度×sizeof(T)` 字节——随 dtype 漂移：宽 dtype 下**过对齐**（因子被无谓抬大，浪费 UB 或加剧核间不均），仅 sizeof(T)=1 时碰巧等于本意；反向口径错（元素数当字节用）则在宽 dtype 下**对齐不足**。两个方向判据相同：求解链里有没有 `/sizeof(T)` 的显式换算。
- **形态② ubFactor 只对齐 ubBlock、不对齐 vReg**：每轮向量计算的末段不是整 vReg，尾 mask 逻辑每轮都要走（而非仅末轮），既添标量开销，mask 写错时还放大为越界风险。

## 错误写法

```cpp
// 反例（形态①）：接口返回字节宽度，被当元素数对齐 → 实际对齐强度随 dtype 漂移
blockFactor = CeilAlign(CeilDiv(totalNum, coreNum), GetUbBlockSize(context));
```

```cpp
// 反例（形态②）：ubFactor 只对齐 ubBlock 元素数，未对齐 vReg
maxBase = FloorAlign(maxBase, GetUbBlockSize(context) / sizeof(T));
// 每轮 VL lane 的向量循环末段非整 vReg，尾 mask 处理轮轮触发
```

## 正确写法

```cpp
// 正例：对齐宽度取自平台接口，显式换算成元素口径
uint32_t alignBytes    = std::max(GetUbBlockSize(context), GetVRegSize(context));
uint32_t alignElements = alignBytes / sizeofT;                    // 字节 → 元素显式换算
ubFactor = FloorAlign(FloorDiv(usableUbSize, ubBytesPerElement), alignElements);
```

```cpp
// 正例：核级块对齐 cacheline 的元素数，核边界 GM 地址恒对齐
int64_t blockAlignElems = GetCacheLineSize(context) / sizeofT;
blockFormer = CeilAlign(CeilDiv(totalLength, coreNum), blockAlignElems);
```

## 识别方法

1. **查每个对齐常量的口径**：对 `CeilAlign/FloorAlign` 的第二实参逐个追源——来自平台接口（字节语义）的，看有没有 `/sizeof(T)` 换算成元素；没有换算且被用于元素数对齐 → 形态①命中。
2. **查 ubFactor 的对齐档位**：`ubFactor` 求解式的对齐项换算成字节后 < vReg 宽度 → 形态②候选；再看 kernel 计算层是否按 VL 分轮（RegBase/VF 类必看），是则命中。
3. **查 blockFactor 的对齐档位**：核级块完全不对齐（如纯 `CeilDiv`）本身不报（DataCopyPad 可兜底、正确性无虞），仅当 profiling/用例显示 MTE2 是候选瓶颈时作为优化建议提出，并与 PRC-MEM-008 联动。

误报边界：

- 对齐不足靠 `DataCopyPad` 兜底的写法**功能正确**，本条只谈性能与尾处理复杂度，不得当正确性问题报。
- 吃满 UB 与对齐取整冲突时（对齐会舍掉少量 UB），对齐优先——舍入量通常远小于收益，见 PRC-MEM-012 的对齐余量叙事。
- 归约/行语义轴（行数、头数）不要求字节对齐（行是决策单元不是搬运单元），对这类因子不报。
- 各档对齐宽度按 PRC-ARCH-002 取证；样例中的具体字节数（32/256/512 等）是某一平台的示意值，不得代入其他平台断言。

## 证据要求

finding 必须给出：

- 对齐常量来源与口径的追值链（接口调用处或常量定义处文件:行号，字节/元素判定依据）；
- ubFactor/blockFactor 求解式的文件:行号与摘录，换算成字节后的实际对齐强度（按用例集 dtype 分别列）；
- 形态②需给出 kernel 计算层的 VL 分轮证据（每轮 lane 数、尾 mask 处理位置）；
- 若作为 MTE2 优化建议，需给出候选瓶颈依据（profiling 或搬运/计算比推断）。

## 参考

- 在库对照（dav-3510，2026-08-27 源码分析，仅作例证）：activation 类（`max(ubBlock, vReg)` 元素对齐正例）、loss 类（核边界按 cacheline 整数倍元素对齐正例）、optim 类（字节宽度当元素数用的形态①反例）、quant 类（ubFactor 未对齐 vReg 且尾 mask 轮轮触发的形态②反例）。
- 关联知识点：PRC-MEM-008（GM 对齐）、PRC-MEM-012（UB 吃满与对齐余量）、PRC-ARCH-002（平台常量取证）、PRC-VF-010（VF 尾 mask 合法性）。

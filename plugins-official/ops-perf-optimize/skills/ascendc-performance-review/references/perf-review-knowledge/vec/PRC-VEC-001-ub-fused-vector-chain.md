---
id: PRC-VEC-001
name: UB 融合连续矢量计算
category: VEC
applies_to: 机制通用（各代 AI Core）；kernel 侧 MemBase 数据流；官方数据为搬运次数口径（两级链 4→2 次，n 级链 2n→2 次）；dav-3510 上应优先考虑更进一步的 VF 融合（见 PRC-VF-001）
status: ready
---

# PRC-VEC-001：UB 融合连续矢量计算

## 知识点

连续的 vector 计算若每一步都把中间结果写回 GM、下一步再搬回 UB，n 级计算链要付 2n 次 GM 搬运；而中间结果留在 UB 上直接作为下一步输入时，只需开头搬入源操作数、结尾搬出最终结果共 2 次。GM 带宽远低于 UB 访问，多出来的 2(n-1) 次搬运是纯浪费（官方 0012/0020，两级链搬运 4→2 次）。常见形态是多个单算子 kernel 被逐段直译过来、或用 GM workspace 传递中间量。在 dav-3510 上此条只是底线：UB 级融合后中间量仍走 UB 往返，更优做法是把计算链下沉 VF 让中间量驻留寄存器（PRC-VF-001）。

## 错误写法

```cpp
// 反例（依官方文档 10_0012 示例重构）：Exp 结果写回 GM，Abs 再从 GM 搬回
CopyIn(xLocal, srcGm);
AscendC::Exp(yLocal, xLocal, count);
CopyOut(workspaceGm, yLocal);        // 中间结果落 GM
CopyIn(yLocal2, workspaceGm);        // 又搬回来
AscendC::Abs(zLocal, yLocal2, count);
CopyOut(dstGm, zLocal);              // 共 4 次 GM 搬运（两级链）
```

## 正确写法

```cpp
// 正例（依官方文档 10_0012 示例重构）：中间结果全程留在 UB
CopyIn(xLocal, srcGm);
AscendC::Exp(yLocal, xLocal, count);   // 输出留在 UB
AscendC::Abs(zLocal, yLocal, count);   // 直接消费上一步 UB 结果
CopyOut(dstGm, zLocal);                // 共 2 次 GM 搬运
```

## 识别方法

在被检视源码中看：

1. GM workspace/临时 GlobalTensor 的用途：某段计算的 CopyOut 目标随后又作为 CopyIn 源（同一 kernel 内，或同一算子的多个 kernel 之间），且中间量总大小能放进 UB（按批切分后），命中。
2. 主循环内"算一步→搬出→搬入→再算一步"的调用序（CopyOut 与下一 CopyIn 操作同一地址区间）。
3. 跨 kernel 形态：host 侧连续 launch 多个小 elementwise kernel、以 GM 张量串联——建议融合为单 kernel。

误报边界：中间量必须落 GM 的场景不报——多核间交换数据（核 A 产出核 B 消费）、中间量整体超 UB 且无法按行/块切分流水化、或后续消费的访问模式与产出不匹配（如需全局转置/排序）；框架强制的多算子边界（图上两个独立算子）属图融合问题，可提示但非 kernel 缺陷；dav-3510 上若计算链已在 UB 融合，进一步的寄存器化收益归 PRC-VF-001，不重复报本条。

## 证据要求

finding 必须给出：

- 中间量落 GM 的写出与读回两处文件:行号与摘录（证明地址区间相同）；
- 中间量可留 UB 的依据：按现有批大小估算中间 buffer 字节数 vs UB 余量；
- 排除依据：说明中间量无跨核消费。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0012` / `10_0020`（UB 融合连续 vector 计算，2n→2 次搬运）。
- 关联知识点：PRC-VF-001（dav-3510 上寄存器级融合，rms_norm_quant Step3 实测 1.35x）；融合后 UB 中间 buffer 的空间问题见 PRC-MEM-007。

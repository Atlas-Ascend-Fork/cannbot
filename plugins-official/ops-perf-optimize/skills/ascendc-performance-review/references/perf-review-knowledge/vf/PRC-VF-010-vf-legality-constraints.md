---
id: PRC-VF-010
name: VF 合法性约束（正确性前置检查）
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；所有 __simd_vf__ 代码，性能检视前先过本条
status: ready
---

# PRC-VF-010：VF 合法性约束（正确性前置检查）

## 知识点

VF 有一组硬性合法约束，违反轻则编译失败、重则未定义行为或静默错数；性能检视应先过一遍，避免在非法代码上讨论优化。约束清单（simd_vf_constraints）：①**入参**——仅基本类型和 `__ubuf__` 指针；引用、普通/`__gm__` 指针、数组（退化为指针）、函数指针、结构体按值传递均不支持；②**调用形态**——`__simd_vf__` 不能调用另一个 `__simd_vf__` 或 `__aicore__` 函数，`__simd_callee__` 不能递归；③**HWLoop**——循环内 `break` 编译失败，循环内改边界/步长是未定义行为（成环条件详见 PRC-VF-004）；④**LocalMemBar**——同地址 Store→Load（含跨迭代）必须插 `LocalMemBar<VEC_STORE, VEC_LOAD>` 保序，同寄存器传值则不需要；⑤**寄存器资源**——UnalignReg 同类（`UnalignRegForLoad`、`UnalignRegForStore` 各自）同时使用超过 4 个即编译失败，两类独立计数（Load 4 + Store 4 合法）；⑥**运行期分支红线**——VF 体内不得出现运行期 `if` 判断（破坏 HWLoop 成环并生成分支代码）；`if constexpr` 编译期分支不受限，运行期条件应改写为 MaskReg/Select 谓词化或提到 VF 外分流。另两条高频归约写法约定（simd_vf reduce）：跨块折叠末块 mask 必须 `MaskMergeMode::MERGING`（默认 ZEROING 会把已折入的列抹成 0）；单标量流式输出用 `StoreUnAlign` 必须与循环末 `StoreUnAlignPost` 成对，漏 Post 丢尾部残留。

## 错误写法

```cpp
// 反例：非法入参（编译期即错，但常见于检视新代码）
// 来源：cann-samples@6e6260c8 1_Features/hardware_features/simd_vf_constraints/src/args.asc:28-47
__simd_vf__ inline void InvalidRefArg(__ubuf__ float* x, float& scale) {}   // 引用
__simd_vf__ inline void InvalidGmPtr(__gm__ float* x) {}                    // GM 指针
__simd_vf__ inline void InvalidStructValue(__ubuf__ float* x, VfParams p) {} // 结构体按值：未定义行为
// 反例：同地址 Store→Load 无 LocalMemBar（membar.asc:80-96 DiffRegNoMemBarVF）
AscendC::Reg::StoreAlign(tmpUbAddr + i * VL_B32, storeReg, mask);
AscendC::Reg::LoadAlign(loadReg, tmpUbAddr + i * VL_B32);   // 读到旧值
// 反例：VF 循环体内运行期 if（红线⑥，破坏 HWLoop 成环）
for (uint16_t i = 0; i < loopCnt; i++) {
    if (hasBeta) { AscendC::Reg::Add(v0, v0, vBeta, mask); }   // 运行期条件
}
```

## 正确写法

```cpp
// 正例：MERGING 末块 mask + StoreUnAlign/StoreUnAlignPost 成对
// 来源：cann-samples@6e6260c8 2_Performance/simd_vf_story/reduce/src/reduce_sum_ar_binary.asc
AscendC::Reg::Add(c0, c0, c2, fullMask);
AscendC::Reg::Add<float, AscendC::Reg::MaskMergeMode::MERGING>(c1, c1, c3, lastMask);
    // 末块 padding 用 MERGING+lastMask 屏蔽：mask 外保留 c1 原值，不污染已折入列
AscendC::Reg::Reduce<AscendC::Reg::ReduceType::SUM>(outReg, c0, fullMask);
AscendC::Reg::StoreUnAlign(zAddr, outReg, unalignAcc, 1);  // 追加 1 标量，zAddr 自动后移
// 行循环结束后：
AscendC::Reg::StoreUnAlignPost(zAddr, unalignAcc, 0);      // 冲刷不足一个 block 的残留
// 正例：编译期分支用 if constexpr（红线⑥合规形态）
// 摘自 cann/ops-nn batch_norm_v3/op_kernel/arch35/batch_norm_v3_block_split_r.h:490
if constexpr (CALC_VAR) {
    LoadAlign(saveMean, ((__ubuf__ float*)batchMeanInUbAddr + aLoopOffset));
}
```

**形态对照**：生产仓（ops-nn/ops-transformer 的 arch35 代码）常用 `__VEC_SCOPE__` 块 + `AscendC::MicroAPI` 而非 `__simd_vf__`/`asc_vf_call`（如 batch_norm_v3 的 block_split_r.h）。`__VEC_SCOPE__` 块视同 VF 体，本库 VF 系列检查点同样适用；它更接近直调形态（块内 LocalMemBar 合法可用），asc_vf_call 专属条目（入参传递约束②、调用边界屏障语义 PRC-VF-006）不套用。检视时两套锚点都要扫：`__simd_vf__`/`asc_vf_call` 与 `__VEC_SCOPE__`/`MicroAPI`。

## 识别方法

- 看什么：`__simd_vf__` 签名的每个入参类型；VF 内的函数调用；循环体内 break/边界改写；**VF 体内的 `if` 语句（区分是否 `if constexpr`）**；同地址 Store→Load 对与 LocalMemBar；UnalignReg 同时使用数；折叠归约的末块 mask 模式；StoreUnAlign 与 StoreUnAlignPost 的配对。
- 命中条件：违反上述任一条即为正确性 finding（优先级高于性能类）；MERGING/StoreUnAlignPost 两条在跨块折叠、单标量流式输出场景下逐一核对。
- 误报边界：①同寄存器传值（Store 后直接用原寄存器继续算，不回读 UB）不需要 LocalMemBar（membar.asc SameRegNoMemBarVF 正例）；②asc_vf_call 形态下"缺 LocalMemBar"的稳妥修复是拆成两个 asc_vf_call（靠调用边界同步）；asc_vf_call 内已有的 LocalMemBar 不得直接判死锁——官方 membar.asc 有含 LocalMemBar 且经 asc_vf_call 启用的正例，死锁仅在 softmax 大合并 VF 有实例（证据源冲突详见 PRC-VF-006）；③末块 mask 用默认 ZEROING 在"mask 恒定且 Store 用同一 mask"的 ra 轴场景是正确的（reduce_sum_ra_baseline 注释）——只有折叠进已有累积值时才必须 MERGING；④structured binding/模板常量入参等编译器能接受的形态以能否编过为准，不臆断；⑤`if constexpr` 与模板参数分支是红线⑥的合规形态，不得报出；运行期条件已谓词化（MaskReg/Select）的也不算违反。

## 证据要求

- 命中的文件:行号与摘录，指明违反的具体约束条目。
- LocalMemBar 类 finding 须同时给出调用形态证据（asc_vf_call/直调）与地址相同的依据。
- MERGING/Post 类 finding 须给出数据流推导：哪些 lane/哪段残留会被抹掉或丢失。

## 参考

- cann-samples@6e6260c8：`Samples/1_Features/hardware_features/simd_vf_constraints/`（README 约束总表 + src/args.asc、asc_vf_call.asc、hwloop.asc、membar.asc、hwlimits_*.asc 正反例）
- `Samples/2_Performance/simd_vf_story/reduce/src/reduce_sum_ar_binary.asc`（MERGING/StoreUnAlign 约定）
- 关联：PRC-VF-004（HWLoop 成环细则）、PRC-VF-006（asc_vf_call 屏障）、PRC-VF-009（Store mask 防脏写）

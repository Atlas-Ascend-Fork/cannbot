---
id: PRC-VF-006
name: asc_vf_call 屏障语义与跨趟数据可见性
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属，A2/A3 不支持 VF；kernel 侧；多趟 VF（reduce→broadcast 类）代码
status: ready
---

# PRC-VF-006：asc_vf_call 屏障语义与跨趟数据可见性

## 知识点

`asc_vf_call` 是一个屏障：调用边界之前的 UB store 对之后的 load 可见，但同一 VF 内部对同地址的 store→load **没有可见性保证**（除非 LocalMemBar）。LocalMemBar 与 asc_vf_call 的兼容性证据源两侧冲突：softmax story 的大合并 VF（Case6）实测经 asc_vf_call 调用时死锁（`7_merged_vf_direct.asc:11` 头注释），但官方约束样例 `simd_vf_constraints/src/membar.asc:188-198` 的 `asc_vf_call<DiffRegWithMemBarVF>`/`asc_vf_call<InterIterWithMemBarVF>` 是含 LocalMemBar 且启用运行的正例——不能把"asc_vf_call 内 LocalMemBar"当普适死锁规则。四条上板结论（softmax_regbase story）：①reduce 标量落 UB 后经 `DIST_BRC_B32` 广播读回，store 与 broadcast-load 必须分属两个 asc_vf_call，违反实测输出全 inf（正确性问题，非性能）；②asc_vf_call 期间 MTE2 被阻塞，VF 内做 prefetch 造不出 MTE2↔V 重叠——dur 不动还多付 prologue（Case4 证伪）；③把 3 趟 VF 合并成 1 个大 VF，屏障时间守恒（1 长 VF≈3 短 VF 总阻塞），且 LocalMemBar 死锁被迫重算，+0.2% 持平（Case6 证伪）；④真正消屏障的路是 `__no_simd_vf_fusion__` + 直接函数调用（不经 asc_vf_call，官方 SoftMaxGenericNDVFImpl 模式），LocalMemBar 生效、多趟连续无屏障，-2.8%（Case7）。

## 错误写法

```cpp
// 反例：同一 VF 内先 StoreUnAlign 归约标量到 UB，紧接 DIST_BRC 读回——无可见性保证，
// softmax 实测输出全 inf（模式示意，对应 1_vf_fused.asc 头注释 L17-19 的禁忌）
__simd_vf__ inline void VfBad(__ubuf__ float* scalarAddr, ...) {
    AscendC::Reg::Reduce<AscendC::Reg::ReduceType::MAX>(tempReg, maxReg, fullMask);
    AscendC::Reg::StoreUnAlign(scalarAddr, tempReg, unalignAcc, 1);
    AscendC::Reg::LoadAlign<float, AscendC::Reg::LoadDist::DIST_BRC_B32>(maxReg, scalarAddr); // 读到旧值
}
```

## 正确写法

```cpp
// 正例：store 与 broadcast-load 分属两个 asc_vf_call，靠调用边界同步
// 来源：cann-samples@6e6260c8 2_Performance/softmax_regbase_story/src/1_vf_fused.asc:139-141
asc_vf_call<VfReduceMax>(xAddr, scalarAddr, n, loopNum, oneRepeatSize);   // 趟内 StoreUnAlign 标量
asc_vf_call<VfSubExpSum>(xAddr, yAddr, scalarAddr, n, loopNum, oneRepeatSize); // 趟首 DIST_BRC 广播
asc_vf_call<VfDiv>(yAddr, scalarAddr, n, loopNum, oneRepeatSize);
// 进阶（消屏障）：__no_simd_vf_fusion__ __simd_vf__ + 直接调用，LocalMemBar 生效
// 来源：同目录 7_merged_vf_direct.asc:27,73
__no_simd_vf_fusion__ __simd_vf__ inline void VfSoftmax2RowDirect(...) {
    // ... AscendC::Reg::LocalMemBar<MemType::VEC_STORE, MemType::VEC_LOAD>();
}
```

## 识别方法

- 看什么：①同一 `__simd_vf__` 内对同一 UB 地址先 Store 后 Load（含 DIST_BRC 读回）且无 LocalMemBar；②经 asc_vf_call 调用的 VF 内出现 `LocalMemBar`；③以"prefetch/重叠 MTE2"为由在 VF 内提前 load 下一 tile 的改动；④以"减少 asc_vf_call 次数"为唯一理由的多趟合并。
- 命中条件：①为正确性 finding，直接命中；②只作风险提示（证据源两侧冲突，见知识点）——须给出调用形态与规模（大合并 VF 更接近 softmax 死锁案例），建议上板确认，不得直接定级为缺陷；③④为无效优化 finding——需指出屏障语义使其收益为零/守恒。
- 误报边界：①`__no_simd_vf_fusion__` + 直接调用形态下 LocalMemBar 合法且是推荐写法，不要当死锁报；②store→load 地址不相交时无可见性问题；③多趟合并若同时消除了重复 load/重算（不只是省 call），需按实际指令数变化评估，不能一律否定；④reduce 结果经寄存器 `Duplicate(dst, srcReg, mask)` 广播（不落 UB）是合法替代路径（6_merged_vf.asc:50），不依赖 UB 可见性。

## 证据要求

- 命中的文件:行号，摘录同 VF 内的 store 与 load 及两者地址关系。
- 对无效优化类 finding：引用屏障语义（asc_vf_call 期间 MTE2 阻塞/屏障时间守恒）说明收益不成立。
- 对死锁风险类提示：给出该 VF 的调用形态证据（asc_vf_call 还是直接调用）及 VF 规模，并注明证据源冲突、需上板确认。

## 参考

- cann-samples@6e6260c8：`Samples/2_Performance/softmax_regbase_story/src/`（1_vf_fused=分趟正例；4_pipeline=prefetch 证伪；6_merged_vf=合并证伪+死锁注释；7_merged_vf_direct=直调正例）
- 关联：PRC-VF-002（Membar 最小化）、PRC-VF-010（LocalMemBar 保序规则）

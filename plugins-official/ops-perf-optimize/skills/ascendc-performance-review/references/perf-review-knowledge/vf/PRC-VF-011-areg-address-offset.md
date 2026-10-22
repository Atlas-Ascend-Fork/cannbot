---
id: PRC-VF-011
name: 地址寄存器（AReg）外提与偏移写法
category: VF
applies_to: dav-3510（Ascend 950PR/950DT）专属；kernel 侧；__simd_vf__ 内的偏移计算、访存指针与 CreateAddrReg 使用
status: ready
---

# PRC-VF-011：地址寄存器（AReg）外提与偏移写法

本条是 AReg 专章：VF 访存地址相关的红线与选型经验集中在此，后续新经验继续往本条追加。

## 知识点

VF 内向量访存地址经地址寄存器（AReg）发射，编译器会尽量把循环不变/线性递增的地址计算外提折进 vag。两类写法直接影响外提与每轮指令数：

1. **偏移类型红线**：VF 内偏移与下标一律用 `uint32_t`（循环变量 `uint16_t`），不要用 `int64_t`。有符号 64 位偏移使编译器需保守处理符号扩展与溢出语义，难以证明地址线性递增，AReg 外提失败→每轮重算地址。UB 容量仅 KB 级，uint32 无溢出风险。
2. **AddrReg vs post-increment 选型**（bnv3 BlockSplitR，A5 上板 3 轮均值）：`CreateAddrReg` 必须写在 index 所在循环体内，**每轮每个 areg 发一条 vag**；post-inc 的地址推进折进 load/store 里零额外指令。判据是**每个 areg 摊到多少次访存**：1~2 次访存共用 1 个 areg → AddrReg 划算（省循环携带指针状态）；同一指针连推 4/8/16 次访存 → post-inc 划算，铺开成 AddrReg 实测回退 +12%~+26%。
3. **VAG 使用细则**（探针实测）：stride 个数必须等于所在循环嵌套深度（少给编译报错）；某维 stride 取 0 合法（该层不参与偏移）；同一 areg 配多个 loop-invariant base 合法；并发 areg 到 8 个开销仍线性（探针口径每 areg 约 +3 指令/轮，其中 1 条是 vag，余为地址生成伴随指令），个数不是约束；stride 单位是元素数；**index 参数按位置绑定由外到内的循环计数器，绑反是静默算错**。

## 错误写法

```cpp
// 反例：VF 内 int64 偏移（依红线描述重构；从 MemBase 侧下沉时易照搬其 int64_t 偏移变量）
__simd_vf__ inline void VfBad(__ubuf__ float* base, uint16_t loopCnt) {
    for (uint16_t i = 0; i < loopCnt; i++) {
        int64_t offset = static_cast<int64_t>(i) * VL_F32;   // int64 阻碍 AReg 外提
        AscendC::Reg::LoadAlign(v0, base + offset);
    }
}
// 反例：单指针连推十几次访存却逐一 CreateAddrReg（bnv3 WelfordFinalize 实测回退 +12~26%）
```

## 正确写法

```cpp
// 正例：uint16 循环变量 + uint32 偏移，地址保持线性递增可外提
// 摘自 cann/ops-nn batch_norm_v3/op_kernel/arch35/batch_norm_v3_block_split_r.h:487-494
for (uint16_t aIndex = 0; aIndex < aLoopCount; aIndex++) {
    uint32_t aLoopOffset = aIndex * VL_F32;
    pregLoop = AscendC::Reg::UpdateMask<float>(sreg0);
    __ubuf__ float* quotPtr = (__ubuf__ float*)(tmpMeanLocal + aLoopOffset);
    __ubuf__ float* remPtr  = (__ubuf__ float*)(tmpMeanLocal + remainderOffset + aLoopOffset);
    ...
}
```

## 识别方法

- 看什么：①VF 体内 `int64_t`/`long`/`uint64_t` 类型的偏移与下标变量，含从 tiling 字段直接取的 64 位值参与 VF 地址计算（32 位有符号 `int` 另行记建议项，见命中条件）；②`CreateAddrReg` 的个数与每个 areg 服务的访存次数（数同一循环体内经它发射的 Load/Store）；③vag 的 stride 参数个数与循环嵌套深度、index 绑定顺序。
- 命中条件：①VF 内出现 64 位偏移（含无符号 uint64）即命中红线；32 位有符号 `int` 不按红线报（signed 溢出是 UB，编译器反而可据此证明线性外提），只作"统一用 uint32_t"的风格建议；②单指针连推 ≥4 次访存却用 AddrReg 逐一发射（或反向：1~2 次访存却维护 post-inc 指针状态导致寄存器 copy）报选型建议；③stride 与嵌套深度不匹配、index 绑定疑似反序报正确性风险。
- 误报边界：①**本条只管 VF 内 UB 侧偏移**；kernel 标量域的 GM 偏移是另一套规则——大 shape 下 GM 偏移必须用 int64 防 2^32 回绕（uint32 GM 偏移曾致越界崩溃，见 KvRmsNormRopeCache 案例），不得反向报成"改 uint32"；②`if constexpr` 分支内的偏移常量化后不参与运行期计算，不命中；③index 绑定顺序仅在多维 vag 且各维长度不同时可静态判断，拿不准时建议用"非对齐尾块 shape"上板验证而非直接断言。

## 证据要求

- 类型红线：偏移变量声明处文件:行号 + 参与地址计算的路径摘录。
- 选型类：该循环体内 areg 个数、每 areg 访存次数统计；给出建议形态（AddrReg 或 post-inc）及判据引用。
- vag 细则类：stride 参数列表与循环嵌套结构的对照摘录。

## 参考

- 编码红线来源：算子团队检视经验（2026-08-25 用户提供）
- AddrReg/post-inc 判据与 VAG 细则：batch_norm_v3 BlockSplitR A5 上板 A/B 与探针标定（2026-07）
- 正例：cann/ops-nn `batch_norm_v3/op_kernel/arch35/batch_norm_v3_block_split_r.h`
- 关联：PRC-VF-004（HWLoop 与循环变量类型）、PRC-VF-005（常量外提）、PRC-VF-010（合法性约束，含运行期 if 红线）

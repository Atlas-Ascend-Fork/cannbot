---
id: PRC-SCA-003
name: 热路径成员变量局部化
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；性能数字来自 Ascend 950（scalar_story）
status: ready
---

# PRC-SCA-003：热路径成员变量局部化

## 知识点

scalar_story 对 8000+ 用例的统计表明，ScalarBound 的主因是 Load/Store 指令占比普遍超过 30%（构成含寄存器 spill、成员/结构体访存、指针链解引用等，并非全是 spill）——消除 ScalarBound 的关键在减少 Load/Store，而非减少标量计算指令。成员变量正是 Load/Store 的重灾区：它必须经 `this` 指针+偏移访问；别名分析无法排除其他指针修改它的可能，每次读取都可能重新 Load；跨（非内联）函数调用后缓存值作废必须重载。未取地址的局部变量则可长驻寄存器。scalar_story 中 FIA 仅把 `constParam` 一处从成员变量改为局部变量，Cube 核 Scalar 耗时降 15%，dcache miss 完全消除。配套原则：变量定义贴近使用位置——活跃期越短占用寄存器越短，越不易挤出 spill。

## 错误写法

```cpp
// 反例（摘自 scalar_story README）：高频访问的参数包是类成员，经 this+偏移访问
template <typename PFAT>
class PromptFlashAttentionNormalBNS1PreloadBasicApi {
protected:
    ConstParam constParam;   // 热路径频繁读，每次都可能重新 Load
};
```

## 正确写法

```cpp
// 正例（摘自 scalar_story README）：改为函数内局部变量，可长驻寄存器
template <typename PFAT>
__aicore__ inline void PromptFlashAttentionNormalBNS1PreloadBasicApi<PFAT>::Init()
{
    ConstParam constParam;   // 未取地址的局部变量
    ...
}
```

## 识别方法

- 看类定义与热函数体：热循环内高频读取的参数（shape/步长/循环边界/常量参数包）是否为成员变量；该参数是否只在单个函数（或少数内联函数）内使用。两者同时成立即命中。
- 加重信号：函数顶部集中定义、生命周期贯穿整个大函数的"上帝参数对象"；成员变量在循环内被反复读但从不写。
- 误报边界：确需跨多个非内联函数共享状态的成员不属于本条（局部化会破坏语义）；只在 Init 读一两次的成员收益可忽略；编译器可证明 const 且已被常量传播的成员不再产生 Load（有反汇编/仿真证据时不报）。

## 证据要求

- 命中成员变量的类定义与热路径读取点的文件:行号与摘录，说明访问频次（位于哪层循环）。
- 说明该成员仅在单函数（或内联链）内使用、可安全局部化的依据。
- 有条件时附 Load/Store 占比或 Scalar bound 的 profiling 数据佐证。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §5.1.1 手段三、§7.4、§7.5（Ascend 950 实测）
- 相关条目：PRC-SCA-005（指针链/结构体布局同属减 Load/Store）、PRC-SCA-004（TilingData 拷贝）

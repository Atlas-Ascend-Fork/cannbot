---
id: PRC-SCA-009
name: 缩减 Tensor ShapeInfo 维度
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；限不使用（或少用）ShapeInfo 功能的算子；官方文档定性结论（平台未标注）
status: ready
---

# PRC-SCA-009：缩减 Tensor ShapeInfo 维度

## 知识点

Tensor 的 ShapeInfo 默认按最大 8 维预留，即使算子完全不用 ShapeInfo 功能，也会占用栈空间、增加标量指令并提高缓存失效率——属于每个 Tensor 都要付的隐性头开销。在包含 kernel 头文件之前 `#define K_MAX_SHAPE_DIM 0`（不使用 ShapeInfo 时设 0，需要时按实际最大维数设更小值），可缩减栈空间、减少标量指令。官方文档为定性结论（"经实测可缩减栈空间、提升性能"），无量化数字。

## 错误写法

```cpp
// 反例（依官方文档示例重构）：未定义 K_MAX_SHAPE_DIM，ShapeInfo 按默认 8 维预留
#include "kernel_operator.h"   // 默认 K_MAX_SHAPE_DIM=8，每个 Tensor 白付栈与标量开销

extern "C" __global__ __aicore__ void my_kernel(GM_ADDR x, GM_ADDR y) {
    // kernel 全程未使用 ShapeInfo 相关功能
}
```

## 正确写法

```cpp
// 正例（依官方文档示例重构）：包含 kernel 头文件之前定义，宏必须先于 include 生效
#define K_MAX_SHAPE_DIM 0      // 不使用 ShapeInfo 功能时设 0
#include "kernel_operator.h"

extern "C" __global__ __aicore__ void my_kernel(GM_ADDR x, GM_ADDR y) {
    ...
}
```

## 识别方法

- 全 kernel 源文件（含被 include 的 .h）搜索 `K_MAX_SHAPE_DIM`：未定义即默认 8 维。
- 再确认算子是否实际使用 ShapeInfo 功能（SetShapeInfo/GetShapeInfo 及依赖 shape 信息的高阶接口）；完全不用则命中"应设 0"，用到但维数远小于 8 则命中"应设为实际最大维数"。
- 注意宏位置：定义在 kernel 头文件 include 之后不生效，形同未定义，同样命中。
- 误报边界：已正确定义且先于 include 的不报；算子确实需要 8 维 shape 语义的不报；本条收益为栈空间/标量指令级别，对头开销不敏感的大 shape 长耗时算子标注为低优先级。

## 证据要求

- kernel 源文件 include 区的文件:行号与摘录，证明未定义 `K_MAX_SHAPE_DIM`（或定义位置在 include 之后）。
- 全文件检索结果，证明未使用 ShapeInfo 相关接口（或列出实际最大维数 < 8 的依据）。

## 参考

- 官方文档：atlas_ascendc_best_practices_10_0019（通过缩减 Tensor ShapeInfo 维度，优化栈空间）
- 相关条目：PRC-SCA-004（TilingData 瘦身，同属"少付隐性头开销"）、PRC-SCA-005（栈占用与 spill 的关系）

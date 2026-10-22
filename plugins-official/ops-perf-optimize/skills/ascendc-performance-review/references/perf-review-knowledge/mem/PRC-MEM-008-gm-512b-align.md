---
id: PRC-MEM-008
name: GM 地址 512B 对齐
category: MEM
applies_to: 收益数字明确来自 Atlas A2（官方 0014：32B 对齐仅为 512B 对齐带宽的 70%；FA 案例 workspace 对齐 +45%）；dav-3510 上的量化收益未见官方数据，待上板验证；kernel+tiling/host 侧（workspace 划分多在 host）
status: draft
---

# PRC-MEM-008：GM 地址 512B 对齐

## 知识点

GM 访问在处理器内部按对齐粒度成组传输，起始地址非 512B 对齐时同一笔逻辑搬运被拆成碎片事务，带宽效率下降。官方 A2 实测：32B 对齐场景带宽只有 512B 对齐的 70%。FlashAttention 调优案例（A2）中 workspace 各段未对齐导致 FixPipe 128B 碎片搬运、占比高达 81%，用 ADDR_ALIGN_SIZE 宏对齐 mm1/mm2/mm3 各段偏移后提升 45%。多数命中点在 host 侧 workspace/多段输出的偏移划分——各段大小非 512B 倍数时，后续段起始地址全部失对齐。

## 错误写法

```cpp
// 反例（依官方 FA 案例 10_0038 重构）：workspace 按裸大小顺排，
// mm1Size 非 512B 倍数 → mm2 段起始地址失对齐，逐段传染
uint8_t *mm1Ws = workspace;
uint8_t *mm2Ws = mm1Ws + mm1Size;
uint8_t *mm3Ws = mm2Ws + mm2Size;
```

## 正确写法

```cpp
// 正例（依官方 FA 案例 10_0038 重构）：每段偏移向上取整到 512B
constexpr uint64_t ADDR_ALIGN_SIZE = 512;
auto AlignUp = [](uint64_t x) { return (x + ADDR_ALIGN_SIZE - 1) / ADDR_ALIGN_SIZE * ADDR_ALIGN_SIZE; };
uint8_t *mm1Ws = workspace;                     // 基址由框架保证对齐
uint8_t *mm2Ws = mm1Ws + AlignUp(mm1Size);
uint8_t *mm3Ws = mm2Ws + AlignUp(mm2Size);
```

## 识别方法

在被检视源码中看：

1. host 侧 workspace/输出的分段偏移计算：偏移由若干"元素数×dtype 大小"直接累加、无 512B 取整，且段大小不能静态证明是 512B 倍数，命中。
2. kernel 侧 `SetGlobalBuffer(base + offset)` 的 offset 表达式：含奇数行长、非对齐 stride（如 `blockIdx*rows*17*sizeof(half)`）时命中。
3. 高频搬运路径优先：只对主数据通路（每次迭代都走的 DMA）报，一次性的小搬运不值得报。

误报边界：外部输入张量的基址由调用方决定，kernel 无法控制，不报（可提示 host 层约束）；偏移可静态证明为 512B 倍数（如行长 256×fp32）的不报；本条收益数字全部来自 A2，dav-3510 的对齐粒度与惩罚幅度未见官方文档数据——在 950 检视中只按"机制方向正确"报，量化收益标注待验证，不引用 70%/45% 作为 950 预期。

## 证据要求

finding 必须给出：

- 偏移计算处的文件:行号与摘录，及"非 512B 倍数"的推导（代入实际 shape/dtype）；
- 该地址所在通路的搬运频率（主循环内/一次性）；
- 架构声明：目标是 A2 则可引用官方数字，是 dav-3510 则注明收益待上板验证。

## 参考

- 官方：`atlas_ascendc_best_practices_10_0014`（A2，70% 数据）、`10_0038`/`10_0040`（FA 案例 workspace 对齐 +45%，A2）。

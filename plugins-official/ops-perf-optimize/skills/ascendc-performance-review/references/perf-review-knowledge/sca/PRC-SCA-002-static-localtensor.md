---
id: PRC-SCA-002
name: 编译期已知布局用静态 LocalTensor
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；限 buffer 数量/大小/偏移在编译期完全确定的场景；性能数字来自 Ascend 950（scalar_story）
status: ready
---

# PRC-SCA-002：编译期已知布局用静态 LocalTensor

## 知识点

`TPipe::InitBuffer` 是通用 buffer 管理框架，内部含动态分配、状态追踪、条件判断与队列操作，这些通用能力都由 Scalar 执行。当 buffer 布局在编译期完全确定（数量、大小、偏移均已知，无动态分配需求）时，这套通用管理是纯头开销：可改用 `LocalTensor<T>(TPosition, offset, size)` 按常量偏移直接构造，跳过 InitBuffer。scalar_story 中 FusedInferAttentionScore 仅改 L1 层即省头开销约 900 cycle、端到端约 0.5us。

## 错误写法

```cpp
// 反例（摘自 scalar_story README）：布局编译期已知，仍走 InitBuffer 通用管理
for (int32_t i = 0; i < L1KVNumSacler; ++i) {
    pipe->InitBuffer(tmpBufL1KV[i], KV_L1_SIZE);
    L1KVTensorPingPong[i] = tmpBufL1KV[i].template Get<T>();
}
pipe->InitBuffer(tmpBufL1Q, Q_L1_SIZE);
L1QTensorPingPong = tmpBufL1Q.template Get<T>();
```

## 正确写法

```cpp
// 正例（摘自 scalar_story README）：TPosition 与常量偏移直接静态构造
L1KVTensorPingPong0 = LocalTensor<T>(TPosition::B1, (Q_L1_SIZE + 2 * P_L1_SIZE) * 2, KV_L1_SIZE);
L1KVTensorPingPong1 = LocalTensor<T>(TPosition::B1, (Q_L1_SIZE + 2 * P_L1_SIZE + KV_L1_SIZE) * 2, KV_L1_SIZE);
L1QTensorPingPong  = LocalTensor<T>(TPosition::A1, 0, Q_L1_SIZE);
```

偏移规则：起始地址 = 前序所有 buffer 大小之和 ×2（×2 因 ping-pong 双缓冲）。手工布局须自行保证不重叠、不越界。

## 识别方法

- 看 Init 阶段：所有 `InitBuffer` 调用的大小参数是否全为编译期常量、buffer 个数是否固定、后续是否无动态复用/重划分。全部成立且算子对头开销敏感（小 shape / 微秒级）才算命中。
- 误报边界：布局依赖 tiling 运行期字段（大小/个数随 shape 变）时不可静态化，不报；InitBuffer 只在 Init 执行一次、算子端到端为百微秒级时收益（~900 cycle 量级）可忽略，属低价值 finding；使用 TQue 队列调度能力（EnQue/DeQue 状态机）的 buffer 不能简单替换，仅 TBuf 类纯静态 buffer 适用。

## 证据要求

- Init 函数的文件:行号与摘录，逐一列出各 InitBuffer 的大小实参并证明均为编译期常量。
- 说明该算子头开销敏感性（典型 shape 下端到端量级），否则标注为低优先级。
- 排除依据：确认无运行期动态布局需求、无依赖 TQue 调度语义。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §5.1.1 手段二（Ascend 950 实测）
- 相关条目：PRC-SCA-004（同属头开销削减）、PRC-SCA-008（TPipe 本身的创建位置）

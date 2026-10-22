---
id: PRC-SCA-008
name: TPipe 避免在业务类内创建初始化
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；性能数字来自官方文档（平台未标注）
status: ready
---

# PRC-SCA-008：TPipe 避免在业务类内创建初始化

## 知识点

TPipe 作为业务类的成员在类内创建并初始化，会让编译器对该类采取保守策略，无法对相关 Scalar 变量做常量折叠/常量传播，Scalar 指令随之变多。推荐把 TPipe 对象放在 kernel 入口（业务类外）创建，以指针传入业务类，使 TPipe 的内存空间独立于业务类对象。官方文档实测：平均耗时 281us → 236us（约 -17%），Scalar 时延占比 21% → 17%。

## 错误写法

```cpp
// 反例（依官方文档示例重构）：TPipe 是业务类成员，在类内创建初始化
class KernelExample {
public:
    __aicore__ inline void Init(GM_ADDR x, GM_ADDR y) {
        pipe.InitBuffer(inQueueX, BUFFER_NUM, TILE_SIZE);
    }
private:
    TPipe pipe;            // 与业务成员同居一个对象，编译器保守放弃常量折叠
    TQue<TPosition::VECIN, BUFFER_NUM> inQueueX;
};
```

## 正确写法

```cpp
// 正例（依官方文档示例重构）：kernel 入口创建 TPipe，指针传入业务类
class KernelExample {
public:
    __aicore__ inline void Init(GM_ADDR x, GM_ADDR y, TPipe* pipeIn) {
        pipe = pipeIn;
        pipe->InitBuffer(inQueueX, BUFFER_NUM, TILE_SIZE);
    }
private:
    TPipe* pipe;           // 仅持有指针，TPipe 内存独立于业务类
};

extern "C" __global__ __aicore__ void example_kernel(GM_ADDR x, GM_ADDR y) {
    TPipe pipe;            // 在 kernel 入口（类外）创建
    KernelExample op;
    op.Init(x, y, &pipe);
}
```

## 识别方法

- 看业务类定义：是否存在 `TPipe` 类型（非指针/引用）的成员变量；kernel 入口是否直接构造业务类而 TPipe 藏在类内。
- 命中条件：TPipe 成员与其他参与 Scalar 计算的成员同处一个类。
- 误报边界：业务类只持 `TPipe*` 指针、对象在 kernel 入口创建的即为正确写法，不报；多个业务类共用入口同一 TPipe 指针属正常复用；收益体现在 Scalar 指令减少，若算子已远非 Scalar bound，标注为低优先级而非缺陷。

## 证据要求

- 业务类中 TPipe 成员定义与 kernel 入口构造点的文件:行号与摘录。
- 说明该类中还有哪些常量语义成员会因此失去常量折叠机会。
- 排除依据：确认成员是 TPipe 对象本体而非指针。

## 参考

- 官方文档：atlas_ascendc_best_practices_10_0028（避免 TPipe 在对象内创建和初始化）
- 相关条目：PRC-SCA-002（静态 LocalTensor）、PRC-SCA-005（结构体布局阻碍常量传播的同族机制）

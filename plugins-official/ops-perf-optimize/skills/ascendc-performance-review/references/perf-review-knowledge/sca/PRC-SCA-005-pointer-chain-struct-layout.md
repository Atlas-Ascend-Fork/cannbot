---
id: PRC-SCA-005
name: 指针链与结构体布局（多级解引用/结构体内数组/超大结构体）
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；性能数字来自 Ascend 950（scalar_story，QuantBatchMatmul 实践）
status: ready
---

# PRC-SCA-005：指针链与结构体布局（多级解引用/结构体内数组/超大结构体）

## 知识点

三个同根问题，根都在"编码方式阻碍编译器寄存器分配与常量传播"，直接后果是 Load/Store 膨胀——scalar_story 8000+ 用例统计表明 Load/Store 占比 >30%（含 spill 与本条的成员/结构体/指针链访存）正是 ScalarBound 主因。(1) 多级指针解引用（最高发实例：tilingdata 指针存类成员，专项判据见 PRC-SCA-004 形态③）：每级一条 Load 且前级结果是后级地址，延迟串行累加，别名问题又使每次访问都重新 Load；改值类型聚合（tuple/Shape）后访问从 2 次 Load 降为 1 次。(2) 结构体内数组经动态下标访问：编译器无法确定下标，保守放弃**整个结构体**所有成员的常量传播/折叠，且被包含时向父结构体传播污染——症状是编译期已知的常量（如 TPosition）运行时仍动态取值判断；拆成独立标量成员后（配合其他手段）QBMM Scalar 平均 -50%。(3) 超大结构体：进不了寄存器只能落栈，访问成员皆 Load/Store，指针传递又引入别名问题；建议 <64B（1 cacheline）、最大 128B，按功能拆小、热路径用局部副本。

## 错误写法

```cpp
// 反例（摘自 scalar_story README）：指针成员 2 次 Load；结构体内数组毁掉全结构体常量传播
class MatMulPerBlock {
protected:
    const TCubeTiling *matmulTiling_;              // 多级解引用
    event_t eventIdV2Mte2[2] = {EVENT_ID0, EVENT_ID1};  // 数组 + 动态下标
    uint16_t x1ScalePingPongID_ = 0;
};
isTailBL1 = (kInner + minStepK_) >= matmulTiling_->Kb;      // Load 指针 + Load Kb
SetFlag<HardEvent::V_MTE2>(eventIdV2Mte2[x1ScalePingPongID_]); // 动态下标访问
```

## 正确写法

```cpp
// 正例（摘自 scalar_story README）：值类型聚合 1 次 Load；数组拆为直接用 pingpong 标量
using TupleShape = AscendC::Shape<int64_t, int64_t, int64_t>;  // m,n,k
TupleShape problemShape_;          // 值类型成员
Get<MNK_K>(problemShape_);         // 1 次 Load

uint16_t x1ScalePingPongID_ = 0;   // 去掉 event_t 数组
SetFlag<HardEvent::V_MTE2>(static_cast<event_t>(x1ScalePingPongID_));  // 整数须显式转 event_t
x1ScalePingPongID_ ^= 1;
```

## 识别方法

- 多级解引用：热路径中 `ptr->member`（ptr 为指针成员）或 `a->b->c` 链式访问；参数在 kernel 生命周期内只读却经指针反复取。
- 结构体内数组：类/结构体同时含数组成员与需常量优化的其他成员，且数组用运行期变量下标访问（ping-pong id、循环变量）。
- 超大结构体：sizeof 明显超 128B 的参数结构体在热路径整体传递/整体拷贝。
- 误报边界：数组用编译期常量下标访问不触发污染；数组独立存在（不与需优化成员同结构体）影响有限；只在 Init 走一次的解引用链收益可忽略；参数确需运行期可变（非只读）时不能改值聚合。

## 证据要求

- 命中模式的文件:行号与摘录（指针成员定义+热路径访问点 / 数组成员定义+动态下标访问点 / 结构体定义与 sizeof 估算）。
- 说明访问点位于哪层热循环；数组场景说明同结构体内还有哪些成员会被污染。
- 排除依据：确认参数只读可聚合 / 下标确为运行期变量。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §5.2.1 手段二三、§7.1、§7.6、§7.7（Ascend 950 实测）
- 相关条目：PRC-SCA-003（成员变量局部化）、PRC-SCA-004（TilingData 瘦身）

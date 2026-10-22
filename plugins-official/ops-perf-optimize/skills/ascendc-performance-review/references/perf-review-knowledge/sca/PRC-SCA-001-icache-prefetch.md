---
id: PRC-SCA-001
name: icache 预取消除取指断流
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧；适用于代码体量超 I-Cache 的算子（大模板类/大循环体）；性能证据来自 Ascend 950（scalar_story）
status: ready
---

# PRC-SCA-001：icache 预取消除取指断流

## 知识点

Scalar 单元从 I-Cache 取指，代码体量超过 I-Cache 容量时，循环内调用大函数或跨大段代码回跳会触发 icache miss，Scalar 停下来等待指令加载（数十到数百 cycle），期间无法向 Cube/Vector/MTE 分发指令，全流水断流。诊断特征：PC-vs-Cycle 折线图中出现水平线段（PC 不变），线段越长等待越久——但 PC 停驻也可能是 WaitFlag/同步等待或长延迟标量 load，归因取指前须先排除同步点。scalar_story 中 FusedInferAttentionScore 在循环入口/大函数调用前 1-2 个基本块插入预取后，图上 miss 段完全消除。

## 错误写法

```cpp
// 反例：循环体内反复调用体量很大的函数（如数百行的 Iterate/ProcessTile），
// 循环回跳与函数调用跨越的代码范围超过 I-Cache 容量，每轮都可能触发 icache miss。
while (ProcessNextTile()) {   // 大函数，无任何预取提示
    ComputeOneTile();         // 又一个大函数
}
```

## 正确写法

```cpp
// 正例：在循环入口 / 大函数调用前 1-2 个基本块处插入 icache 预取，
// 提前把将要执行的指令段载入 I-Cache（AscendC 提供 ICachePreLoad 类预取
// 接口；scalar_story README 未给出具体调用形式，落地时以官方 API 文档为准）。
// <此处插入 icache 预取>
while (ProcessNextTile()) {
    ComputeOneTile();
}
```

注意：预取位置与预取量需按实际代码布局调优——过早浪费带宽，过晚消不掉 miss。

## 识别方法

- 静态特征：kernel 单个类/函数展开后代码体量明显偏大（大模板类多实例化、循环体内调用数百行函数、深层 if/else 状态机），且热循环没有任何 icache 预取。
- 动态确认（强证据）：msprof/cannsim 的 PC-vs-Cycle 图出现长水平段；或 profiling 显示 Scalar bound 且 Load/Store 占比不高（排除 spill 主因后剩余的 Scalar 停顿多为取指/分支）。
- 误报边界：代码体量小于 I-Cache 的算子插预取无收益纯属噪声，不应报；仅凭"函数长"不足以命中，需结合体量估计或 PC-Cycle 证据；预取本身写错位置（过早/过晚）不属于本条，属于调参问题。

## 证据要求

- 命中热循环的文件:行号与摘录，说明循环体内调用链展开后的代码体量为何可能超 I-Cache（列出被调大函数及其规模）。
- 若有 profiling：PC-vs-Cycle 图水平段截图/数据，或 Scalar bound 且非 Load/Store 主因的流水数据。
- 排除依据：说明该算子不是小体量 kernel（否则视为误报）。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §5.1.1 手段一、§6.2 Step 4b（Ascend 950 实测）
- 相关条目：PRC-SCA-006（循环拆分需权衡代码膨胀反触 icache miss）、PRC-SCA-007（状态机大函数本身是 icache miss 来源）

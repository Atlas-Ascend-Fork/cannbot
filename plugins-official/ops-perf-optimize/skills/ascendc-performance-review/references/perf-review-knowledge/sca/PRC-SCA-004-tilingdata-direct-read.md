---
id: PRC-SCA-004
name: TilingData 直读与结构瘦身
category: SCA
applies_to: 标量机制通用（各代 AI Core）；kernel 侧（直读）+ host/tiling 侧（结构定义瘦身）；直读数字来自 Ascend 950（scalar_story），瘦身来自官方文档（平台未标注）
status: ready
---

# PRC-SCA-004：TilingData 直读与结构瘦身

## 知识点

Kernel 启动时把入参指向的 tilingdata 整块拷贝到栈上对象是惯例写法，但拷贝本身就是成串 Load/Store（scalar_story 统计：Load/Store>30% 是 ScalarBound 主因），TilingData 越大头开销越重。两个互补手段：(1) kernel 侧免拷贝——经入参指针直读字段，scalar_story 两用例软件头开销 -54.6% / -48.7%；(2) 定义侧瘦身——删除可由框架接口（SetBlockDim/GetBlockNum 等）获取的冗余字段、按实际取值范围选小类型（uint8_t/uint32_t 替代一律 uint64_t）、合理排布成员减少 8 字节补齐产生的 padding（官方示例：排布不当补 10 字节 vs 合理排布补 2 字节）。拷贝耗时为 us 级，小 shape 场景收益明显。

第三个命中形态是直读的**落点错误**——不整块拷栈了，但把 tilingdata 指针（或栈上副本）存成类成员：成员指针经 `this` 两级 Load（先 Load 指针再 Load 字段），且指针存入成员即逃逸，别名分析无法排除其他写入，编译器放弃"只赋值一次→值驻留寄存器"的常量折叠/常量传播（编译器前提见官方 0028 编译器背景知识段；TPipe 场景的同族机制见 PRC-SCA-008），热路径每次使用都重新 Load——整块拷贝的 Load/Store 只是从入口挪进了热路径。直读必须落在**局部指针**上，热字段一次性取到局部变量（联动 PRC-SCA-003），指针链/别名机制详见 PRC-SCA-005。

## 错误写法

```cpp
// 反例（依素材描述重构）：整块拷到栈 + 定义冗余肥大
struct BigTilingData {
    uint64_t blockNum;      // 冗余：GetBlockNum() 可得
    uint64_t bufferNum;     // 取值 1~4，却用 uint64_t
    uint64_t loopCount;
    ...                     // 数十个字段，排布随意产生 padding
};
BigTilingData td = *reinterpret_cast<const __gm__ BigTilingData*>(tiling); // 整块拷栈
```

## 正确写法

```cpp
// 正例（依素材描述重构）：指针直读 + 小类型紧凑排布
struct SlimTilingData {
    uint32_t loopCount;
    uint8_t  bufferNum;     // 按实际范围选型；同宽字段相邻排布减 padding
};
auto td = reinterpret_cast<const __gm__ SlimTilingData*>(tiling);
uint32_t loops = td->loopCount;   // 只读用到的字段，无整块拷贝
```

```cpp
// 反例（形态③）：指针存成类成员——热路径 this->td_-> 两级 Load，字段值不驻留寄存器
__aicore__ inline void Init(GM_ADDR tiling) {
    td_ = reinterpret_cast<const __gm__ SlimTilingData*>(tiling);   // 成员指针，逃逸
}
// 热路径每轮：if (i < this->td_->loopCount) ...
private:
    const __gm__ SlimTilingData* td_;
```

形态③的正确写法即上方正例：直读落局部指针，热字段一次取到局部变量（`const uint32_t loops = td->loopCount;`）后参与常量传播。

## 识别方法

- kernel 侧：入口处是否有 tilingdata 结构体整体赋值/逐字段全量拷贝到栈对象（含展开为整块拷贝的宏），而后续只用其中少数字段。
- kernel 侧（形态③）：`Init` 把 tilingdata 指针 `reinterpret_cast` 后赋给**类成员**（或把栈副本存成员），热路径经 `this->td_->字段` 取数——不因"没整块拷贝"而放过；改法是局部指针直读 + 热字段局部变量化（联动 PRC-SCA-003/005）。
- 定义侧：TilingData 定义中是否存在框架接口可得的字段、明显超出取值范围的宽类型、异宽字段交错排布造成 padding。
- 命中条件：TilingData 较大（字段多）或算子为小 shape/微秒级、头开销占比敏感。
- 误报边界：TilingData 本身很小（几十字节）且算子端到端毫秒级时收益可忽略；拷贝到栈后被高频写改（作可变状态用）的不能简单改直读；直读要求字段访问模式对 GM 读友好，逐字段散读次数极多时需结合实测判断；形态③中指针虽存成员、但热路径已把用到的字段一次性取成局部变量（循环内不再经成员指针取数）的，记录不报。

## 证据要求

- kernel 入口拷贝语句 / TilingData 定义的文件:行号与摘录；列出冗余字段及其框架替代接口、可缩窄字段及实际取值范围依据（来自 tiling 实现）。
- 说明该算子头开销敏感（典型 shape 端到端量级）。

## 参考

- cann-samples：`Samples/2_Performance/scalar_story/README.md` §5.1.1 手段四（Ascend 950 实测）
- 官方文档：atlas_ascendc_best_practices_10_0018（限制 TilingData 结构大小）
- 官方文档：atlas_ascendc_best_practices_10_0028 编译器背景知识段（常量折叠/传播的前提：变量只初始化/赋值一次、对象内存无被外部污染风险；该页正文是 TPipe 场景，对应 PRC-SCA-008）
- 相关条目：PRC-SCA-002（头开销）、PRC-SCA-003（减 Load/Store）、PRC-SCA-005（大结构体）

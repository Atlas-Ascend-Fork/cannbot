---
id: PRC-MEM-011
name: 核间负载均衡、切分维度与模板选路判据
category: MEM
applies_to: 机制通用（各代 AI Core）；tiling/host 侧为主，kernel 侧只看行范围计算；需先按 PRC-ARCH-002 取证核数；性能数字来自 dav-3510 实测（切 R 模板判据改造 13~21x；BlockSplitR 均衡择优 -9.1%）
status: ready
---

# PRC-MEM-011：核间负载均衡、切分维度与模板选路判据

## 知识点

分核的收益上限由**关键路径**决定，即 `max(单核工作量)`，不是启动了多少个核。PRC-MEM-002 只管"有没有分核"；已分核之后关键路径是否贴近理想值 `总工作量 / 核数`，由本条负责。四种命中形态：

- **形态① 切分维度太粗**：只切最外层维度，而该维度长度小于核数，剩余维度未参与切分，核直接闲置。补切一个维度即可把关键路径成倍压低。
- **形态② UB 因子先定死，分核只能在残余自由度上切**：先按吃满 UB 解出 ubFactor，再由它反推出分组数，最后才轮到分核——分组数已是因变量，`ceil(分组数 / 核数)` 的取整阶跃无法再调，关键路径被抬高。
- **形态③ 模板/分支选路判据与"填不填得满核"无关**：多模板算子用魔法阈值（`if (r > 512) 走 B 模板`）选路，判据既不含核数也不含关键路径，于是在"另一个模板填不满核"的区间里仍然选错模板。同型变体：双模板算子的临界仅由单一 shape 量（如列宽）决定、既不含核数也不含关键路径量——临界附近某些 dtype/shape 组合会落入退化路径（如整行单轮往返、流水停顿），同属本形态（在库归约类有此写法实例）。
- **形态④ 切分前未做合轴归一化**：tiling 直接在原始 rank/dims 上求解（`switch(rank)` 逐维特判、或只切 dim0），而相邻的同角色轴本可先合并。正确结构是先按算子语义把轴抽象成角色 pattern——elementwise 全轴同角色可合成一维 `[N]`；broadcast 类抽象为 A（非 broadcast 轴）/B（broadcast 轴）；norm/归约类抽象为 A（非 Reduce 轴）/R（Reduce 轴）——再把**内存连续且同角色的相邻轴**合并成最简交替序列（如 `[A,R]`、`[R1,A,R0]`、A/B 交替），切分在规范 pattern 上求解。收益一举三得：①分核自由度——合并后 A 段长度是各轴乘积，不再受单一外轴长度限制，是形态①的系统性预防；②搬运连续性——合并后的内段可整段连续 DMA（联动 PRC-MEM-005）；③实现收敛——tiling/kernel 只处理规范 pattern，不随 rank 枚举分支、不漏配高维 case。UB 因子的求解域也应是合轴后的规范 pattern（联动 PRC-MEM-012）。

形态②的机理值得单独看。设 `rGroups = floor(R / rUbFactor)`、`关键路径 = ceil(rGroups / coreNum) × rUbFactor`：`rGroups` 是 `rUbFactor` 的减函数，而外层 `ceil` 制造阶跃，两者叠加使关键路径**对 rUbFactor 非单调**——吃满 UB 取最大值往往不是最优点。按上游 BlockSplitR 的真实公式，`R=8192、coreNum=48` 时：

| rUbFactor | rGroups | ceil(rGroups/48) | 关键路径 |
|---|---|---|---|
| 160 | 51 | 2 | 320 |
| **176** | 46 | 1 | **176（最优）** |
| 192 | 42 | 1 | 192 |
| **256（吃满 UB 取最大）** | 32 | 1 | **256** |

吃满 UB 的取法比最优点慢 **45%**，而最优点的 UB 反而没吃满。实测把该模板改成"均衡择优"后 A5 上 **-9.1%**。

## 错误写法

```cpp
// 反例（形态②）：rUbFactor 只由 UB 解出，分组数是它的因变量，分核只能被动接受
int64_t rUbFactor = FloorDiv(ubSizeCanUse, aAlignSize * (inOutNodeNum + TBUF_NODE_NUM));
rUbFactor = FloorAlign(rUbFactor, RA_BINARY_ADD_THRESHOLD);
int64_t rGroups = FloorDiv(patternR, rUbFactor);          // ← 已被 rUbFactor 定死
int64_t formerCoreBlockFactor = CeilDiv(rGroups, usedCoreNum);  // ← 到这里已无自由度
```

```cpp
// 反例（形态③）：选路判据是魔法阈值，与核数/关键路径无关
if (r1Dim > 512) { return TemplateB; }   // 512 从何而来？填不满核的区间照样选 A
```

```cpp
// 反例（形态④）：不合轴，按原始 rank 逐维特判，且只切 dim0
switch (shape.GetDimNum()) {                 // 每个 rank 一套切分代码
    case 2: blockFactor = CeilDiv(shape[0], coreNum); break;   // dim0 短则核填不满
    case 3: blockFactor = CeilDiv(shape[0], coreNum); break;   // dim1/dim2 从未参与切分
    ...
}
```

## 正确写法

```cpp
// 正例（形态②）：在候选 ubFactor 上按关键路径择优，而非直接取最大
int64_t best = maxUbFactor, bestCost = LLONG_MAX;
for (int64_t f = maxUbFactor; f >= minUbFactor; f -= align) {
    int64_t groups = FloorDiv(R, f);
    int64_t cost   = CeilDiv(groups, usedCoreNum) * f;    // 关键路径
    if (cost < bestCost) { bestCost = cost; best = f; }
}
```

```cpp
// 正例（形态③）：判据写成"对手模板填不满核 或 本维度足够长"
bool rivalUnderfillsCores = (aSplitBlocks < coreNum);
bool rLongEnough          = (r >= rSplitProfitableLen);
if (rivalUnderfillsCores || rLongEnough) { return TemplateSplitR; }
```

```cpp
// 正例（形态④）：先按角色合轴成规范 pattern，再在其上切分（以归约类 A/R 为例）
int64_t aLen = 1, rLen = 1;
for (size_t i = 0; i < shape.GetDimNum(); ++i) {     // 连续同角色轴合并
    (IsReduceAxis(i) ? rLen : aLen) *= shape[i];     // 前提：同角色轴相邻且内存连续
}
blockFactor = CeilDiv(aLen, coreNum);                // A 段=各轴乘积，rank 无关
```

## 识别方法

**先判结构，再用数值取证**——四种形态都能从切分逻辑本身看出来，不必逐 shape 试算。

前置：按 PRC-ARCH-002 确认核数确实从 `GetCoreNumAiv()` 取得且真正参与了切分表达式。若核数是写死的或"取了不用"，先报 PRC-ARCH-002，本条的关键路径分析在此之上才有意义。

1. **看切分前有没有合轴归一化**（形态④）：tiling 入口是否先把同角色相邻轴收拢成规范 pattern（存在 merge/收拢逻辑，或输入已是框架合轴后的规范形），还是直接 `switch(rank)`/逐维硬编码求解。判定角色按算子语义：elementwise 同角色、broadcast 分 A/B、归约分 A/R。未归一化且存在"内存连续 + 同角色"的可合相邻轴 → 命中；症状佐证：外轴短的 case 核数上不去（与形态①合并报）、不同 rank 各一套切分代码。
2. **看切分用了哪些维度**（形态①）：列出算子可切的全部维度，对照切分表达式实际用了哪几个。只切最外层维度、而用例集里**存在该维度取值小于核数量级的 case**、且剩余维度未参与切分 → 命中。这一步只需要"该维度取值范围"，不需要逐 case 算；命中后在证据里列出受影响的 case 及其闲置核数量级。
3. **看各切分因子的求解顺序与自由度**（形态②）：把 tiling 里 `ubFactor` / 分组数 / `blockFactor` 的赋值按依赖排成链。若形如 `ubFactor ← UB 容量` → `分组数 ← f(ubFactor)` → `blockFactor ← ceil(分组数 / 核数)`，即分核发生在最后一环、且上游不回溯，则分核已无自由度 → 命中。**这是纯结构判定，与具体 shape 无关。**
4. **看选路判据的表达式**（形态③）：多模板算子的模板选择条件里是否出现核数或关键路径量。只有魔法阈值/纯 shape 阈值 → 命中。
5. **数值只用于取证与排序**：命中后才代入用例集的 shape，算 `max(单核工作量)` 与理想值 `ceil(总工作量 / 核数)` 的差距，用于给 finding 排序和写证据；不用它来发现问题。**平台核数不可得时照常出结论**——用用例集里该维度的取值范围与核数的相对关系表述（如"batch 最小 1、10 条 ≤16，而向量核数为几十量级"），不得因缺数值跳过本条。

误报边界：

- **`blockFactor = CeilDiv(numRow, coreNum); useCoreNum = CeilDiv(numRow, blockFactor)` 这个写法本身关键路径恒等于理想值 `ceil(numRow / coreNum)`，与具体数值无关**，因此 `useCoreNum < coreNum` 不构成 finding，也不必逐 shape 验算。举例佐证：`numRow=64, coreNum=56 → blockFactor=2, useCoreNum=32`，看似闲置 24 核，但关键路径 = 2 行 = 理想值；`numRow=128 → blockFactor=3, useCoreNum=43`，关键路径 3 行 = 理想值。识别出这个写法即排除形态②，只需继续看形态①（还有没有别的维度可切）。
- **memory-bound 算子加核收益封顶**：同一算子在核数多 23~100% 的机器上实测只快 3~11%。不得按核数比例预估收益，形态①的收益要按瓶颈流水重估。
- **小 shape 边界按"单核工作量"判，不按"被切维度短"判**：只有当单核工作量已小到与核启动头开销同量级（如单核仅处理几十到几百元素）时才排除。**"被切维度长度小于核数"本身正是形态①的命中条件，不得用本边界把它排除掉**——判据是"闲置核 × 单核工作量"是否可观，而不是被切维度是否短。例：`batch=2、numCol=12288、fp32` 只用 2 核、54 核闲置，单核要跑整行 48KB 的两趟处理，属命中，不属小 shape。
- 形态①**不因"补切的维度需要跨核归约"而排除**：跨核归约（各核局部结果 + SyncAll/原子加归并）是既有可行手段，见 PRC-MEM-002 的归并形态；只有确实无法改写为归并形态的强顺序依赖才排除。
- 变长/稀疏导致的天然不均，若无重排/归并手段可用，不报（与 PRC-MEM-002 的归并形态边界一致）。
- 形态④的"可合"有硬前提，以下情形不报：轴间内存不连续（非 dense stride、转置视图、NZ 等带分形/padding 的 format 轴不得跨界合并）；轴上挂有 per-axis 语义（按轴生效的 attr、逐轴 quant scale）；框架/adapter 或 op_host 前置已做过合轴、kernel 收到的已是规范 pattern。
- 形态④用例集全部 rank 恰等于规范 pattern（无可合轴的余地）时，仅作记录不报——收益要在高维/外轴短的 case 上才兑现。
- 形态③中判据虽是常数阈值、但有实测数据或注释说明该阈值即等效于填满核判据的，记录不报。

与 PRC-MEM-012 同时命中时（形态②即典型场景）：**本条优先**——先定均衡择优，再在其约束下谈 UB 吃满。

## 证据要求

finding 必须给出：

- 核数在代码中的来源（按 PRC-ARCH-002：接口调用处的文件:行号，及它流到分核表达式的追值链）；
- tiling 中各切分因子的赋值链摘录（带文件:行号），形态②需据此说明分核发生在最后一环且上游不回溯；
- 代入用例集 shape 的关键路径算式与理想值对比，以及 `CeilDiv` 写法边界的排除判定；
- 形态①需给出候选切分维度及切后可达的关键路径；形态③需给出选路判据处的文件:行号与摘录，并说明判据为何与填核程度无关；
- 形态④需给出：可合而未合的相邻同角色轴清单及其内存连续性依据（stride/format 判定）、合轴后规范 pattern 与 A 段长度变化（受影响 case 的核数对比）、以及切分代码按 rank 枚举的文件:行号佐证。

## 参考

- 官方核间负载均衡：`atlas_ascendc_best_practices_10_0035`。
- 关联知识点：PRC-MEM-002（有没有分核，本条的前置）、PRC-MEM-012（UB 切分，冲突时本条优先；ubFactor 求解域应是形态④合轴后的规范 pattern）、PRC-MEM-005（合轴后内段整段连续 DMA）、PRC-ARCH-002（核数取证）。
- 形态④的角色抽象例证：norm/归约类 A/R（在库 batch_norm 类的 r1·a·r0、softmax 类的 A/R 均为此抽象）；broadcast 类 A/B。

# GE 自定义交付件路由（选型与共用规范）

> 本文件是「条目 7 / 11 / 12」的统一路由与共用规范：先按决策树选交付形态，再进入对应 skill。
> 逐步指导与可编译模板在各 skill 内：`model-recommend-plugin-dev`、`model-recommend-fusion-pass-dev`、`model-recommend-custom-op-dev`。

## 1. 选型决策树

```
模型迁移/优化需求
  ├─ 解析报"算子不支持"(it is not supported / CheckTypeSupported / parse model failed)
  │   （多为 GPU 定制/大融合算子、第三方域算子，如归一化、注意力类）──▶ 插件 model-recommend-plugin-dev
  │        └─ 拼图所需原语 NPU 也没有、现有算子拼不出 ──▶ 自定义算子 model-recommend-custom-op-dev
  ├─ 已跑通、要提性能，且图内结构可一次下发在 device 侧算完 ──▶ Pass model-recommend-fusion-pass-dev
  └─ 编译/运行报"无对应内核"(assign engine failed / op type ... is not found in this op store /
    data type ... is not supported)，或特殊功能(动态/分组扩展等)小算子拼不出或不划算、dtype/layout 不满足
    ────────────────────────────────────────────────▶ 自定义算子 model-recommend-custom-op-dev
```

补充规则：

- **实施优先级：Pass 优先 > Plugin 其次 > 自定义算子最后**；自定义算子必须人工评估确认。
- 插件/自定义算子解决"能否跑通"，Pass 解决"跑得快"；Pass 本质也是把已有算子重组。
- dtype/format 不支持（如 int64/bool）→ **优先用 Pass 在前后加 Cast/Transpose 规避**；奇怪 shape 导致的低效 → 优先用 Pass 重组。
- 自定义算子分两类：① NPU 完全没有对应功能；② 已有算子有 bug 或当前版本不支持、需改单算子代码重编。
- 大部分模型用官方内置能力即可跑通；只在跑不通、跑不快时按上述顺序按需引入定制。

## 2. 方案库 → 交付形态映射

| 方案类别 | 首选形态 | 说明 |
| --- | --- | --- |
| 图级：融合、常量折叠、死代码消除、冗余 cast/transpose、布局转换、子图划分 | Pass | 结构可识别、语义等价 |
| 算子级：等价算子替换、模式融合、kernel/tiling 选择、减少小算子 | Pass；缺内核再自定义算子 | 热点明确、语义可对齐 |
| 内存：中间结果复用、峰值削减、缓冲复用、对齐 | Pass / 运行参数 | 避免破坏语义 |
| 运行时：线程/核心、流并行、批处理、异步、预取 | 运行参数（条目 3/8 限核压测） | 交付件 skill 不实施 |
| Host：减少 launch/sync、workspace 复用、避免逐次分配 | Pass / 图模式 | non-kernel 占比高时优先 |
| 数据/IO：连续布局、对齐、减少转置、统一 dtype | Pass | 数值一致性与边界 shape 必须回归 |
| 精度：混合精度、累加精度、按算子回退 | Pass 或自定义算子 | 必须用户签核并做精度回归 |
| 动态 shape：静态特化、分桶、动态 kernel、shape 缓存 | Pass / 自定义算子 | 评估覆盖率与最坏时延 |
| 量化/压缩、并行/通信、自动调优 | 越界 | 单卡 onnx 推理不覆盖，记录不执行 |
| 缓存/预取：权重预取、流式加载 | Pass / 运行参数 | 关注峰值与最坏时延 |

选择原则：先看收益上界是否在关键路径，再看实现成本、风险、精度与维护成本；优先"证据强、改动小、可回归"。

## 3. ROI 与开发门禁

- 单 Pass 收益低于 1% 且在噪声范围 → 不开发/不保留。
- 自定义算子周期显著大于收益上界 → 不开发；必须人工评估开发周期、风险与维护成本。
- 需要修改 ONNX、重新切分或修改输出 dtype → 产品决策，需负责人/精度签核。
- 依赖当前 CANN 版本不稳定项（编译超时、segfault、NZ 长尾）且无法白名单规避 → 暂缓并记录。
- 精度/语义无法证明、缺 golden 且差异无法解释 → 不实施。
- 开发优先级以 `model-recommend-analysis` 的融合规划排序（Top-N）为准；未进清单不立项。

## 4. 交付规范（强制）

- **一个交付件 = 一个功能单元**：插件按原算子、Pass 按最大同结构融合模式、算子按单算子拆分。
- 每个交付件 README 固定 6 字段：功能 / 分类 / 实现原理 / 工程结构 / 安装使用 / 适配版本与芯片。
- 命名：插件 `framework/onnx_plugin/<domain>_<optype>.cc`；Pass `<pattern>_pass/`、`<Pattern>Pass`、`lib<pattern>_pass.so`；算子包 `<op>_custom`。
- **不得直接切分/删改原图**；**先单件精度，后整网精度**。
- 交付件须登记本地源码、安装包、开关与默认值、设置参数、精度模式、验收结论与回退方式，并写入模型交付说明书（见 `workflows/templates/model-delivery-manual-template.md`）。

## 5. 关键 API 速查

- 插件：`REGISTER_CUSTOM_OP("PartitionedCall").FrameworkType(ONNX).OriginOpType({...}).ParseParamsByOperatorFn(...).ParseOpToGraphFn(...).ImplyType(ImplyType::BUILDIN)`；属性在 `"attribute"` 的 JSON 字符串内，先 `json::parse`。
- Pass：`REGISTER_CUSTOM_PASS("<PassName>").CustomPassFn(<PassFn>).Stage(CustomPassStage::kAfterInferShape)`；遍历 `graph->GetAllNodes()`，匹配后 `AddDataEdge`/`RemoveEdge`/`RemoveNode`。
- 算子：`msopgen` 生成工程 → `op_graph`(REG_OP) / `op_host`(def/infershape/tiling) / `op_kernel`(AscendC) / `op_api`(aclnn) → `build.sh --soc=ascend910b` → `.run`。

## 6. 部署/回退

| 交付件 | 部署 | 回退 |
| --- | --- | --- |
| 插件 | `libcust_onnx_parsers.so` → `opp/vendors/<vendor>/framework/onnx/` | 删除或移除 `ASCEND_CUSTOM_OPP_PATH` |
| Pass | `lib<pattern>_pass.so` → `opp/vendors/<vendor>/custom_fusion_passes/` | 移除 `.so` 或 `GE_FUSION_SWITCH_FILE` 关 |
| 算子 | `./custom_opp_<os>_<arch>.run --quiet` + `source set_env.bash` | 删除 `$ASCEND_OPP_PATH/vendors/<package_name>` |

覆盖/卸载后清 `kernel_meta`/`fusion_result` 并复跑 `--verify`。

## 7. 报错样本

- 解析期：`CheckTypeSupported ... type[<domain>::<version>::<OpType>] ... it is not supported` → 取该 type 作 `OriginOpType`。
- 无内核：`GetDNNEngineName ... assign engine failed` / `op type ... is not found in this op store` / `data type ... is not supported` → 先 Pass+Cast 规避，再自定义算子。

> 完整细节与可编译模板：`model-recommend-plugin-dev` / `model-recommend-fusion-pass-dev` / `model-recommend-custom-op-dev`。
> 执行框架（GE_SESSION_DEMO）对 Agent 只读，详见 `framework/README.md`。

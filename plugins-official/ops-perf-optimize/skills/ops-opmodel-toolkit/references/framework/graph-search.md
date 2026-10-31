# 候选比较、图搜索与会话接口

以完整模型目录、实验 YAML 和当前版本支持的动作作为输入。
使用命令入口完成实验；生成的候选和检查点按产物保存，不手工拼装或改写其内容。

## 候选比较输入

```yaml
kind: comparison
evaluation: {scope: all_nonempty_cores}
baseline: {name: baseline, path: ../baseline}
candidates:
  - {name: candidate_a, path: ../candidate_a}
cases:
  - {name: default, params: {}, weight: 1}
cache_model: shared_estimated
objective: {metric: weighted_geomean_ratio}
```

路径相对实验 YAML；`params` 填写模型所需的完整 case 输入。
`all_nonempty_cores` 要求模型具有有效的分核和逐核工作量声明。
`native_workload` 是另一种评价范围，不与完整 case 的结果混用。

```text
python -m accel_model.app.cli.graph_search --experiment EXPERIMENT.yaml --output OUTPUT
python -m accel_model.app.cli.graph_search --actions MODEL
python -m accel_model.app.cli.graph_search --help
```

`--actions` 返回当前模型可供尝试的动作及标识。需要应用动作时使用
`--apply-action MODEL --action-id ID --evidence TEXT --expected-gain TEXT --added-cost TEXT --output NEW_MODEL`。
输入必须是对应父模型的动作标识；记录实际变更及实验依据。
动作列表不是完成搜索的证据，动作被接受也不意味着候选通过全部验收。

## 输出与采纳

实验报告包含基线、候选、逐 case 评价、排名、覆盖和失败原因；可用字段取决于入口。
`ranking/design_winner` 表示当前成本与范围下的模型实验结果。
`validated_ranking/validated_winner`、`prediction_ranking`、`recommendation` 等状态
分别读取，不能用一个较低周期替代未完成的检查。

候选与基线必须具有可比较的输入、数学语义、硬件、成本、后端和 scope。
来源不明或未知成本的候选不作为有效性能依据。采纳导出目录后重新运行原 case；
模型数值通过不等于设备正确或已获得设备加速。

## 搜索会话

`python -m accel_model.app.cli.agent_search --help` 提供
`init/propose/register/evaluate/status/note/retain/defer/close` 等操作。
会话输入包括 `requirements`、带 `params/weight` 的 `cases`、`objective` 和 `budget`。
会话目录位于 `OPMODEL_WORKSPACE` 下，并与候选模型目录分开。
完整可运行流程见[联合搜索示例](../joint-optimization/wheel-commands.md#图动作与搜索会话)。

`register` 保存本次候选；后续编辑原目录不会自动更新已登记候选。
`status` 用于查看尝试、失败、排除项和当前结果；登记或恢复会话本身不算性能评价。
结束时用真实原因调用 `close`，预算耗尽和暂停不等于达到优化目标。

## 使用限制

不同入口接受的实验类型、参数及模型组合不同，先核对帮助及错误信息。
参数搜索不能视为任意结构搜索；未尝试的候选族及预算未覆盖项应如实报告。
存储、控制、物理执行或 Python hooks 不受某动作支持时，保留拒绝原因并选择可用实验。
不能修改检查点签名或删除模型约束来绕过校验。

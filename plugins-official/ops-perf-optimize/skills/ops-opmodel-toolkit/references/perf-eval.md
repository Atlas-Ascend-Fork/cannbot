# 性能评估

输入清单可使用[shape 规格模板](../assets/templates/shape-spec.md)。运行前核对
[常见偏差](perf-eval/pitfalls.md)，交付内容见[报告格式](perf-eval/output-format.md)。

回答完整 case 在声明硬件与成本下的模型耗时、瓶颈和可行配置变化。先恢复固定基线，
再按请求比较分核、tiling、阶段与 slots；具体运行命令见[快速入门](quickstart.md)
和[参数寻优](optimization.md)。

## 比较口径

- 输入为分核前的完整 case，按模型契约包含 batch 等维度，不能把单核工作量当总量。
- 保存 wheel 版本、模型/成本快照、硬件 profile、核数、时钟、执行入口和输出 scope。
  理论 profile、实测成本与校准配置分别说明，名称为 theoretical 不能证明所有成本均为理论值。
- 比较双方实际加载的硬件和成本必须一致。各入口覆盖能力见[硬件配置](hardware.md)：
  普通完整 case 不支持 `hardware_path` 覆盖，分核 CLI 没有通用 `--hardware`。
  不能只在 DAG 搜索切换硬件后，将其结果与另一 profile 的完整 case 混比。
- 评估现有实现时，固定其不可变的接口与实现常量；探索新实现时按合法设计空间展开，
  并说明候选落地所需的实现变化。

## 基线、搜索与复评

1. 用完整输入运行 `scripts/run_case.py` 或相应物理入口，保存 `result.json`、有效
   参数、分配结果和 trace。核对非空核数及尾块，不能用平均分配猜最重核。
2. 请求分核搜索时使用 `split_run` 与独立实验 YAML；检查候选的 `feasible`、
   `adoptable`、核数和验证结果。请求固定 DAG 搜索时使用 `dag_run`，核对
   `parameter_space` 或 `SEARCH_DIMS` 未缺失、未被全部固定，hook 未加载失败。
3. 多阶段流水需要联合评估 phases 与 slots 时，按[联合搜索命令](joint-optimization/wheel-commands.md)
   调用 `joint_search`。记录合法阶段候选、参数域、发射策略、预算与实际覆盖。
   单 stage 模型的 `phases: search` 仍可能只有一种划分。
4. 将候选的输入参数和执行配置分别应用回模型副本，再以同一完整 case 复评。
   不能直接用搜索导出的配置片段覆盖六份完整定义；核对派生后的实际参数。
5. 用[结果分析](analysis.md)比较总体耗时、活跃核与流水统计；有空泡时转到
   [空泡分析](dag-bubble-opt.md)。不要求每次搜索都得到改善。

DAG 局部评分、代表核周期和完整 case 周期分开报告。`native_top_k` 的固定配置复核
也不自动等于完整 case 复评。VF 未知成本保持待测，不用任意常数完成有效排名。

## 报告内容

| 内容 | 要点 |
| --- | --- |
| 输入与身份 | 完整 shape、dtype/layout、模型、版本、硬件与成本来源 |
| 搜索覆盖 | 参数域、固定项、候选数、淘汰原因、预算未覆盖部分 |
| 同口径结果 | 基线和候选完整 case 周期；时钟有依据时换算时间 |
| 实现差异 | tile、phase、slots、split 的实际变化及落地条件 |
| 瓶颈证据 | busy/等待/任务不均衡，并引用结果或 trace |
| 限制 | 成本未校准、数值未执行、设备未验证等实际状态 |

时间换算为 `duration_us = cycles / (clock_ghz * 1000)`。收益比明确分子分母，例如
`baseline_cycles / candidate_cycles`；周期下降百分比为 `1 - candidate/baseline`。
配置相同或候选同分只说明本次范围没有改善，不写成全局最优。

多 case 使用相同入口逐 case 编排，每个 case 保留独立输出。

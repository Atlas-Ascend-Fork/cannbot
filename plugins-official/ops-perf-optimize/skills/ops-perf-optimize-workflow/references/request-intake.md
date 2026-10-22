## 2. 启动配置与输入冻结

启动配置分为可复用请求和本次运行身份。主 Agent先检查用户是否提供 `optimization-request.json`：提供时校验并展示摘要，路径和 Python 身份有效即可直接复用；未提供时在最开头一次性确认以下内容：

| 配置 | 规则 |
|---|---|
| `CODE_DIR` | 具体待优化算子代码目录 |
| `TARGET_SOCS` | 本次会完成构建、功能和性能验证的 SoC 列表；只验证 A5 时只能写 A5，不得填写未验证代际 |
| `TUNING_MODE` | `standard`（默认）或 `generalization`；属于输入身份 |
| `PERFORMANCE_CASES` | standard 必选；generalization 可提供性能/功能合一用例，或留空后生成 |
| `FUNCTIONAL_MODE` | standard：`reuse_performance|existing|generate`；generalization：固定 `reuse_performance`，不作为待确认选项 |
| `PERFORMANCE_REFERENCE` | 每 case 对标来源与目标比例，见 [`baseline-evaluation.md`](baseline-evaluation.md)；通过 `--performance-reference <json>` 固化，旧任务保留原始实现对比 |
| `OPTIMIZATION_OBJECTIVE` | `fixed_rounds` 或 `target`；前者默认 3 轮，后者需指标、比较方向、数值、单位和可选最大轮次 |
| `PYTHON_ENVIRONMENT` | Python 可执行文件及可选激活命令；创建 request 时记录实际版本 |
| `CANN_ENVIRONMENT` | 环境加载命令；用户明确选择当前环境时写 `inherit` |

generalization 还必须在启动时确认竞品性能来源：

- `COMPETITOR_PERF`：竞品性能 CSV，接受 `case_id,gpu_total_us`，或 `testcase_name,gpu_time_us` 后由脚本规范化；创建时未提供时可在泛化用例接入后用 `attach-competitor` 补交。

竞品性能文件未给出时必须询问，不允许默认跳过。泛化模式固定记录默认目标 1000 条、geomean ratio ≥ 1.0、min ratio ≥ 0.6、内层最多 3 轮和外层最多 2 次；这些值进入 request/manifest，不能只留在对话中。

`fixed_rounds` 固定执行确认的轮数；未指定轮数时向用户提议默认 3 轮并确认。`target` 按 `metric + comparison(ge/le/eq) + value + unit` 判断达标，指标必须能从本工作流的落盘性能证据计算；可选 `max_rounds`，不提供时不设隐式轮次上限。达到目标即结束性能循环；目标未达时，只有所有仍可能填补差额的合法方向均有不可行证据，或显式停止条件到达，才能结束。零方案、连续无收益或未能外推的诊断仿真不满足这一条件，具体判定以 [workflow-contract.md](workflow-contract.md) 为准。性能轮次或目标不会截断尚未完成的精度诊断。

精度诊断不是用户输入项，固定持续执行，没有工作流级总时长、轮次、Agent turn 或 token 上限。命令级防挂死 watchdog 可以识别单次编译/执行的 Hang，但不得被解释成精度诊断总预算。

用户确认后调用 `prepare_case_sets.py create-request` 写 `optimization-request.json`。该文件只保存请求意图和环境，不保存输出目录、冻结 artifact 或阶段状态，因此可以跨 run 复用。核心结构为：

```json
{
  "schema_version": 2,
  "operator": "maximum",
  "tuning_mode": "standard",
  "target_socs": ["Ascend950"],
  "code_dir": "/abs/path/to/operator",
  "performance_cases": "/abs/path/to/performance.csv",
  "functional": {"mode": "existing", "cases": "/abs/path/to/functional.csv"},
  "optimization_objective": {"mode": "fixed_rounds", "rounds": 3},
  "performance_reference": {"kind": "baseline", "target_ratio": 1.0},
  "generalization": null,
  "environments": {
    "python": {"executable": "/abs/path/to/python", "version": "Python 3.x", "activation_command": null},
    "cann": {"setup_command": "source /abs/path/to/setenv.bash"}
  },
  "confirmation": {"status": "confirmed", "confirmed_by": "user"}
}
```

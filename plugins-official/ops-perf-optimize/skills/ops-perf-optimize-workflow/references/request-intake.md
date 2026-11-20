## 2. 启动配置与输入冻结

启动配置分为可复用请求和本次运行身份。主 Agent先检查用户是否提供 `optimization-request.json`：提供时校验并展示摘要，路径和 Python 身份有效即可直接复用；未提供时在最开头一次性确认以下内容：

| 配置 | 规则 |
|---|---|
| `CODE_DIR` | 具体待优化算子代码目录（git 仓；非 git 目录需在确认时定处置，见 `GIT_INIT`） |
| `DIRTY_POLICY` | 检测到未提交/暂存区改动时必问（基线 = 原工程已提交状态，脏改动不进基线）：`(b)` 留在用户工作树（默认，附"脏文件 ∩ 算子闭包"交集警告；优化任务在自己 worktree 内进行，绝不使用用户工作树）/`(d)` 存 patch 后丢弃全部更改 /`(c)` 终止；随 request 冻结 |
| `GIT_INIT` | `code_dir` 非 git 仓时必问：是否允许原地 `git init`（只新增 `.git`，可逆）；同意则基线评估定稿时初始化并首 commit 作基线，拒绝则直接终止流程 |
| `BACKEND` | ascendc（旧请求默认）或 cannbot_dsl；输入身份，不以文件后缀推断 |
| `DSL` | DSL 必选 repo_root、entrypoint=module:callable、execution_mode=jit或aot；默认 workload_scope=network_cases |
| `TARGET_SOCS` | 本次实际用于验证的 SoC 列表；识别现有目标设备的 `NpuArch` 和具体型号，在可用设备上验证，代码按同族泛化，不得新增具体型号专属门禁 |
| `SCHEDULE_POLICY` | **按需开启**（默认不冻结）：仅当候选方案涉及跨 tile、多 engine 或异步缓冲复用时，经 `create-request --schedule-policy` 或 request 字段显式启用；历史缺字段保持旧协议，不在恢复时偷偷升级。适用性与证据见 [调度契约](../../ops-perf-acceptance-criteria/references/async-schedule-contract.md) |
| `TUNING_MODE` | `standard`（默认）或 `generalization`；属于输入身份 |
| `SEARCH_POLICY` | 新请求默认 `{"id":"architecture_search_v1","version":1}`；每轮一个方案，测量驱动参考晋升与架构重规划，见 [搜索决策](../../ops-perf-acceptance-criteria/references/architecture-search.md)。搜索不改变用户目标或轮数 |
| `EXPERIENCE_POLICY` | 新请求默认 `{"id":"evidence_lessons_v2","version":2}`；全部轮次提炼可复用经验并独立阅读验收，见 [经验质量契约](../../ops-perf-postprocess/references/experience-reflux.md)。这是流程默认项，无需另问用户；历史请求缺字段时不追溯升级，冻结后不得移除 |
| `PERFORMANCE_CASES` | standard 必选；generalization 可提供性能/功能合一用例，或留空后生成 |
| `FUNCTIONAL_MODE` | standard：`reuse_performance|existing|generate`；generalization：固定 `reuse_performance`，不作为待确认选项 |
| `PERFORMANCE_REFERENCE` | 每 case 对标来源与目标比例，见 [基线评估](../../ops-perf-baseline-evaluate/references/baseline-evaluation.md)；通过 `--performance-reference <json>` 固化，旧任务保留原始实现对比 |
| `OPTIMIZATION_OBJECTIVE` | `fixed_rounds` 或 `target`；前者默认 5 轮，后者需指标、比较方向、数值、单位和可选最大轮次。创建 request 时显式询问用户选固定轮数还是 target 模式 |
| `PYTHON_ENVIRONMENT` | Python 可执行文件及可选激活命令；创建 request 时记录实际版本 |
| `CANN_ENVIRONMENT` | 环境加载命令；用户明确选择当前环境时写 `inherit` |

generalization 还必须在启动时确认竞品性能来源：

- `COMPETITOR_PERF`：竞品性能 CSV，接受 `case_id,gpu_total_us`，或 `testcase_name,gpu_time_us` 后由脚本规范化；创建时未提供时可在泛化用例接入后用 `attach-competitor` 补交。脚本仅机械校验 ID 精确覆盖与数值为正，**不校验参考实现的语义正确性**：接入前必须对采样 case 做 golden 链数值交叉验证（掩码方向、单位、重复计算等语义误读会把整个优化方向带偏），交叉验证证据随 request/manifest 归档。

用例与竞品 CSV 的 `case_id` 约定：优先读 `case_id`/`id`/`case`/`name` 列；均缺失时按数据行位置编号 `row-{Excel 行号}`（首个数据行为 `row-2`，表头占第 1 行）。该约定在 freeze（`prepare_case_sets.case_id`）、搜索（`search_policy.case_ids`）等所有模块一致生效，不要自造 `row-1` 起数或其他编号。

竞品性能文件未给出时必须询问，不允许默认跳过。泛化模式固定记录默认目标 1000 条、geomean ratio ≥ 1.0、min ratio ≥ 0.6、内层最多 3 轮和外层最多 2 次；这些值进入 request/manifest，不能只留在对话中。

`fixed_rounds` 固定执行确认的轮数；未指定轮数时向用户提议默认 5 轮并确认。`target` 按 `metric + comparison(ge/le/eq) + value + unit` 判断达标，指标必须能从本工作流的落盘性能证据计算；可选 `max_rounds`，不提供时不设隐式轮次上限。达到目标即结束性能循环；目标未达时，只有所有仍可能填补差额的合法方向均有不可行证据，或显式停止条件到达，才能结束。零方案、连续无收益或未能外推的诊断仿真不满足这一条件，具体判定以 [workflow-contract.md](workflow-contract.md) 为准。性能轮次或目标不会截断尚未完成的精度诊断。

精度诊断不是用户输入项，固定持续执行，没有工作流级总时长、轮次、Agent turn 或 token 上限。命令级防挂死 watchdog 可以识别单次编译/执行的 Hang，但不得被解释成精度诊断总预算。

用户确认后调用 `$WORKFLOW_SCRIPTS/prepare_case_sets.py create-request` 写 `optimization-request.json`。该文件只保存请求意图和环境，不保存输出目录、冻结 artifact 或阶段状态，因此可以跨 run 复用。核心结构为：

DSL 创建时追加 `--backend cannbot_dsl --dsl-repo-root <领域仓库> --dsl-entrypoint <原module:callable> --dsl-execution-mode jit|aot`。默认 standard + 用户网络 case；原 pytest 库存按 existing 接入，库存目录提供 cases.csv、测试 nodeid 映射及测试/golden 资产。只有原测试缺口才补必要边界，不默认生成泛化全集。身份切换需更新请求并失效旧证据。

```json
{
  "schema_version": 2,
  "operator": "maximum",
  "tuning_mode": "standard",
  "target_socs": ["Ascend950"],
  "code_dir": "/abs/path/to/operator",
  "performance_cases": "/abs/path/to/performance.csv",
  "functional": {"mode": "existing", "cases": "/abs/path/to/functional.csv"},
  "optimization_objective": {"mode": "fixed_rounds", "rounds": 5},
  "performance_reference": {"kind": "baseline", "target_ratio": 1.0},
  "generalization": null,
  "schedule_policy": {"id": "schedule_contract_v1", "version": 1},
  "search_policy": {"id": "architecture_search_v1", "version": 1},
  "experience_policy": {"id": "evidence_lessons_v2", "version": 2},
  "environments": {
    "python": {"executable": "/abs/path/to/python", "version": "Python 3.x", "activation_command": null},
    "cann": {"setup_command": "source /abs/path/to/setenv.bash"}
  },
  "confirmation": {"status": "confirmed", "confirmed_by": "user"}
}
```

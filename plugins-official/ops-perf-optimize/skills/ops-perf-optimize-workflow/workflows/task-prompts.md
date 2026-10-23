# 性能优化工作流任务模板

本文件是跨客户端必须保留的稳定派发入口。`skills/ops-perf-optimize-workflow/references/workflow-contract.md` 是阶段、模式、恢复和交接规则的唯一工作流真源；本文件只负责角色路由和通用信封，不复制或改写业务规则。

## 按角色加载

| `ROLE` | 只读取此模板 | 执行者 |
|---|---|---|
| `baseline` | [`prompts/baseline.md`](prompts/baseline.md) | 通用 subagent + `ops-perf-baseline-evaluate` |
| `preparation` | [`prompts/preparation.md`](prompts/preparation.md) | 通用 subagent + `ops-perf-preparation` |
| `analysis` | [`prompts/analysis.md`](prompts/analysis.md) | 通用 subagent + `ops-perf-analysis` |
| `implementation` | [`prompts/implementation.md`](prompts/implementation.md) | 通用 subagent + `ops-perf-implementation` |
| `integration` | [`prompts/integration.md`](prompts/integration.md) | 通用 subagent + `ops-perf-postprocess` |

派发方先完整读取工作流契约，再按本次 `ROLE` 读取且只读取一份角色模板。不得预载其他角色模板，也不得从模板反推阶段、模式或验收规则。

五个 ROLE 统一派发给当前环境的**通用 subagent**，信封中声明 `ROLE` 并要求加载对应阶段 Skill；阶段职责、流程与验收以各 Skill 为唯一真源。前处理与后处理必须是独立实例，靠剥离映射、快照和冻结证据交接；不得恢复前处理实例执行后处理。用例生成由 baseline 角色按需读取 `prompts/generation.md` 的库存变体，不另派 generation 角色。

## 派发前检查（主 Agent 必做）

1. **读取本 ROLE 的角色模板**：先完整读取 `$WORKFLOW_ROOT/workflows/prompts/<role>.md`，按模板字段逐项填写信封。只凭下方“通用信封”手写视为派发准备未完成，容易漏掉角色固定产物（例如 implementation 的 `final-functional-regression.md`、`final-performance-comparison.md`）。
2. **信封与工作流脚本路径用绝对路径**：信封中的每条路径、以及子 agent 对工作流脚本（`scripts/` 目录下）的调用，必须使用解析后的绝对路径；`WORKFLOW_ROOT`/`WORKFLOW_SCRIPTS` 是主 Agent 侧的占位符，**不是环境变量**，不要当 shell 变量展开。子 agent 在自己工作目录内对普通文件做 `sed`/`grep`/`ls` 等常规相对路径操作不受此限制。

## 通用信封

```text
ROLE: <baseline|preparation|analysis|implementation|integration>
TASK_KIND: <role template variant>
WORKFLOW_ROOT: <resolved absolute ops-perf-optimize-workflow skill directory>
WORKFLOW_SCRIPTS: <resolved absolute ops-perf-optimize-workflow/scripts directory>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <absolute path; pending only before baseline freeze>
WORKFLOW_STATE: <absolute path; pending only before baseline freeze>
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: <N or absent>
CODE_DIR: <assigned isolated absolute path>
KB_ROOT: <cannbot-knowledge knowledge root for analysis/implementation, or absent>
INPUT_ARTIFACTS: <absolute paths, one per line>
OUTPUT_ARTIFACTS: <absolute paths, one per line>
ACCEPTANCE: <mechanically verifiable completion conditions>
CONDITIONAL_SKILLS: <additional skills required by the selected route, or absent>
```

只替换模板占位符，不删字段。基线 freeze 前 `TUNING_MODE`、`TARGET_SOCS` 取自已确认 REQUEST；freeze 后 `TUNING_MODE` 必须取自 manifest，输入与输出必须是绝对路径；`KB_ROOT` 由主 Agent 按编排契约解析一次后全程复用，absent 表示知识库不可用，阶段按无知识增强继续；执行细则以对应阶段 Skill 为准；角色基础技能以 Agent 定义为准，条件技能只按契约和已确认输入填写，不能因猜测预载。

主 Agent 不预载阶段执行参考，不将整份工作流契约复制进任务。受派 Agent 只加载角色声明的阶段 Skill，按需加载共享验证规则；`workflows/prompts/<role>.md` 是主 Agent 的派发模板，不随信封下发，受派 Agent 的角色定义即阶段 Skill。受派 Agent 先读自己的角色定义及冻结输入；manifest/state 已初始化时，先用 `$WORKFLOW_SCRIPTS/workflow_state.py inspect --state <WORKFLOW_STATE> --stage <本阶段键>` 读取配置、集合身份和本阶段记录，按需读取原文件的详细字段；基线 freeze 前改读已确认 REQUEST。只写分配目录。返回 `status`、产物绝对路径、适用的源码/二进制 SHA、门禁结论和未决证据；不得用对话摘要代替落盘文件。输入不完整、身份不匹配或验收不可机械验证时，返回主 Agent 补齐，不在 prompt 中临时发明流程。

信封引用产物路径和必要差异，不粘贴完整日志、逐 case 数据或历史诊断。目录与构建入口定位一次后复用清单；仅在路径、依赖或身份变化时重新扫描。长命令的完整输出写入证据文件，向会话返回退出码、摘要和日志路径；失败时读取首个完整错误及相关上下文，不反复整树搜索或输出全量日志。

阶段内的可验证进展先落盘再返回文本摘要；保存点同时写明已完成证据、未核验产物和下一动作，便于中断后续接。不要让结束时一次性补写所有交付文档。

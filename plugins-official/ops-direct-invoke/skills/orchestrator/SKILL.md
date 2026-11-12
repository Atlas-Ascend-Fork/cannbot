---
name: ops-direct-invoke
description: 主会话承接用户的直调算子开发、修复、已有算子性能优化或继续交付请求时使用，作为 PM 对齐需求与环境、编排工作流并组织交付。不用于已派发节点的执行或验收、单纯读取模板资源，也不用于维护工作流本身。
---

# 直调算子工作流编排

## PM 职责与边界

承接用户完整任务的主会话加载本 Skill 后担任 PM，负责需求对齐、工作区准备、模板选择、流程启动和交付汇总。PM 不进入任务图，不代替节点执行或编写验收报告。

节点按安装后的角色配置和 task 工作，读取模板或脚本资源不改变其派发身份，也不重新进入 PM 流程。角色、业务步骤、输入输出和验收方法以所选模板及其 task 为准。

调度前必须加载 `workflow-orchestrator` Skill，按其中的要求执行；实际路径从本轮 `context.json` 的 `skills` 清单定位。只通过 harness 公开接口下发、查询、恢复工作流和提交用户决定的审批结果，不绕过框架派发节点、修改调度状态或自动批准节点。task 委托完整独立工作流时，按其公开契约接入输入输出，内部执行由被委托工作流负责。

## 需求与启动准备

先读取已有说明和项目 `.cannbot/ops-direct-invoke.json` 中的 `preferences`，按其中的交互偏好和自主范围完成需求对齐。具体交互规则由需求 Skill 维护；本次用户明确要求优先于初始化偏好。

必须加载 `ops-direct-invoke-requirement` 和 `ops-direct-invoke-repo-guide` Skill，按其中的要求执行。具体仓库与平台的检查方法由这些能力维护，本入口不复制其分支规则。语言和工程确定后，按支持声明选取 `ops-direct-invoke-env-check`，完成实际组合的环境检查；不把其他变体同时注册到主工作区。

发问前先做必要的只读摸底，只询问确需用户决定的缺项，优先一次问齐，每批不超过五题或问卷工具上限。已知问题因题数限制拆分时连续分批询问；依赖前一答复时只补充新产生的问题。已有明确要求、有效确认和授权直接沿用，未答复不等于确认，不追加总启动批准。

启动前按 `repo-requirement` 的现有 R8 核对是否接入性能优化及确认依据；意愿未明确时先询问，确认需要后再补齐目标、适用 case 和预算，已有有效答复与输入直接沿用。未答或必要输入未决时不启动，不以“用户未提出”替代已确认不接入，也不增加一次总启动批准。需求记录和启动 prompt 按该 Skill 的边界区分初始生成与后续调优，不把“不接入”扩写为取消初始性能选型，也不把这种推导标为用户明确。

将已确认需求写入本轮 `需求分析.md`，环境组合、激活方式、权限与确认依据写入 `环境信息.md`。仓库级环境记录和检查日志沿用环境 Skill 的约定；只复用适用且仍有效的记录，缓存不授予新权限。

所选模板的必要输入、能力与权限缺口在启动前处理；已获授权的准备工作按模板契约编排为前置任务。未解决的缺口如实记录，自主选择须有授权依据，不把默认值写成用户选择，也不宣称环境已通过。需求、环境和授权已对齐后，简要说明目标与交付标准，通知用户开始执行。

## 工作区与运行输入

工作区是本次任务开始时的项目目录，记录其绝对路径，不随切换目录改变。读取项目 `.cannbot/ops-direct-invoke.json`，由 `asset_root` 定位插件资源。配置缺失时按项目安装说明初始化。向 harness 提供的 `START_DIR` / `--start-dir` 使用项目工作区，不使用单轮 `work_dir`；各节点的实际 cwd 由阶段工作区准备接口设置。

每个任务在工作区 `.cannbot/` 下建立独立目录，每轮追加未使用的 `workflow1/`、`workflow2/` 等目录。规划、需求、输入快照、YAML、日志及汇总放在本轮目录，harness 管理的 `.workflow/` 状态只读。节点交付位置与业务产物布局由 task 及已确认需求规定。

语言、任务与工程确定后，用初始化配置准备本轮固定的能力与身份：

```bash
python3 "$ASSET_ROOT/tools/workspace.py" \
  --config "$PROJECT/.cannbot/ops-direct-invoke.json" \
  --work-dir "$WORK_DIR" --language '<已确认语言>' \
  --task '<已确认任务类型>' --engineering '<已确认工程>' \
  --code-dir '<实际代码目录绝对路径>' --provider '<当前客户端>'
```

`ASSET_ROOT` 取初始化配置的 `asset_root`，`PROJECT` 为项目工作区。读取生成的 `context.json`，将其 `plugin_root` 用作 `OPS_DIRECT_INVOKE_ROOT`，后续使用该快照中的工具；本轮组合固定，变更组合新建运行，不覆盖已有清单或修改共享 Skill。

任务 prompt 包含原始请求、本轮目标、需求与环境记录的绝对路径、所需资产及版本、有效确认、修改授权和本轮交互偏好。按选中模板的 `use_when` 与 task 契约准备输入；外部资产与独立流程续写目录须明确路径和权限。复用有效产物时保留原路径、版本与适用范围。

PM 按已确认环境生成 `$WORK_DIR/运行环境.sh`，只包含获准的激活命令及 `PYTHON` 等环境导出，不夹带安装、升级或修复操作。通过 `run_workflow.py --env-script` 将环境落实到实际子进程；节点需要新 shell 时沿用同一激活约定。

按调度 Skill 核对启动输入，其四项启动确认由 PM 根据已确认任务代答，不重复询问用户：

| 输入 | PM 的代答依据 |
|---|---|
| `workflow.yaml` | 本轮准备好的完整 YAML 绝对路径 |
| `work_dir` | 本轮独立工作目录 |
| `provider` | 当前会话实际使用且受支持的 Agent 框架 |
| `prompt` | 已确认需求、原始任务和本轮目标 |

代答不扩展需求或权限，也不替代节点审批。确实无法确定的启动输入纳入首次集中问卷。将用户明确要求的人工检视点落实为 `require_approval`，在提示列表中保留对应偏好原文；偏好直接指定完整节点 ID 时也可设为 true，启动前核对覆盖。

DSL 的能力依据与版本规则按本轮固定插件的 $OPS_DIRECT_INVOKE_ROOT/skills/custom-skills/doc-templates/ascend/dsl/templates/运行工具.md 定位；默认单节点 op-dev 准备上下文时，将本轮 WORK_DIR 作为实际 --code-dir，声明受管目录的模板沿用其 CODE_DIR。

## 从生成的引导选择模板

**每轮编排前先运行 `$OPS_DIRECT_INVOKE_ROOT/tools/generate_workflow_guide.py`，读取生成的 `workflow-guide.csv`，再按其中的 `file` 和 `use_when` 选择并打开模板。** 不凭记忆或在本入口维护另一份模板清单。脚本失败时先处理错误，不使用过期引导继续编排。

```bash
python3 "$OPS_DIRECT_INVOKE_ROOT/tools/generate_workflow_guide.py" \
  --output /absolute/workspace/.cannbot/task/workflow1/workflow-guide.csv
```

脚本递归扫描插件的 `orchestrations/workflows/`，CSV 中 `file` 相对该目录，`use_when` 来自模板。已确认开发语言时可用 `--language` 收窄扫描范围；不根据模板文件名推断适用性。

模板的适用场景、使用说明和允许的调整只由其 `use_when` 维护。读取匹配模板及其引用的 task，准备输入、绑定声明变量，核对节点、角色、依赖和预算后再启动。向用户简述选择及依据，授权与条件已明确时不追加审批。

按选中模板运行，不根据历史经验省略节点、添加流程或改变验收标准。确无适用模板时说明差异，在已授权范围内组织一次性图并验证；不得为绕过模板必经步骤另造流程。维护可复用模板或 task 时加载 `ops-direct-invoke-maintain` Skill，普通运行不修改已安装的共享资源。

恢复同一轮沿用原引导、完整 YAML、输入和工作目录，不重新选择模板或覆盖文件；新一轮重新生成引导并按当前目标选择。

使用 CANNBotDSL 模板时，按选定 task 核对性能 case、设计路线及精度输入；有用户性能 case 时由设计任务分组建模，无 case 时按其范式路线执行，仅模型路线要求 OpModel 环境。设计和实现职责、同会话建模落稿、测试并行及最终交付规则以模板和任务为准，不另读一份流程总说明。工具固化、恢复与实际 DSL 版本依据见 [运行工具]($OPS_DIRECT_INVOKE_ROOT/skills/custom-skills/doc-templates/ascend/dsl/templates/运行工具.md)。

用户提供的性能 case 无论是否接入寻优，均保留原始输入、case ID 与来源，交 performance-cases 标准化进 CSV 并用于设计和正确性覆盖；不能因不寻优而丢弃。是否接入性能优化按需求 Skill 的 R8 在启动前确认：未明确先询问，确认需要后才补目标、case 和预算；已有有效确认直接复用，不因给了 case 自动开启，也不把未答当作不接入。未决时不启动。

只有确认接入且 case、自然语言目标及预算齐备时，按 [性能契约]($OPS_DIRECT_INVOKE_ROOT/skills/custom-skills/doc-templates/ascend/dsl/templates/性能契约.md) 固化 contract/perf-contract.yaml，明确比较对象、范围、方向、汇总方法与采用条件，保留用户原始要求；不自行增加目标、阈值或固定采样次数。启动前使用本插件 tools/check_perf_contract.py --contract <契约路径> --purpose comparison 核对；采用 diagnostics 时另核对对应入口，保存输出及退出码，缺项先解决。未接入时不另索要寻优预算、不安排独立摸底或默认性能采集，也不声明已做性能验收。

将可选 orchestrations/workflows/cannbot-dsl/perf-opt.yaml 以 perf-opt 子图挂入本轮 op-dev，依赖 precision-validation；它替换原 review-fix，documentation 等待 perf-opt 最终放行。交组装器展开并调整依赖，不手改运行 YAML；未启用时保持原图。测量和预算按性能契约及任务执行，不要求设备独占，不终止他人进程，不用旧诊断冒充比较数据。恢复沿用冻结图、输入、工具和证据，不热更新；这些扩展只用于 DSL，不改变 AscendC/Kirin 路由。

## 组装与下发

节点内容与执行、验收契约来自 task，依赖、角色和重试预算来自模板。PM 只按 `use_when` 允许的方式调整本轮图；不在入口补默认预算或按节点名称推断业务规则。

新轮定制引用图时默认保留所选源模板的 `max_parallel` 和可并行分支；复用产物、删除已完成节点或更换运行目录，不应顺带把全图改为串行。已有用户并发要求优先，依据原始答复核对其适用轮次与持续条件，不把仅限某轮的选择扩展为永久策略，也不因资源变化自行取消仍适用的串行要求。

沿用历史锁冲突、共享写入或资源压力导致的临时降并发前，核对本轮是否仍使用相同会话库/资源、冲突范围及限制依据；配置已变化时记录事实与剩余不确定性，不直接断言故障已消失或提高并发已安全。新一轮不能只替换旧模板的轮次名称而遗漏这项复核；同一轮恢复保持冻结 YAML、工具和状态不变。

启动前在既有编排说明中简记所选源模板并发值、本轮完整 YAML 的顶层值、调整理由及原始授权/资源依据，核对实际依赖和允许写集。用户选择仍有效时沿用；确需改变而授权不明确时按现有启动输入确认规则处理，不追加总启动审批。会话库、CPU 内存和设备使用分别判断，不因 NPU 阶段需串行就限制无冲突的资料准备和只读审查；正式 CSV 仍单一写入，CPU 大用例不增加内部并行，单节点 TDD 的组织方式不变。启动器仅展示最终配置，不代替 PM 判断或自动改值。

需定制本轮参数时，先将引用图保存为本轮 `workflow1.template.yaml`，保持 task 与子图引用能解析到原资源，再绑定声明变量。`variables` 仅作用于所属节点；普通变量使用默认值或填写所需字符串，不添加未知字段。补充 Skill 变量须同时声明提示文本与阶段所需能力，按平台限定适用项；组装时生成提示词与能力绑定，启动前核对实际可用性。共同需求、授权和复用资产放在任务输入中。

组装脚本按引用模板的位置解析 task，展开变量、报告编号和固定子图，输出 harness 标准 YAML。报告路径、变量含义及业务交付要求以 task 为准。组装有错误时先修复输入，不手工修补生成结果；已开始运行的 YAML 保持冻结。

直接启动引导中选出的共享模板：

```bash
python3 "$OPS_DIRECT_INVOKE_ROOT/tools/run_workflow.py" \
  --template '<workflow-guide.csv 中选中的 file>' \
  --work-dir /absolute/workspace/.cannbot/task/workflow1 \
  --provider '<当前 provider>' \
  --env-script /absolute/workspace/.cannbot/task/workflow1/运行环境.sh \
  --prompt-file /absolute/workspace/.cannbot/task/workflow1/original-task.txt
```

`--template` 相对插件的 `orchestrations/workflows/`，与当前 shell 目录无关。脚本先在 work_dir 中生成完整 YAML，再调用 harness；输出已存在时拒绝覆盖。

使用本轮引用图时先组装，再启动：

```bash
python3 "$OPS_DIRECT_INVOKE_ROOT/tools/assemble_workflow.py" \
  --template /absolute/workspace/.cannbot/task/workflow1/workflow1.template.yaml \
  --output /absolute/workspace/.cannbot/task/workflow1/workflow1.yaml
python3 "$OPS_DIRECT_INVOKE_ROOT/tools/run_workflow.py" \
  --yaml /absolute/workspace/.cannbot/task/workflow1/workflow1.yaml \
  --work-dir /absolute/workspace/.cannbot/task/workflow1 \
  --provider '<当前 provider>' \
  --env-script /absolute/workspace/.cannbot/task/workflow1/运行环境.sh \
  --prompt-file /absolute/workspace/.cannbot/task/workflow1/original-task.txt
```

`--yaml` 与 `--template` 互斥。`--yaml` 只接受完整 harness YAML，不重新展开引用；恢复时使用它指向原文件，不重做组装，可省略 `--prompt-file` 复用已保存输入。首次运行必须提供原始任务；`--prompt-file` 与 `--prompt` 互斥，省略 prompt 不清除耗尽状态。

运行使用本轮冻结的 workflow-orchestrator；`--harness-skill` 用于未准备快照的接口模拟等调用，不覆盖已有运行的依赖。`--env-script` 在前台、后台及恢复时均生效，激活失败不启动；恢复沿用同一环境约定。

默认以 tmux 后台运行，返回会话名及 `work_dir/orchestrator.log`。检查实际退出状态，不将启动成功当成交付完成。`--foreground` 前台运行并返回 harness 退出码，`--dry-run` 透传模拟执行选项；脚本不自行重试或修改调度状态。

## 执行、验收与恢复

每个普通节点按模板配置由 executor 执行、verifier 独立验收。双方都读取 goal、acceptance、out_of_scope；approach 只交给执行者，procedure 只交给验收者。角色身份和 Skill 权限由本轮固定的身份及节点契约承接，不根据模板名称另配一套身份。阶段声明分别绑定所需 Skill；工具为 execute/verifier 准备独立 cwd、身份、技能集合和会话，`AGENTS.md` 链接到原角色文件。`WORK_DIR` 始终指向本轮产物目录，`CODE_DIR` 指向实际代码目录，产物与证据使用明确路径访问。

执行者交付真实产物与原始证据，验收者核对内容、完整性和版本对应关系，不代替执行者构建、测试或补造证据。结果通过 harness 当前公开协议提交，文本回复不替代裁决；重试、回滚、审批和耗尽处理沿用框架原生机制。

节点运行中只使用已确认输入和已声明能力，不等待 PM 追加指令，也不修改本轮图。独立受委托流程按其契约交互；无法继续时保存实际阻塞与恢复依据，按协议结束，不把未完成记录作为通过。

PM 按调度 Skill 的要求等待、查询和转发进度，不持续通读产物或向节点补发指令。整轮退出后读取日志、结果和交付件，汇总完成范围及未解决问题。证据仍有效时复用；发生变化或证据缺失时，按任务契约安排必要验证。

交付未完成时按当前目标和生成的引导组织下一轮，保留前轮输入、状态和报告；不复制 `.workflow/` 或重置计数来规避停止条件。同一轮中断则通过公开恢复接口沿用原文件、目录和快照。快照丢失或被改动时报告缺口，不切换到最新资源。任务确认与授权跨轮复用，只有实质变化才补充询问。

缺少必要信息、权限或外部条件时如实汇报，不反复执行相同的无效流程。最终说明交付位置、验证结果和限制；模拟执行及接口回归不等于真实 Agent 或设备验证通过。

上下文隔离不等于操作系统沙箱；客户端仍可能加载用户全局或祖先指引，不修改用户全局配置。

### DSL 性能优化接入

DSL 性能优化接入按本轮选中模板及其 task 的 use_when 与输入契约执行。PM 在首次需求对齐时读取实际安装版本的请求接入规则，收集轮数或可计算目标、对标来源、Python/CANN、SoC 与 JIT/AOT 模式；已有有效确认直接复用，记录到本轮需求中。不要硬编码轮数或把环境的 full/compile_only 当成 JIT/AOT。无交互运行必须提供这些已确认输入。

主图的 performance 是静态子图；harness 调度专用 perf-coordinator 与独立 verifier。性能编排者只在该任务内部按原 Skill 派发通用阶段代理，外层 PM、developer 和其他节点的权限不变。阶段业务状态使用原 Skill 公开接口，外层状态仍由 harness 管理。恢复保留同一请求、run 和已用预算，不清空内部状态。

性能输入适配与输出契约见 `$OPS_DIRECT_INVOKE_ROOT/orchestrations/tasks/cannbot-dsl/性能优化.yaml`。确定性库存转换使用 `$OPS_DIRECT_INVOKE_ROOT/tools/prepare_dsl_performance.py`；功能全集来自冻结原用例，设备性能集合使用相同 case 的原输入配方。性能结果在 `perf-optimize/run/`，最终交接是 `perf-optimize/HANDOFF.md`；文档与交付使用回集成后的版本及证据，优化前 `review-fix/selected.json` 保留为来源记录。

## DSL 代码版本管理

DSL 代码路径与版本协议由所选模板和任务明确声明，不在同一运行中混用。当前默认 op-dev 的单节点实现、测试与精度子图沿用 WORK_DIR 下的 operators 路径及其证据绑定；其设计子图在同一次执行会话完成建模与落稿。声明受管代码目录的模板采用 [代码版本协议]($OPS_DIRECT_INVOKE_ROOT/docs/code-versions.md)：由对应创建工作区任务初始化 `$WORK_DIR/code`，代码读写与测试使用 `CODE_DIR`，报告与 harness 状态仍在 `WORK_DIR`。所有代码写入节点按每轮尝试记录 Git 基线、提交与验证证据；并行 Unit 使用独立 worktree，汇合后重验。已有运行 YAML 与目录不迁移，启动新一轮使用此契约。`rollback_to` 仍为返工调度，Git 恢复必须指定完整 SHA。

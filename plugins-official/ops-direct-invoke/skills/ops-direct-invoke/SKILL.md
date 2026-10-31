---
name: ops-direct-invoke
description: 主会话承接用户的直调算子开发、修复、已有算子性能优化或继续交付请求时使用，作为 PM 对齐需求与环境、编排工作流并组织交付。不用于已派发节点的执行或验收、单纯读取模板资源，也不用于维护工作流本身。
---

# 直调算子工作流编排

## PM 职责与边界

承接用户完整任务的主会话加载本 Skill 后担任 PM，负责需求对齐、工作区准备、模板选择、流程启动和交付汇总。PM 不进入任务图，不代替节点执行或编写验收报告。

节点按安装后的角色配置和 task 工作，读取模板或脚本资源不改变其派发身份，也不重新进入 PM 流程。角色、业务步骤、输入输出和验收方法以所选模板及其 task 为准。

调度前必须加载 `workflow-orchestrator` Skill，按其中的要求执行。只通过 harness 公开接口下发、查询、恢复工作流和提交用户决定的审批结果，不绕过框架派发节点、修改调度状态或自动批准节点。task 委托完整独立工作流时，按其公开契约接入输入输出，内部执行由被委托工作流负责。

## 需求与启动准备

先读取已有说明和工作区上下文，明确目标、开发语言、范围、约束、资料和交付标准。告知用户需要补齐的需求，完成对齐后通知即将开始执行。

必须加载 `repo-requirement` 和 `repo-env-check` Skill，按其中的要求执行。具体仓库与平台的检查方法由这些能力维护，本入口不复制其分支规则。

发问前先做必要的只读摸底，只询问确需用户决定的缺项，优先一次问齐，每批不超过五题或问卷工具上限。已知问题因题数限制拆分时连续分批询问；依赖前一答复时只补充新产生的问题。已有明确要求、有效确认和授权直接沿用，未答复不等于确认，不追加总启动批准。

将已确认需求写入本轮 `需求分析.md`，环境组合、激活方式、权限与确认依据写入 `环境信息.md`。仓库级环境记录和检查日志沿用环境 Skill 的约定；只复用适用且仍有效的记录，缓存不授予新权限。

所选模板的必要输入、能力与权限缺口在启动前处理；已获授权的准备工作按模板契约编排为前置任务。未解决的缺口如实记录，不以默认值替代用户选择，也不宣称环境已通过。需求、环境和授权已对齐后，简要说明目标与交付标准，通知用户开始执行。

## 工作区与运行输入

工作区是本次任务开始时的项目目录，记录其绝对路径，不随切换目录改变。向 harness 提供的 `START_DIR` / `--start-dir` 使用项目工作区，不使用单轮 `work_dir`。

每个任务在工作区 `.cannbot/` 下建立独立目录，每轮追加未使用的 `workflow1/`、`workflow2/` 等目录。规划、需求、输入快照、YAML、日志及汇总放在本轮目录，harness 管理的 `.workflow/` 状态只读。节点交付位置与业务产物布局由 task 及已确认需求规定。

任务 prompt 包含原始请求、本轮目标、需求与环境记录的绝对路径、所需资产及版本、有效确认和修改授权。按选中模板的 `use_when` 与 task 契约准备输入；外部资产与独立流程续写目录须明确路径和权限。复用有效产物时保留原路径、版本与适用范围。

PM 按已确认环境生成 `$WORK_DIR/运行环境.sh`，只包含获准的激活命令及 `PYTHON` 等环境导出，不夹带安装、升级或修复操作。通过 `run_workflow.py --env-script` 将环境落实到实际子进程；节点需要新 shell 时沿用同一激活约定。

按调度 Skill 核对启动输入，其四项启动确认由 PM 根据已确认任务代答，不重复询问用户：

| 输入 | PM 的代答依据 |
|---|---|
| `workflow.yaml` | 本轮准备好的完整 YAML 绝对路径 |
| `work_dir` | 本轮独立工作目录 |
| `provider` | 当前会话实际使用且受支持的 Agent 框架 |
| `prompt` | 已确认需求、原始任务和本轮目标 |

代答不扩展需求或权限，也不替代节点审批。确实无法确定的启动输入纳入首次集中问卷。

## 从生成的引导选择模板

**每轮编排前先运行 [generate_workflow_guide.py](scripts/generate_workflow_guide.py)，读取生成的 `workflow-guide.csv`，再按其中的 `file` 和 `use_when` 选择并打开模板。** 不凭记忆或在本入口维护另一份模板清单。脚本失败时先处理错误，不使用过期引导继续编排。

```bash
python3 scripts/generate_workflow_guide.py \
  --output /absolute/workspace/.cannbot/task/workflow1/workflow-guide.csv
```

脚本递归扫描本 Skill 的 `workflows/`，CSV 中 `file` 相对该目录，`use_when` 来自模板。已确认开发语言时可用 `--language` 收窄扫描范围；不根据模板文件名推断适用性。

模板的适用场景、使用说明和允许的调整只由其 `use_when` 维护。读取匹配模板及其引用的 task，准备输入、绑定声明变量，核对节点、角色、依赖和预算后再启动。向用户简述选择及依据，授权与条件已明确时不追加审批。

按选中模板运行，不根据历史经验省略节点、添加流程或改变验收标准。确无适用模板时说明差异，在已授权范围内组织一次性图并验证；不得为绕过模板必经步骤另造流程。维护可复用模板或 task 时加载 `ops-direct-invoke-maintain` Skill，普通运行不修改已安装的共享资源。

恢复同一轮沿用原引导、完整 YAML、输入和工作目录，不重新选择模板或覆盖文件；新一轮重新生成引导并按当前目标选择。

## 组装与下发

节点内容与执行、验收契约来自 task，依赖、角色和重试预算来自模板。PM 只按 `use_when` 允许的方式调整本轮图；不在入口补默认预算或按节点名称推断业务规则。

需定制本轮参数时，先将引用图保存为本轮 `workflow1.template.yaml`，保持 task 与子图引用能解析到原资源，再绑定声明变量。`variables` 仅作用于所属节点；使用默认值或填写所需字符串，不添加未知字段。共同需求、授权和复用资产放在任务输入中。

组装脚本按引用模板的位置解析 task，展开变量、报告编号和固定子图，输出 harness 标准 YAML。报告路径、变量含义及业务交付要求以 task 为准。组装有错误时先修复输入，不手工修补生成结果；已开始运行的 YAML 保持冻结。

直接启动引导中选出的共享模板：

```bash
python3 scripts/run_workflow.py \
  --template '<workflow-guide.csv 中选中的 file>' \
  --work-dir /absolute/workspace/.cannbot/task/workflow1 \
  --provider '<当前 provider>' \
  --harness-skill /absolute/installed-skills/workflow-orchestrator \
  --env-script /absolute/workspace/.cannbot/task/workflow1/运行环境.sh \
  --prompt-file /absolute/workspace/.cannbot/task/workflow1/original-task.txt
```

`--template` 相对本 Skill 的 `workflows/`，与当前 shell 目录无关。脚本先在 work_dir 中生成完整 YAML，再调用 harness；输出已存在时拒绝覆盖。

使用本轮引用图时先组装，再启动：

```bash
python3 scripts/assemble_workflow.py \
  --template /absolute/workspace/.cannbot/task/workflow1/workflow1.template.yaml \
  --output /absolute/workspace/.cannbot/task/workflow1/workflow1.yaml
python3 scripts/run_workflow.py \
  --yaml /absolute/workspace/.cannbot/task/workflow1/workflow1.yaml \
  --work-dir /absolute/workspace/.cannbot/task/workflow1 \
  --provider '<当前 provider>' \
  --harness-skill /absolute/installed-skills/workflow-orchestrator \
  --env-script /absolute/workspace/.cannbot/task/workflow1/运行环境.sh \
  --prompt-file /absolute/workspace/.cannbot/task/workflow1/original-task.txt
```

`--yaml` 与 `--template` 互斥。`--yaml` 只接受完整 harness YAML，不重新展开引用；恢复时使用它指向原文件，不重做组装，可省略 `--prompt-file` 复用已保存输入。首次运行必须提供原始任务；`--prompt-file` 与 `--prompt` 互斥，省略 prompt 不清除耗尽状态。

`--harness-skill` 默认定位同级已安装的 workflow-orchestrator，源码调用或不同布局时显式提供。`--env-script` 在前台、后台及恢复时均生效，激活失败不启动；恢复沿用同一环境约定。

默认以 tmux 后台运行，返回会话名及 `work_dir/orchestrator.log`。检查实际退出状态，不将启动成功当成交付完成。`--foreground` 前台运行并返回 harness 退出码，`--dry-run` 透传模拟执行选项；脚本不自行重试或修改调度状态。

## 执行、验收与恢复

每个普通节点按模板配置由 executor 执行、verifier 独立验收。双方都读取 goal、acceptance、out_of_scope；approach 只交给执行者，procedure 只交给验收者。角色身份和 Skill 权限由安装后的客户端配置及节点契约承接，不根据模板名称另配一套身份。

执行者交付真实产物与原始证据，验收者核对内容、完整性和版本对应关系，不代替执行者构建、测试或补造证据。结果通过 harness 当前公开协议提交，文本回复不替代裁决；重试、回滚、审批和耗尽处理沿用框架原生机制。

节点运行中只使用已确认输入和已声明能力，不等待 PM 追加指令，也不修改本轮图。独立受委托流程按其契约交互；无法继续时保存实际阻塞与恢复依据，按协议结束，不把未完成记录作为通过。

PM 按调度 Skill 的要求等待、查询和转发进度，不持续通读产物或向节点补发指令。整轮退出后读取日志、结果和交付件，汇总完成范围及未解决问题。证据仍有效时复用；发生变化或证据缺失时，按任务契约安排必要验证。

交付未完成时按当前目标和生成的引导组织下一轮，保留前轮输入、状态和报告；不复制 `.workflow/` 或重置计数来规避停止条件。同一轮中断则通过公开恢复接口沿用原文件和目录。任务确认与授权跨轮复用，只有实质变化才补充询问。

缺少必要信息、权限或外部条件时如实汇报，不反复执行相同的无效流程。最终说明交付位置、验证结果和限制；模拟执行及接口回归不等于真实 Agent 或设备验证通过。

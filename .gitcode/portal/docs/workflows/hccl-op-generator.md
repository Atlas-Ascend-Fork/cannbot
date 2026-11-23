<!-- 来源文件：plugins-official/hccl-op-generator/quickstart.md -->

# HCCL 算子开发插件

`hccl-op-generator` 编排 AICPU/CCU 通信算法开发，安装 9 个 Skill 和 Architect、Developer、Reviewer、Verifier 四个角色。CCU 技术能力来自独立 `cannbot-skills` 仓库中的 `communication/hccl-ccu-best-practice`。

## 从源码安装

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot
node script/bin/cannbot.js install hccl-op-generator --source "$PWD" --tool opencode --target /absolute/project
```

## 从本地开发仓安装

在 cannbot 仓根执行，目标为准备运行客户端的工作目录：

```bash
node script/bin/cannbot.js install hccl-op-generator \
  --source "$PWD" \
  --skills /path/to/cannbot-skills \
  --tool opencode \
  --target /absolute/project
```

`--tool` 可选 opencode、codex、claude、trae 或 dsh。OpenCode/Codex 的项目 Skill 位于 `.agents/skills/`，Claude 位于 `.claude/skills/`；工作流和脚本位于 `.cannbot/plugins/hccl-op-generator/`，版本/来源记录在客户端配置目录下的 `cannbot-plugin.json`。安装器还执行对应客户端的原生插件注册；Codex 同时更新用户级插件目录和 marketplace。

`--skills` 必须是包含新 CCU Skill 的 Git 工作树根。此模式保留本地未提交内容并使用符号链接；本地修改会反映到使用它的项目。安装插件不代表已安装 CANN/HCCL 测试环境。

源码子模块和市场中的HCCL Skill条目固定到同一技能提交。发布时先合入对应技能PR；若squash/rebase改变提交SHA，同步核对并更新子模块与市场条目的固定版本。本地开发可用上面的`--skills`方式引用工作树。

## 发起 CCU 开发任务

示例需求（具体支持条件按任务补充）：

```text
使用 CCU_SCHED 开发 AllGather 通信算法。
HCCL 仓：/path/to/hccl
HCOMM 仓：/path/to/hcomm
请先冻结设计和启动参数契约，再按 hccl-op-generator 的 CCU 流程实现和验证。
默认选路保持不变；算法、rank/拓扑、dtype、数据范围按需求与当前源码确定。
```

路由先通过 `workflows/scripts/workflow_policy.py route` 检查。明确 CCU/CcuSched/CcuMS/CCU_SCHED/CCU_MS 的请求进入 CCU；无引擎标记的标准算子仍默认 AICPU；引擎冲突需澄清，AIV/HostDPU 暂不支持。

流程为环境→设计→基线→实现→独立评审→候选构建与双轨测试→estimate 性能估算→完成。新 CCU 任务使用契约版本3，设计额外冻结 `source-report.json`、`launch-contract.json` 和 `sync-contract.json`，绑定 HCCL/HCOMM 身份，使用 `validate_ccu_artifacts.py` 检查。estimate 与功能验证分别保存证据，估算失败或缺失时保留功能结果并阻塞完成；结果为仿真估算，不代表真机性能收益。完整规则与角色调用见 [CCU 工作流](https://gitcode.com/cann/cannbot/blob/master/plugins-official/hccl-op-generator/workflows/ccu-multi-agent-workflow.md) 和 [CCU prompts](https://gitcode.com/cann/cannbot/blob/master/plugins-official/hccl-op-generator/workflows/ccu-task-prompts.md)。

只要求审查已有实现时使用 [独立只读评审](https://gitcode.com/cann/cannbot/blob/master/plugins-official/hccl-op-generator/workflows/task-prompts.md)，不启动完整开发流水线。静态契约检查不能替代源码语义审查、编译或 Checker；功能通过不能代表 NPU 性能收益。

## 复用先验知识

先读CCU Skill的`references/development-entry.md`，再按`references/operator-index.md`只加载本算子的接入卡。现已覆盖AllGather、AllReduce、ReduceScatter、Broadcast、Reduce、Scatter；AllGather Sole另有方法契约，其他算子使用自己的字段/launch/cache约束。首次来源报告保存到任务文件，后续只检查知识卡摘要（示例为AllReduce）：

```bash
CCU_SKILL_DIR=/path/to/cannbot-skills/communication/hccl-ccu-best-practice
python3 "$CCU_SKILL_DIR/scripts/check_knowledge.py" \
  --hccl-root /path/to/hccl --hcomm-root /path/to/hcomm \
  --op all_reduce --summary
```

MATCH且适用的卡直接复用，变化只补查相关方法。新任务的同步和生成器算术检查器在设计冻结门禁运行；测试计划首版核对工具可表达域、分支可达性和宿主机内存预算，避免构建后才退回重设计。

修订规格或测试计划后，可用对应validator的 `--rebind-report TASK_SPEC TEST_PLAN --json` 生成owner拓扑工作单，逐层核对更新后以 `--verify-rebind` 审计残留；这两个命令只读，不自动改报告或赋予PASS。

CCU Skill提供`check_contracts.py --launch ... --sync ... --hcomm-root ...`统一静态检查，以及`check_knowledge.py --summary --explain`源码漂移定位。每template的数据流证明使用专用dataflow-spec-template.md，避免重复完整设计与矩阵。

第四轮复盘后的工具见 [CCU 初始化与证据工具](https://gitcode.com/cann/cannbot/blob/master/plugins-official/hccl-op-generator/workflows/ccu-automation.md)：`preview_cases.py --op <算子目录名>`计算六算子的实际输入（旧AllGather入口兼容），`init_ccu_task.py`创建未通过的环境草稿，`summarize_ccu_evidence.py`核对并汇总显式选定run。执行冻结矩阵复用hvm的`plan.py`；工具结果仍由原角色和门禁验收。

## 开发回归

```bash
CANNBOT_SKILLS_TEST_ROOT=/path/to/cannbot-skills \
  python3 -m unittest discover \
  -s plugins-official/hccl-op-generator/workflows/tests -q
```

未指定 `CANNBOT_SKILLS_TEST_ROOT` 时测试使用 `vendor/cannbot-skills`，需已初始化到包含新 Skill 的版本。测试包含路由/恢复、产物与权限门禁、CCU CLI 合成流程、AICPU 回归，以及临时项目中的 OpenCode/Claude 安装；不会调用设备、构建 HCCL 或注册用户级插件。

## AICPU 使用

AICPU请求继续执行 [AICPU工作流](https://gitcode.com/cann/cannbot/blob/master/plugins-official/hccl-op-generator/workflows/aicpu-multi-agent-workflow.md)，按 [AICPU调用模板](https://gitcode.com/cann/cannbot/blob/master/plugins-official/hccl-op-generator/workflows/aicpu-task-prompts.md) 调度。两条流程均在候选功能验证后执行estimate，执行参数与基础证据格式共用已安装`hccl-test-tool-hvm/references/estimate.md`；CCU额外核对运行模式和HCOMM身份。AICPU原有门禁保持，测试矩阵与实际支持条件按目标源码和工具确认。

### 开发算子示例


详细下发示例：
本地已有hccl代码：/path/to/hccl,请按 HCCLBot 多 Agent 工作流处理以下 AICPU 开发需求：完成aicpu引擎的allgather ring算法,完成后给我呈现报告

allgather-ring算法详细描述
通信引擎：aicpu

算法参数：

- 参与Ring通信的卡数：n
- 输入：in
- 输出：out，分成n片slice，其中第j片slice表示为out[j]
- 中转内存：scratch，分为n片slice，其中第j片slice表示为scratch[j]
- 当前卡的rank_id：i
- ring算法所需的步数：n-1
- rank p的中转内存的第s片slice地址，表达为：p.scratch[s]

算法表达（站在rank i的视角）：

```
    prev = （i-1）% n
    next =  (i+1) % n
    # 输入拷贝到scratch
    scratch[i] = in
    # 输入拷贝到out
    out[i] = in
    # 分步传输，共n-1步
    for k in range( n-1 ):
        # 发送给next
        next.scratch[ (i-k)%n ] = scratch[ (i-k)%n ]

        # 从prev收数据
        scratch[ (i-1-k)%n ] = prev.scratch[ (i-1-k)%n ]

        # 收到的数据，复制一份放到自己的out中
        out[(i-1-k)%n] = scratch[ (i-1-k)%n ]
```

补充说明，假设4卡，当前卡为卡1， out收集数据的过程：

- 直接从本卡获得out[1]
- k = 0, 获得out[0]
- k = 1, 获得out[3]
- k = 2, 获得out[2]

当然也可以用很简单的示例，不需要描述ring算法的详细步骤：
本地已有hccl代码：/path/to/hccl,请按 HCCLBot 多 Agent 工作流处理以下 AICPU 开发需求：完成aicpu引擎的allgather ring算法
HCCLBot 会先判定引擎，AICPU 任务按工作流分派给四个 Agent。把**算子类型**（AllReduce/ReduceScatter 等）、**算法名称**、**引擎**、**拓扑场景**、**数据类型**写清楚即可。

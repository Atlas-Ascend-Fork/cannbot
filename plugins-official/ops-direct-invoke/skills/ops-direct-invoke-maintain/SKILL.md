---
name: ops-direct-invoke-maintain
description: 维护 ops-direct-invoke 工作流的架构与设计思想。修改 ops-direct-invoke Skill 中的 PM 入口、客户端 agents 目录中的 ops-direct-invoke-* 角色、Skill 目录（.agents/skills/ 或客户端配置目录下的 skills/）中的本工作流关联 Skill、.cannbot/plugins/ops-direct-invoke/ 插件资产，以及维护 Skill 内的 test/、插件 README、QUICKSTART 等文档、安装迁移与 harness 调度集成时，必须加载本 Skill。普通算子代码开发、任务产物和单轮工作流编排不触发。
---

# ops-direct-invoke 工作流维护

## 工作区目录结构

本文的“工作区”指用户当前任务所在的项目目录。以用户指定的项目路径和当前会话上下文定位，再结合项目指引文件与客户端配置目录中的 `cannbot-plugin.json` 安装记录确认；不要把 Skill 软链接指向的源码目录当作项目根目录。

不同客户端使用不同的配置目录、角色格式和 Skill 路径。下面的 `<客户端配置目录>`、`<Skill目录>` 是布局占位符，不是实际目录名；具体位置以项目文件和安装记录为准：

```text
<工作区>/
├── <Skill目录>/
│   ├── ops-direct-invoke-maintain/  # 本维护 Skill
│   ├── ops-direct-invoke/           # 主会话 PM 入口、tasks、workflows、scripts、templates
│   ├── workflow-orchestrator/       # harness 调度接口与执行能力
│   ├── repo-*/                      # 仓库约定与工程能力
│   └── <公共 Skill>/               # DSL、AscendC 等领域能力
├── <客户端配置目录>/
│   ├── agents/                     # ops-direct-invoke-* 子 Agent 角色配置
│   └── cannbot-plugin.json          # 插件安装记录
└── .cannbot/
    ├── plugins/ops-direct-invoke/   # 角色原始文件等插件资产
    ├── dependencies/ops-direct-invoke/ # 依赖仓库
    └── <任务名>/workflow<序号>/     # 单轮输入、产物与运行状态
```

Skill 目录可能是 `.agents/skills/`，也可能是客户端配置目录下的 `skills/`；角色配置由安装器按客户端要求生成。安装记录列出角色、Skill 和资产路径，用它定位实际文件，不假定固定扩展名或单一客户端布局。源码安装时 Skill 目录可能是软链接，打包安装时则可能是副本。

主会话通过已安装的 `ops-direct-invoke/SKILL.md` 加载 PM 职责，子 Agent 通过客户端角色配置承接节点任务。

## 整体架构

各组件的职责如下：

| 模块 | 职责 |
|---|---|
| 子 Agent 角色 | 仅定义架构师、开发者、验收者的身份、职责与权限，不绑定具体 Skill |
| `ops-direct-invoke` Skill | 主会话的 PM 入口，负责需求对齐、任务规划和交付组织，组织 task、workflow 模板及组装与启动脚本 |
| `repo-*` 与公共 Skill | 提供仓库约定、工作方法和领域能力 |
| harness / `workflow-orchestrator` | 下发子 Agent 任务并执行工作流 |
| 维护 Skill 内的 `test/` | 工作流维护后的脚本与接口回归验证 |
| `README.md` / `QUICKSTART.md` | README 介绍结构、职责和设计意图；QUICKSTART 介绍安装与使用 |
| 安装与来源配置 | 将角色和 Skill 安装到项目中，维护能力来源与路径映射，同步插件配置 |

## 基础设计思想

- **PM 按任务加载。** 主会话通过 `ops-direct-invoke` Skill 承接用户的算子任务，负责需求对齐、规划和交付组织；PM 职责仅在承接完整任务的主会话中生效。
- **入口与节点隔离。** 非算子任务不受本插件的 PM 规则约束。已派发节点按自己的角色和 task 工作，读取入口目录下的模板或脚本不等于调用 PM 入口。
- **本工作流的子 Agent 统一通过 harness 调度。** 不绕过 harness 直接拉起子 Agent，PM 不进入调度图。
- **各层分工明确。** 角色定义职责与权限，Skill 提供工作方法，task 描述具体任务和交付契约，workflow 组织依赖关系，harness 负责执行调度。详细规则由对应模块维护，避免在 PM 入口重复展开。

### 分层与依赖方向

分层的目的是让组件可以独立理解、复用和替换。PM 入口组织任务，workflow 组织依赖，task 组合角色与能力；子 Agent 角色和知识 Skill 不依赖自己被哪个阶段使用。PM 入口承载流程编排，仓内知识文档不承担 Agent 调度职责；各组件通过公开契约合作，不依赖彼此的内部步骤。

工作流依赖能力名称和输入输出契约，不依赖某份 Skill 的章节、内部资源布局或具体仓库实现。详细的单一职责、扩展与替换原则见 [repo-* Skills](reference/repo-skills.md)。维护 Skill 需要理解跨模块关系以判断变更影响，因此可以引用各层设计；这种跨层视野不应注入普通执行任务。

### 约束应落在合适的机制中

确定性的转换、输入检查和权限边界优先使用脚本、框架接口或客户端已有机制，避免仅靠 Agent 记住提示词。业务判断和设计理由由文档表达，不为难以机械判断的语义堆叠拦截器。harness 已提供的机制直接使用，不在工作流中重复实现或测试。

原则用于保护职责和契约，具体文件名、挂载方式与检查方法按设计需要调整。调整时明确理由及对调用方的影响，同步相关模块资料。

## 通用维护要求

先检查相关 Skill 的软链接目标，并按需读取客户端配置目录中的 `cannbot-plugin.json` 确认插件归属和安装方式。源码安装下，编辑 Skill 链接中的文件会影响其源目录及使用该源码的其他工作区。

客户端角色配置与插件资产是安装生成的文件，不等同于 Skill 软链接。维护可复用规则时定位其源文件和生成逻辑，不只修改安装副本；用户明确要求工作区局部调整时保留该范围。安装器清理项目指引时只移除本插件的完整管理区块，保留区块外用户内容和其他插件指引，不删除整个项目文件。安装记录用于定位，不靠手改记录完成同步。

新增 Skill 或在 task 中引用新 Skill 时，按来源处理：

- **外部 Skill**：必须在插件源码目录的 `plugin-sources.json` 中注册来源，使安装器能够获取并安装；已注册项不重复添加。
- **插件内 Skill**：已经随本代码仓提供，由安装器发现插件 `skills/` 下的内容，不需要在 `plugin-sources.json` 重复注册。

外部注册路径按 `skillsRepository` 解析；两类 Skill 都须确认目录和 `SKILL.md` 存在，task 引用名称与元数据 `name` 一致，并实际安装到工作区。源码安装时核对链接及其目标有效，打包安装时核对复制的完整资源；不能以源仓存在文件代替工作区可加载的验证。

修改 Skill 或角色名称、脚本参数、产物路径或文件格式时，检查生产方、消费方、安装配置、测试及文档是否需要同步。改变已有使用方式时说明影响和迁移办法；兼容性处理以实际使用需求为准，不为假设中的消费者添加额外机制。

每次维护工作流都必须检查 `README.md` 与 `QUICKSTART.md` 是否与实际实现及彼此一致，按 [文档维护规范](reference/documentation.md) 完成检查并修订不一致之处。

**每次修改工作流后，必须完整运行本 Skill 的 `test/ut/test_all.py`，确认未改坏已有脚本、参数处理和工作流接口。** 运行方式与测试边界见 [测试体系](reference/tests.md)；不能用单类通过或部分用例通过替代完整回归。

**新增特性时，必须考虑是否需要新增测试。** 根据脚本行为和接口的回归风险决定，必要时补充最小用例；也可以向用户提出具体测试建议，说明要防止的问题及验证方式，避免为固定配置或提示词措辞增加无意义的看护。

维护资料记录“为什么这样设计”和由此产生的职责边界、维护约束，不记录当前模板清单、固定数量或脚本实现现状。具体功能、参数和操作说明由对应 Skill、使用文档与实现维护，避免把实现现状固化为禁止重构的约束。

完整回归入口（将路径替换为本 Skill 的实际位置）：

```bash
python3 /absolute/skills/ops-direct-invoke-maintain/test/ut/test_all.py
```

## 模块资料路由

每份资料介绍一个完整模块的设计目的、职责边界和维护方法。按本次修改涉及的模块读取，不默认加载全部资料；跨模块修改时读取相关项。

下表中的源码路径相对于插件目录 `plugins-official/ops-direct-invoke/`；工作区中的安装文件按安装记录与软链接映射回对应模块。

| 模块及涉及的修改 | 详细资料 |
|---|---|
| `skills/ops-direct-invoke/SKILL.md`：PM 入口、职责边界与安装行为 | [PM 入口](reference/agents-entry.md) |
| `agents/`：architect、developer、verifier 三个子 Agent 的职责、权限与协作 | [子 Agent](reference/subagents.md) |
| `skills/ops-direct-invoke-maintain/test/`：维护回归、覆盖范围与完整运行方式 | [测试体系](reference/tests.md) |
| `README.md`、`QUICKSTART.md`：文档分工与每次维护的一致性检查 | [文档](reference/documentation.md) |
| `skills/ops-direct-invoke/`：算子流程分层、组装边界及围绕 harness 组织的设计目的 | [算子开发流程 Skill](reference/ops-direct-invoke.md) |
| `ops-direct-invoke` 中的 task 组织、字段语义与可见性、执行与验收契约 | [Task 组织规范](reference/task-authoring.md) |
| `skills/repo-*/`：父仓与子仓的同名覆盖、仓库知识分层及七个 Skill 的正交职责 | [repo-* Skills](reference/repo-skills.md) |

尚未讨论的模块先保留框架，详细设计逐项补充。用户明确要求变更设计思想时，同步更新对应模块资料；新增模块时在此补充路由。Skill 注册等通用维护要求在入口统一维护，不单独划为模块。

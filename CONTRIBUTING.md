# CANNBot 社区贡献指南

本文档是 CANNBot 仓群的贡献入口，说明贡献内容归属、公共与专项要求，以及常见架构问题的处理指引。

仓群级贡献规则以本文档为准，治理机制见[治理指南](GOVERNANCE.md)；各仓库专属流程与质量门槛以各仓 CONTRIBUTING 为准。

---

## 一、社区愿景与架构

CANNBot 是 [CANN](https://gitcode.com/cann) 社区的 Infra 智能体兴趣小组，愿景是降低开发者在整个 CANN 领域的开发难度、提升生态友好度。仓群将各领域的知识、流程和工程实践沉淀为可复用的 Agent 应用与能力，帮助开发者完成算子开发、模型迁移、推理优化，以及图模式、Runtime、通信和工具等系统开发，并支持资料管理、Issue / PR 处理等社区协作。

CANNBot 的定位与仓群结构见 [README 的概述与仓群结构图](README.md)。

---

## 二、贡献内容归属

| 内容 | 目标仓 | 说明 |
|---|---|---|
| 公共 / 可独立使用 Skill | cannbot-skills | 唯一真源，多处使用通过引用复用 |
| 宿主仓私有 Skill | 宿主仓 `.agents/skills/` | 离开宿主仓无独立价值；与公共 Skill 的比较见 [Q1](#q1-新-skill-放-cannbot-skills宿主仓还是随插件abcd-判据) |
| 插件、Agent 与工作流 | cannbot | 目录契约、安装与维护见 `docs/repository-guide.md` |
| 知识卡 | cannbot-knowledge | 生产与治理流程见该仓 CONTRIBUTING |
| DSL 与算子样例 | cannbot-dsl | 随语言和样例同仓演进 |
| 评测题集 / 指标 / 报告 | cann-bench | 随评测体系同仓演进 |
| 观测 / 审计 / 评估工具 | cannbot-sentry | 一仓一包，包间零依赖 |
| 技术专题 / 白皮书 | 对应内容所属仓，或专项评审仓 | — |

### 2.1 跨仓资产的引用与同步

同一 Skill 只维护一份真源，同一场景的本地只存一份；多处使用通过引用复用，禁止复制后双写。不同场景可在各自本地目录锁定不同版本。依赖保持单向：cannbot 仓 → cannbot-skills / cannbot-knowledge，禁止反向；Skills 仅通过 knowledge 查询 / 检索接口获取知识，边界见 [Q2](#q2-知识贡献到-cannbot-skills-还是-cannbot-knowledge)。

可按场景选择以下引用方式：

1. **Agent 安装协议**：通过 `npx skills add`、`plugin install` 等方式按版本安装到场景本地；
2. **清单声明**：通过 `plugin-sources.json` 声明所需 Skills 与版本，由安装器解析；
3. **Git 引用**：通过 `git subtree` / `git submodule` 锁定来源与版本，引用产物只读，不在本地回写。

例外：源码级开发 Skill 可通过在插件或 Skill 中拉取宿主源码获得仓外使用价值，此时按公共 Skill 归 cannbot-skills；强耦合细节保留为仓内文档，`SKILL.md` 仅引用仓库名，不复制内容。

场景级版本隔离见 [Q4](#q4-skills-版本如何锁定)。

---

## 三、贡献要求

所有贡献先满足以下仓群公共要求：

1. **Issue 模板**：必须使用目标仓 `.gitcode/ISSUE_TEMPLATE/` 中与类型匹配的模板（如 [cannbot 仓的模板](.gitcode/ISSUE_TEMPLATE/)），并提供有助于理解和处理问题的实际信息。暂缺日志、环境或复现路径时，可说明缺失原因和已尝试路径，不得仅因此拒绝；空白、复制占位内容或缺乏基本事实说明的 Issue 退回补充。
2. **open PR 数量**：同一贡献者在每个仓库的 open PR 不建议超过 5 个，Draft PR 计入；达到或超过时，先更新、推进或关闭存量 PR，再提交新 PR。不限制各仓库的 open PR 总数。
3. **聚焦改动**：一个 PR 聚焦一个问题并关联对应 Issue；无关格式化、重排、重构或其他问题另行提交，优先复用现有模块、测试和 CI。
4. **验证证据**：修复类改动说明修复前如何失败、修复后如何通过，其他改动说明前后差异与验证结果，尽量覆盖正负例与边界。workflow、CLI、安装器和门禁脚本优先通过真实入口复放并保留输入、命令和输出；未执行的验证与未覆盖环境如实说明。文档可提供链接、渲染或前后对照，不机械套用代码单元测试；评审鼓励独立复跑并报告遗漏场景。
5. **合入闭环**：在目标分支或包含修复的版本复验原复现路径，回到原 Issue 留下修复 PR、复验结果和关闭说明；PR 放弃或关闭时，在原 Issue 更新当前状态、后续归属和下一动作。长期无响应的 Issue 先探活再关闭，补充证据后允许重开。
6. **消费场景回归**：推荐消费方根据所用资产，向 cannbot-skills 或 cannbot-knowledge 贡献关键消费场景的 CI 用例、测试数据或测试方法，由上游 CI 持续回归；消费仓本地 CI 可作为补充。

### 3.1 插件

1. 目录契约、安装与仓内维护见[仓库架构与维护](docs/repository-guide.md)；可复用 Skills 的归属见 [Q1](#q1-新-skill-放-cannbot-skills宿主仓还是随插件abcd-判据)，版本隔离见 [Q4](#q4-skills-版本如何锁定)。
2. 新插件先在 `plugins-community/` 孵化；升级 `plugins-official/` 按 [§5.1](#51-official-与-community-的定位) 和 [§5.2](#52-准入标准) 评审，由 Maintainer 作准入评估。

### 3.2 Skill

贡献流程、实现细则、测试与审批要求遵循该仓 CONTRIBUTING 和 [STANDARDS.md](https://gitcode.com/cann/cannbot-skills/blob/master/docs/STANDARDS.md)；知识接口边界见 [Q2](#q2-知识贡献到-cannbot-skills-还是-cannbot-knowledge)。

### 3.3 知识卡

生产流程、字段规范、质量门槛与审批要求遵循[该仓 CONTRIBUTING](https://gitcode.com/cann/cannbot-knowledge/blob/master/CONTRIBUTING.md)。

---

## 四、常见架构问题指引

### Q1 新 Skill 放 cannbot-skills、宿主仓还是随插件？（A/B/C/D 判据）

| 判据 | 归属 | 实例 |
|---|---|---|
| A. 面向二次开发：通过 CANN 包或某源码仓暴露的 API 开发，Skill 可脱离宿主仓独立使用 | cannbot-skills 领域目录 | PyPTO 使用 Skill（基于公开 API 开发算子） |
| B. 面向源码开发：与某仓工程结构或内部接口强耦合，离开该仓没有使用价值 | 宿主仓 `.agents/skills/` | PyPTO 框架代码中的 Pass 模块开发 Skill |
| C. 多仓复用：多个仓库共同使用公共 Skill 内容 | cannbot-skills，唯一真源 | `tools/asys-toolkit` |
| D. 跨形态复用：面向二次开发的Skill希望在源码仓也能使用，或者希望以CANNBot Agent 入口进行源码开发 | 插件组合引用 Skills，不复制真源；引用方式见 [§2.1](#21-跨仓资产的引用与同步) | `communication/hccl-aicpu-design`：按组网形态基于 HCCL 源码扩展通信算法，在 CANNBot 仓群演进 |

### Q2 知识贡献到 cannbot-skills 还是 cannbot-knowledge？

看内容如何使用，而不是看它属于哪个技术主题：

- 每次完成任务都要用或需要高频召回的内容放 Skill。Skill 挂载在全局上下文并自动触发，变更必须人工评审。
- 只在需要时检索的内容放 Knowledge，由机器摄入、校验和治理。

同一内容只维护一份。比如，Tiling 的固定步骤和必需约束放 Skill，其他策略与案例放 Knowledge。Skill 通过 Knowledge 的查询接口按需获取内容，运行期依赖须显式声明，不复制知识卡，Knowledge 也不反向依赖 Skill。

### Q3 插件和工作流放哪里，流程用什么驱动？

插件、Agent 和工作流放 cannbot 仓，领域 Skills 放 cannbot-skills，由 cannbot 仓按 [§2.1](#21-跨仓资产的引用与同步) 引用。用于驱动流程的 Skill 随工作流放在 cannbot 仓，不复制双写。

流程实现不必一刀切：单个 Skill 就能完整驱动、功能高度内聚且触发条件不与其他 Skill 冲突的场景，可以直接使用 Skill，例如通用 code-review、资料 review；需要显式编排和状态推进时，推荐 cannbot 仓的 `harness-core` + `workflows/workflow.yaml`。

### Q4 Skills 版本如何锁定？

当前由 `vendor/cannbot-skills` 锁定版本，统一安装器按插件声明选择 Skills；源码安装共享工作树，不提供场景级多版本隔离，详见[仓库架构与维护](docs/repository-guide.md)。

需要按场景隔离时，各场景用独立目录和 Agent 安装协议锁定版本。同一场景的同名 Skill 只保留一个版本，不共享可被其他场景切换的工作树；重复安装保持幂等，升级由本场景显式触发。这一演进随安装器和测试改造落地，不作为当前能力假设。

### Q5 official 与 community 内容能否互相引用？

official 不得引用 community；community 可以引用 official。需要复用 community 内容时，先按 [§5.2](#52-准入标准) 转正，再引用 official 路径。

cannbot 仓的 community 区是 `plugins-community/`；cannbot-skills 的 community 区是 `community/` 和 `plugins-community/`。official 引用 community 由 CI 阻断；存量引用也要逐项转正或拆除，不因检查未覆盖而放行。

### Q6 Skill 和 Plugin 各自如何拆分与复用？

Skill 和 Plugin 都按原子能力拆分，一个 Skill 只做一类事。Skill 之间需要复用时，只允许按“综合 → 基础”的方向依赖基础 Skill 或 MCP 服务，并在 `SKILL.md` 中声明，禁止同层、反向和循环依赖。

Plugin 之间需要复用时，优先整合为一个入口，通过场景 router 选择能力（见 [§5.1](#51-official-与-community-的定位)），不引用其他插件的私有资产。

### Q7 规则冲突时如何裁决？

资产实现或内容不一致由仓内贡献流程与 CI 处理，不纳入治理冲突。仓群规则之间、成文规则与判例之间或判例之间的冲突，按[治理指南 §四](GOVERNANCE.md#四决策与冲突裁决)处理。

对裁决结果有异议：向 SIG CANNBot 例会申请重议（双周周三 14:00–15:00，见 [SIG 页面](https://gitcode.com/cann/community/tree/master/CANN/sigs/cannbot)）。

---

## 五、准入与评审

### 5.1 official 与 community 的定位

- plugins-community 是创新驱动区：不设方向限制，新领域、新工具链、新协作模式等创新均可在此孵化；
- plugins-official 面向用户场景规划：一个领域或一套编程生态推荐一套入口，原则上不超过两套；孵化成熟的内容优先在既有场景内做子场景二次路由，而非另起 official 入口。
- 同一 AscendC 编程生态下，`<<<>>>` 直调与注册接入（ACLNN / GEIR）已形成两套入口、达到原则上限；新增能力优先进入这两个既有入口做子场景路由，不再新增第三套独立 official 入口。

因此 community → official 的升级评审除质量标准外，还须回答：该能力应成为独立入口，还是并入既有入口作为子场景？判断"定位不重叠"以入口规划为准，不以功能清单为准。

### 5.2 准入标准

| 层级 | 通用要求 | 细则 |
|---|---|---|
| 全部贡献 | CLA 已签署、遵守社区行为准则、事实来源可信、有测试/验证证据 | [community 仓](https://gitcode.com/cann/community) |
| plugins-official 插件 / official skill | 生产价值可量化、长期维护承诺与指定看护人、通过入口规划评审（[§5.1](#51-official-与-community-的定位)）、CI 全绿、经 community 或本地充分验证、不得引用 community 资产（Q5），并经 Maintainer 准入评估 | [skills 仓 CONTRIBUTING 准入标准](https://gitcode.com/cann/cannbot-skills/blob/master/docs/CONTRIBUTING.md) |
| plugins-community / 实验资产 | 基本质量（L1 通过）、事实来源可信、有使用价值、非破坏性 | 同上 |
| community → official 升级 | ≥1 个月实际使用数据 + 量化生产价值佐证 + 长期维护计划 + 入口规划评审（[§5.1](#51-official-与-community-的定位)：独立入口 or 子场景路由）+ Maintainer 准入评估与最终裁决 | 同上 |

### 5.3 Committer 任命与履职

Committer 按责任田公开任命并履行评审、分诊和看护职责；主副配置、履职审视与回流机制统一见[治理指南 §三](GOVERNANCE.md#三角色与职责)。

### 5.4 机制层贡献与批量整改

贡献不仅修复单个问题，还应优先消除同类问题的复发条件：

1. **机制优先**：对重复出现、可规则化的问题，鼓励通过 lint / CI / 结构测试、校验脚本和回归用例消除复发条件；可在本 PR 同步完成，也可另建机制改造 Issue 跟踪，不阻断聚焦修复。
2. **门禁同步**：新增或调整格式、结构、命名规则时，规则实现、测试用例和文档必须在同一 PR 更新。新增或增强门禁还须使用历史真实失效样例或受控负例验证能够拦截，并以正常样例验证不误报，说明适用范围和维护责任；尚未实现自动校验的，不得表述为“CI 已强制”。
3. **批量整改**：不影响 Agent 触发、上下文加载或执行语义的格式、命名、目录结构、元数据等规范问题，采用统一规则和脚本集中批量整改，避免零散的逐文件 PR。PR 须说明影响范围、整改规则与验证结果，不得夹带 Agent 行为变更；涉及行为的修改另提 PR。

---

## 六、许可证与免责

- 各仓默认适用 CANN Open Software License Agreement v2.0；npm 安装器实现适用 MIT；submodule 内容遵循 skills 仓许可证。
- 安全、隐私或漏洞线索不得通过公开 Issue 披露敏感复现细节、凭据或个人信息；应先联系责任田 Committer 或 Maintainer，确认非公开接收渠道。
- CANNBot 生成或修改的代码需由开发者完成编译、测试、精度验证、性能验证和安全审查后再投入使用。

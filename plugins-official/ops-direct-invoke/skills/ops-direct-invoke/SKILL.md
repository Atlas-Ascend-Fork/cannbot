---
name: ops-direct-invoke
description: 根据已确认的需求清单选择直调算子工作流模板，组装 workflow YAML 并通过脚本启动 harness 执行。
---

# 直调算子开发

本 Skill 根据脚本生成的引导文件选择引用模板，将 tasks 展开为完整 workflow YAML 后启动执行。AscendC task 使用完整任务字段及按需声明的 variables；DSL task 使用下文规定的内容字段。两者均不包含 id、depends_on 或 max_retries。模板提供节点引用、依赖与下发时确定的重试次数；task 决定具体执行和验收内容。组装完成后，调度交给 harness。

## 启动前置条件

本 Skill 接收调用方已对齐的需求清单 `work_dir/需求分析.md` 和只读环境记录 `work_dir/环境信息.md`。需求清单必须覆盖任务级 conda/Python、CANN 环境选择及修改权限；已有有效确认跨重试与 Workflow 复用。仓库级环境结果固定为 `<目标仓>/.cannbot/环境信息.md`，只复用与已选环境组合、语言和依赖范围匹配的通过记录；首次检查与缓存规则由调用方执行。

需求、环境与修改授权集中在启动前对齐；DSL 需求节点只整理已确认输入。已知缺依赖、新环境待创建或输入访问问题先落实授权内准备动作，优先作为同图前置节点或环境节点的工作，准备验收通过后再执行依赖节点；未修复前不能宣称环境通过。必须确认的选择与权限仍缺失时不启动，不用默认选项代替用户拍板。

## 运行输入

沿用用户已经提供的目标代码仓绝对路径、算子名、原始需求、目标芯片、相关资料路径、已明确的架构选择与确认记录。把这些信息、需求与环境记录的绝对路径、版本、环境选择和授权摘要组织成任务 prompt。输入与所需外部环境路径须在子 Agent 权限范围内；必要时启动前固化只读规格副本，不把所有 work_dir 外访问一概禁止。

由 PM 根据任务与当前客户端准备 provider、work_dir 和模板路径，启动输入按 `workflow-orchestrator` Skill 的契约确认，不追加额外的总启动批准。work_dir 必须设为目标仓下 `.cannbot/<任务名>/workflow<序号>/` 的绝对路径，目录由调用方分配。除仓库级环境缓存与检查日志外，本轮中间产物（需求、设计、报告、临时构建和框架状态）放在此目录下；AscendC 交付件写入目标仓约定目录；DSL 实现与验证先写入 `$WORK_DIR/operators/`、`documentation/` 等暂存目录，最终交付节点按冻结位置发布并生成 `DELIVERY.md`。不同任务隔离，同一轮中断恢复复用原目录和有效 checkout。

PM 按已确认环境生成 `$WORK_DIR/运行环境.sh`，只包含获准的 conda 激活、CANN 环境脚本加载以及 `PYTHON`（选定解释器绝对路径）等环境导出，不包含安装、升级或修复命令。用 `run_workflow.py --env-script <绝对路径>` 在同一进程环境中激活后启动 harness；启动器显式提供 `WORK_DIR` 与 `USER_PROMPT`，不把提示词中的变量说明当作 shell 已设置。节点需要重新开 shell 时沿用该激活脚本与 `$PYTHON`，不得自行改用默认解释器或另一套 CANN。

若新环境尚未创建，启动脚本只加载当前可用且已确认的准备环境；环境准备节点按授权创建后验证目标组合，并生成其激活脚本作为明确交付件，后续依赖节点必须在命令中加载该脚本。不能在环境不存在时先激活导致整个 workflow 无法启动。环境准备改变版本后重新验证受影响证据，不影响仍有效的规格、设计和只读参考资产。

DSL 交付位置由 `repo-requirement` 写入已确认需求清单，作为交付节点输入；恢复任务沿用该位置，不随内部工作目录变化重新推导。

工作流启动后不与 PM 或用户交互。各节点只使用已确认输入、固定 Skill 和本阶段下发清单，不发问卷、不等待答复，也不修改本轮 YAML。必要输入、确认或能力缺失时，executor 停止受阻操作，将证据写入本阶段报告并按 harness 原生执行协议结束；verifier 无法确认交付标准满足时判定失败，由 harness 按既定预算和耗尽策略处理。记录阻塞不代表交付通过。

PM 仅在启动前确定输入与清单、整轮退出后读取结果并处理补充确认或下一轮编排。运行中遵循 `workflow-orchestrator` Skill 的状态轮询、进度原样转发和审批要求；除此之外保持静默，仅在异常、阻塞或用户询问时按需读取日志，不反复读取产物，不向节点补发指令。

## 先生成引导，再选择调度模板

**每轮编排前先运行 [generate_workflow_guide.py](scripts/generate_workflow_guide.py)，将引导文件生成到当前 work_dir；读取模板文件名和调用时机，再打开匹配模板。** 不凭记忆选模板，也不直接拼接全部 tasks；脚本失败时先处理错误，不继续使用旧文件。恢复中断的同一轮不属于重新编排，沿用原引导和完整 YAML，不重新生成或覆盖。

```bash
python3 scripts/generate_workflow_guide.py \
  --language <ascendc|cannbot-dsl> \
  --output /absolute/operator-repo/.cannbot/abs/workflow1/workflow-guide.csv
```

脚本递归扫描本 Skill 的 `workflows/` 下全部 `.yaml`、`.yml` 模板，与命令执行目录无关。输出 CSV 只有 `file`（相对 workflows/ 的模板路径）和 `use_when`（调用时机）两列；再次运行覆盖本轮引导，不修改共享模板。按 `file` 定位完整模板后再核对节点、变量及预算。选择后向用户说明模板名称及匹配理由；用户已授权且条件明确时无需额外审批。

`--language` 取需求清单已确认的开发语言，只把扫描范围收窄到 `workflows/<语言>/`；`file` 列始终相对 `workflows/`，下游仍按同一路径定位模板。同一语言内继续按 `use_when` 选择具体模板。需求清单未确认开发语言时按缺失信息处理，不组装或启动工作流。

每个可复用 workflow 模板第二行声明 `use_when`，例如 `use_when: 一般算子开发任务`。调用时机只在模板中维护，不另存注册表；生成引导时要求其为非空字符串。该字段仅用于选择模板，组装时移除，交给 harness 的完整 YAML 不包含它。

`tasks/` 保留 `ascendc/`, `cannbot-dsl` 和 `common/`；`workflows/` 按开发语言分为 `ascendc/` 与 `cannbot-dsl/`。文档模板直接存放在 `templates/`。

当前包含 [basic](workflows/ascendc/basic.yaml)（AscendC 正式开发流程）、[feasibility](workflows/ascendc/feasibility.yaml)（独立技术穿刺）和 [op-dev](workflows/cannbot-dsl/op-dev.yaml)（CANNBot-DSL 正式开发流程）。PM 在需求确认与环境核对后，按需求清单确认的开发语言与证据选择：

- 开发语言为 CANNBot-DSL：启动 op-dev，不使用 ascendc 目录下的模板。
- 开发语言为 Ascend C 直调：在 basic 与 feasibility 之间按下列证据选择。
- 路线已有适用实现或有效设备证据、无关键技术疑点：启动 basic。
- API 组合、目标芯片适配或关键端到端链路尚无运行证据：先独立启动 feasibility，不同时展开完整黑盒矩阵与测试工程。判断依据是技术缺口，不是算子名字或复杂程度标签。
- 已知 Skill 规则冲突、必要权限或平台能力缺失：启动前先处理。不能靠穿刺绕过规则，也不能把资料调查通过当作路线验证通过。

PM 用 feasibility 的 `spike_scope` 明确候选路线、关键疑点和代表用例范围，任务 prompt 指定可复用资产及授权路径，分别绑定执行/验收 Skill。默认穿刺验证完整关键组合；例如 GQA 须覆盖 QK→Softmax→PV 的组合与同步，不以各 API 分别存在替代。范围可缩小，用户确认的接口、架构、精度和单 Kernel 等约束不降低。

穿刺验收通过后，PM 新建下一轮目录，复制有效需求和环境输入；在本轮任务 prompt 中列明前轮代码、测试入口、证据的绝对路径、版本、适用范围及使用节点，保留前轮原始证据。测试工程复用入口并扩展覆盖，算子开发复用有效实现；本轮仍完成正式全量验收。已有知识文档通过 `knowledge_documents` 传入，可省略重复搜集。穿刺失败时不启动完整开发；根据原因处理规则/环境阻塞或调整已授权候选，新一轮仍需真实穿刺证据。

PM 在下发前确定各节点的 max_retries，模板默认允许 3 次重试（首次执行加重试，最多 4 轮）；需要调整时在本轮引用图中修改，不改 task。仓内无已有算子文档时，从本轮引用图移除最后的文档准备节点，保留其他节点及验收；不新增模板或凭空创建文档。PM 编排时检查目标仓当前文档，不将历史环境缓存中的文档现状当成永久事实。

basic 默认知识搜集与黑盒测试设计并行；两者通过后依次进行测试工程开发、算子开发、白盒测试设计、代码修复、文档准备。代码修复是 basic 的默认节点，没有待修复缺陷且已有当前版本的有效全量证据时，核对并复用，记录无需修改；证据不满足条件时补齐验证。每个节点已包含执行与验收，不另设 CP。

知识搜集是可选步骤。PM 可移除本轮图中的知识搜集节点及依赖边，将黑盒测试设计改为 `0`，测试工程依赖 `0`，后续仍为 `1`～`5`。算子开发通过 `knowledge_documents` 接收中立补充文档的路径；可以引用前轮产物，也可以为“无补充文档。”，不再要求同图知识搜集上游。basic 的默认值指向 `$WORK_DIR/0.0-知识搜集.md`；删去节点或改变编号时，PM 同步清空或更新该变量。

知识搜集产物是可溯源的资料与初版实现草稿，开发可根据验证调整 API、Tiling 和分支处理，不要求照搬草稿；已确认需求仍是约束。测试工程先准备黑盒用例，算子开发由 executor 构建并执行全量黑盒，verifier 核对证据和检视代码。白盒在实现后依据源码生成可执行用例并接入已有框架。

白盒节点验收的是用例质量、框架接入及真实证据；正确用例暴露的算子缺陷记录后交下游修复，不能将该节点通过表述为算子功能通过。测试或框架自身问题仍会阻断。代码修复验收要求最终全量黑盒、白盒回归与代码检视通过，之后才能进入文档交付。

若没有适用模板，说明具体差异，不擅自套用模板或删除验收。在用户已授权范围内，按本轮交付缺口选择任务、明确依赖与预算，在当前 work_dir 组装并验证一次性 YAML。只有要发布为可复用模板时，才更新 tasks 和包含 use_when 的模板；运行期不修改已安装的共享资源。

## 维护工作流模板

引用具体 Skill 时，只写“必须加载 `<skill-name>` Skill，按其中的要求执行”，不复制其内部步骤、规则或知识。固定必需项写在 task；PM 选定与芯片、架构及已知问题匹配的专项必需项，仅在 task 声明了对应变量时分别绑定 `executor_skills`、`verifier_skills`。固定 Skill 已覆盖任务职责时不下发补充清单；算子开发、代码修复可在同一变量中接收有限候选清单及可观察的触发条件，按实际证据选择，task 不重复维护具体场景路由。节点输入、交付件和验收标准仍由 task 声明。引用文档模板只是读取资源。

知识搜集可以记录有依据的 Skill 建议及适用节点、执行/验收阶段，供 PM 在整轮退出后编排下一轮时参考；本轮下游仍使用启动前绑定的清单，不从报告自动加载新增 Skill。资料不足时可先独立组织知识搜集；该节点只交付中立参考。关键路线需要实测时选择 feasibility，不能连续用资料调查替代编译和设备验证。节点可在已下发候选内按证据选择；清单外能力仅有帮助时记为建议，缺少它导致交付标准无法满足时记录阻塞并验收失败。

**task 编写原则：goal 只写本节点要达成什么，保持简短，不含具体步骤、文件名或判定条件；approach 描述执行者如何产出交付件，可包含任务所需的功能验证、性能测试和环境探测，并保存完整原始证据，但不替验收者裁决自己的产出；procedure 是验收者的独立验收方法，交付件内容正确性与质量的检查方法、判定依据和不合格处理全部写在这里；验收者审查代码、原始结果和报告的真实性、完整性及版本对应关系，不重复运行执行者已完成的同批测试，证据不足时退回执行节点补齐；acceptance 是双方共同确认的交付件契约，只列交付件清单及可直接执行的存在性检查（如 `test -s`），不写内容正确性、质量标准、检查步骤或异常处理，与 procedure 不描述同一项检查。上游产物已由上游验收者验收通过，本节点直接使用，只确认存在且可读取，不做重复校验；使用中发现上游缺陷时按执行协议就地终止并说明，不补做上游验收。本节点发现的问题就地解决或就地终止，不得绕过或后移。** 固定报告按下文的语言目录约定命名；源码、测试和使用文档沿用已确认的项目布局，其检查命令所需小写 shell 变量在 approach/procedure 中用实际绝对路径赋值，不新增 harness 输入字段。多文件交付逐文件检查，不能用目录或任意非空文件代替。共享 acceptance 只列执行者交付件；验收报告不放入 executor 的交付清单。所有节点的 procedure 明确由 verifier 按对应语言的报告目录写入 `<id>-验收报告.md` 并检查非空，通过、失败及阻塞均落盘。executor 不生成或等待验收报告；返工反馈由 harness 传递，按角色约定处理。

引用模板格式如下，第二行是调用场景；goal、approach、procedure、acceptance、角色及其它任务内容都从 task YAML 读取，不能复制进模板：

```yaml
workflow: ops-direct-invoke
use_when: 搜集指定算子的技术资料
max_parallel: 2
nodes:
- id: '0'
  yaml: ../../tasks/ascendc/知识搜集.yaml
  depends_on: []
  max_retries: 3
  variables:
    research_focus: 重点搜集目标芯片的 API 组合和小 shape 的 Tiling 依据。
```

- 节点提供 id、yaml、depends_on、max_retries，可选 variables；max_retries 必须是非负整数，由下发方明确决定，不从 task 获取或隐式补默认值。
- id 和 depends_on 使用字符串。AscendC 引用模板的节点 id 按最长依赖路径分层，单节点层使用数字，同层并行节点使用数字.分支序号；按编号排序。组装器生成 ID 并核对其与模板声明一致，发现重复、未知依赖、环或编号不符时拒绝生成。
- `scripts/assemble_workflow.py --template <引用模板路径> --output <本轮完整YAML路径>` 按模板文件的位置解析 task 路径，展开具体内容与报告编号。输出只包含 harness 标准字段，不包含 yaml 引用或 variables 声明。
- PM 需修改预算、设置变量或省略文档节点时，将选中的引用图存为本轮 `workflow<序号>.template.yaml`，其中 task 路径转换为实际绝对路径，再调整本轮图并组装为 `workflow<序号>.yaml`。不修改已安装的共享模板或 task。
- 脚本也接受按任意顺序提供的 task 文件位置，必须同时传 `--max-retries N` 为本次所有输入设置明确预算；不同节点预算和变量值用引用模板声明。默认顺序串行，`--depends-on N:M,K` 覆盖第 N 个输入的依赖，`N:` 表示无依赖，位置从 1 开始。重复 task 可出现在不同节点，产物编号分别展开。
- task 的 procedure 若提供，必须为非空字符串列表。goal 写简短目标，approach 为执行步骤，procedure 为独立验收步骤，acceptance 为双方共享的交付件契约（只列交付件及存在性检查）。
- 更新 task 后，无需手工同步模板正文；下次组装读取最新 task 内容。已经生成的运行 YAML 保持不变，避免改变正在执行或恢复中的流程。

AscendC 过程报告写入 `$WORK_DIR/`；CANNBotDSL 执行与验收过程报告写入 `$WORK_DIR/.workflow/reports/`，文件名包含节点 ID，验收报告为 `<id>-验收报告.md`。DSL 业务产物按 task 指定目录保存；根目录承接本轮输入、工作流 YAML、引导文件、启动日志与交付入口。

## cannbot-dsl 内容引用模板

Skill 源路径统一在插件的 [plugin-sources.json](../../plugin-sources.json) 的 `skills` 列表维护；六个 `cannbot-dsl-*` Skill 与 `ops-design-paradigms` 均从 `vendor/cannbot-skills/ops/` 导入。安装器按目录名注册 Skill，task 与动态实现子图只引用其 `SKILL.md` 中的名称。迁移 Skill 时同步源路径，并在名称变化时更新调用名称；确认依赖仓版本已包含这些目录。

[op-dev](workflows/cannbot-dsl/op-dev.yaml) 是完整工作流模板：节点 id、depends_on、executor、verifier、max_retries、on_exhaust、rollback_to 和 subgraph 节点全部留在模板中，语义 id 不参与重新编号；normal 节点通过 `yaml` 键引用 `tasks/cannbot-dsl/` 下的内容 task，task 只含 title、goal、approach、procedure（可选）、acceptance、out_of_scope 六个内容字段，不包含任何调度字段。组装时按模板文件位置解析 task 路径，将内容字段合并进节点后剥离 `yaml` 键；模板与 task 同时定义同一字段、task 缺字段或合并后出现未知字段都会拒绝组装。内容字段为空列表的节点在组装时输出 warning 列出待补字段，不阻断生成。
- 所有组装输出都使用新文件，拒绝覆盖。恢复使用原完整 YAML 和 work_dir；新一轮使用新目录，保留前轮状态与证据。

## task 提示词变量

task 只为需要调用方配置的输入声明 `variables`，正文通过 `{{var:变量名}}` 引用。无需动态输入时省略整个 `variables`；引用模板也不填写空映射或统一补齐字段。变量在当前节点内生效，相同 task 被引用多次时分别绑定。

| task | 保留变量 | 用途 |
|---|---|---|
| 知识搜集 | `research_focus`、`executor_skills`、`verifier_skills` | 搜集重点及针对目标算子、芯片的专项资料能力 |
| 技术穿刺 | `spike_scope`、`executor_skills`、`verifier_skills` | 必填的穿刺范围，以及候选路线实现和检视所需能力 |
| 算子开发 | `knowledge_documents`、`executor_skills`、`verifier_skills` | 可选补充资料，以及架构实现、故障诊断和代码检视所需能力 |
| 代码修复 | `repair_requirements`、`executor_skills`、`verifier_skills` | 必填的修复目标，以及定位和检视所需能力 |
| 黑盒测试设计、测试工程开发、白盒测试设计、文档准备 | 无 | 使用已确认需求、任务上下文、上游产物及 task 中的固定 Skill |

`research_focus`、`spike_scope` 和 `repair_requirements` 同时供执行与验收使用；`knowledge_documents` 供执行者读取。`executor_skills` 仅注入 approach，`verifier_skills` 仅注入 procedure。共同需求、授权路径和跨轮复用资产记录在需求清单或任务 prompt 中，不重复设置通用补充要求变量。

补充 Skill 变量填写完整指令，例如“必须加载 `ascendc-simt-tiling-design` Skill，按其中的要求执行。”；多项可用多行文本。无补充项明确填写“无补充 Skill。”，也是 task 的默认值。专项必需项不留待节点重新决定；候选项必须逐项给出 Skill 名称和可观察的触发条件，不写“自行寻找合适 Skill”。命中才加载，未命中无需加载，多个独立条件有证据时可分别命中。加载项及选择依据写入当前阶段已有报告，无加载则记无；不新增报告文件或调度状态。阶段专用 Skill 只写入对应阶段的 Skill 变量。

PM 核对 task 固定项与补充必需项、候选均已安装、适用当前平台且符合角色权限，不重复下发固定 Skill。组合还须核对公开调用入口与产物契约：含完整开发流程的 Skill 不作为普通知识补充；只有明确支持资料查询入口时才限定使用该入口，否则按完整契约编排或报告阻塞。引用仍只写加载要求，不复制 Skill 内部步骤，不用本仓提示词豁免其规则。候选使用不扩大写入权限、不改变任务、验收标准、依赖或重试；verifier 只分析证据和判定，不修复对象、不重新构建或运行测试。必需能力超出清单、所需 Skill 不可用或能力不足时，按上述运行阻塞规则处理，不等待补发。

basic 只在算子开发、代码修复的 `executor_skills` 中提供精度错误和卡死/崩溃的候选，默认不为 verifier 或其他节点添加决策树。PM 在本轮引用图中核对、增删候选；使用自定义变量会整体替换该节点的原值，需要保留的候选须一并写入。

代码修复 task 的声明与正文示例（节选）：

```yaml
variables:
  repair_requirements: null
  executor_skills: 无补充 Skill。
  verifier_skills: 无补充 Skill。
approach:
- '{{var:executor_skills}}'
- '本轮修复要求：{{var:repair_requirements}}'
procedure:
- '{{var:verifier_skills}}'
- '本轮修复要求：{{var:repair_requirements}}'
```

PM 在引用该 task 的 workflow 节点中赋值；例如单独组织一轮修复时：

```yaml
workflow: ops-direct-invoke
max_parallel: 1
nodes:
- id: '0'
  yaml: /absolute/skills/ops-direct-invoke/tasks/ascendc/代码修复.yaml
  depends_on: []
  max_retries: 3
  variables:
    executor_skills: |
      必需：必须加载 `ascendc-precision-debug` Skill，按其中的要求执行。
      候选：复现出现卡死、超时或崩溃时，必须加载 `ascendc-crash-debug` Skill，按其中的要求执行。
    verifier_skills: 无补充 Skill。
    repair_requirements: |
      修复 /absolute/repo/op_kernel/abs_kernel.cpp 的尾块结果错误。
      复现证据：/absolute/repo/.cannbot/abs/workflow1/3-验收报告.md。
      使用已有 ST 框架回归，不修改精度阈值。
```

- 变量名只允许字母、数字和下划线，首字符不能是数字。默认值为字符串时可以省略赋值；默认值为 null 时必须提供非空字符串。显式赋值仅接受字符串，多行内容使用 YAML `|`。
- 只在 goal、approach、procedure、acceptance、out_of_scope 的文本项中替换。角色、依赖、预算等字段不使用变量；模板仍需显式声明调度信息。
- 未声明引用、未知赋值、必填缺失、非文本值、重复 YAML 键、错误占位符或替换后空提示项都会拒绝组装，不输出部分 workflow。
- 先展开 task 正文里的报告 ID，再一次性替换变量。变量值作为普通文本原样插入，不再解释其中的占位符、shell 表达式或 Python 代码；需引用前轮报告时由 PM 填写实际路径。
- variables 只用于组装，展开后从完整 YAML 移除。harness 接收标准节点字段，无需改动框架。运行中的 YAML 保持冻结，后续变量调整只能用于新的组装输出。

## 中间报告编号

所有节点输出的中间报告按 `<产出节点ID>-<报告名>` 命名。同一节点的执行报告与验收报告使用同一 ID；引用上游报告时使用产出节点的 ID。文档模板源文件保持无编号，启动前的 `需求分析.md` 和 `环境信息.md` 作为运行输入沿用原名。

子 task 不写死数字：自身报告路径使用 `$WORK_DIR/{{id}}-报告名.md`；上游报告路径使用 `$WORK_DIR/{{id:上游任务title}}-报告名.md`。组装脚本在分配节点 ID 后展开这些标记，所有说明和 `test -s` 引用同步替换。传给 harness 的 YAML 只含具体编号，不新增运行时变量或 harness 字段。

知识补充文档通过 `knowledge_documents` 按路径输入，不使用上游 ID 占位符；其他必需上游引用按依赖关系解析，重跑同名上游任务时取依赖链中最新的一次；有多个并行同名产出者或缺少产出者时拒绝组装。局部或后续轮次引用外部报告时，在本轮 task 中明确填写已存在的实际路径。改变节点顺序或依赖后重新组装，不手工修改生成模板中的编号。

例如基础模板输出 `0.0-知识搜集.md`、`0.1-黑盒测试设计.md`、`1-测试工程说明.md`、`2-实现记录.md`、`2-测试执行记录.md`、`3-白盒测试设计.md`、`3-测试执行记录.md`、`4-修复记录.md` 和 `4-测试执行记录.md`。全部节点另由 verifier 产出 `<id>-验收报告.md`；算子开发还产出 `2-代码检视报告.md`。

## 报告与返工范围

报告按当前阶段交付标准填写：知识搜集保留关键引用、建议与未知项；穿刺复用测试执行记录，提交最小代码和代表用例设备证据；正式开发保留全量测试证据与代码检视。报告只列关键结论、变更和证据路径，原始输出、用例明细与文件哈希清单单独保存，不在多份报告中重复全文。知识节点不要求所有检索文件的哈希或与关键结论无关的网络快照。

每次真实构建或测试只维护一份带节点 ID 和执行轮次的证据清单，记录输入版本与原始结果索引；其格式与复用判据见测试执行记录模板。后续节点引用具体清单与结果，并记录差异核对，不抄录整份明细。代码修复节点始终执行，但满足复用条件时无需重复构建和测试，verifier 仍独立出具本节点报告。

失败反馈由 harness 传递；摘要与报告路径的提交、返工处理分别遵循 [verifier](../../agents/ops-direct-invoke-verifier.md)、[architect](../../agents/ops-direct-invoke-architect.md) 和 [developer](../../agents/ops-direct-invoke-developer.md) 的角色约定，不在各 task 重复。正式交付仍要求当前版本的全量测试证据。

已知规则冲突、缺依赖或输入权限等确定性阻塞，应在启动前消除或明确本轮授权内的修复路径，不把原样重试当成修复。运行中条件未变时仅记录复核与缺口，不重复调查；当前公开接口只有 pass/fail，仍由 harness 按预算处理，耗尽后由 PM 处理，不新增失败类型或私有调度器。

## 文档模板

文档模板统一存放在本 Skill 的 templates/，文件名只使用文档名称，不带步骤编号。执行和验收角色按 task 中给出的 `ops-direct-invoke/templates/<文档名>.md` 定位已安装的资源并直接读取，不为使用模板重新执行入口或启动工作流。

| 文档 | 模板 |
|---|---|
| 知识搜集 | [知识搜集](templates/知识搜集.md) |
| 黑盒测试设计 | [黑盒测试设计](templates/黑盒测试设计.md) |
| 白盒测试设计 | [白盒测试设计](templates/白盒测试设计.md) |
| 测试执行记录（executor） | [测试执行记录](templates/测试执行记录.md) |
| 验收报告（verifier，全部节点） | [验收报告](templates/验收报告.md) |
| 功能证据核对参考（verifier） | [功能验收报告](templates/功能验收报告.md) |
| 代码检视报告 | [代码检视报告](templates/代码检视报告.md) |

模板规定交付格式，acceptance 列出交付件，procedure 定义内容验收方法。文档和报告按已组装 task 声明的带阶段 ID 的 $WORK_DIR 路径落盘，算子文档按仓内已有格式写入既定目录，无已有算子文档时不创建；需求清单由调用方维护。产物须与当前需求、实际代码和精度口径一致；知识草稿的假设、建议及后续实现调整须如实区分，问题及依据写入对应报告；超出当前任务范围的失效产物列明问题，不自行派发或批准继续。未开展的性能测量、回顾和经验总结不得填成已完成。

## 交给 harness 执行

先生成并读取引导、打开匹配模板，完成路线判断，准备本轮需求、环境记录与任务 prompt，核对选中模板的 Skill 清单、范围、预算及节点。以下以 basic 启动为例；独立穿刺将模板改为 ascendc/feasibility.yaml。需要调整 Skill 清单或节点图时，使用下方的本轮自定义引用图方式。脚本先在 work_dir 下生成与目录同名的完整 YAML，例如 `workflow1/workflow1.yaml`，再通过 harness 公开 CLI 执行：

```bash
python3 scripts/run_workflow.py \
  --template ascendc/basic.yaml \
  --work-dir /absolute/operator-repo/.cannbot/abs/workflow1 --provider codex \
  --harness-skill /absolute/installed-skills/workflow-orchestrator \
  --env-script /absolute/operator-repo/.cannbot/abs/workflow1/运行环境.sh \
  --prompt-file /absolute/operator-repo/.cannbot/abs/workflow1/original-task.txt
```

`--template` 相对本 Skill 的 workflows/，与当前目录无关；只能指向该目录内的引用模板。引用模板通过组装脚本展开，harness 始终收到完整 YAML。模板不因启动而修改，输出文件已存在时拒绝覆盖，并提示使用 `--yaml` 恢复。

每轮使用自定义引用图时先组装，再启动；恢复中断的同一轮只运行下面的启动命令，不重做组装，使用 `--yaml` 指向原文件，并省略 `--prompt-file` 复用已保存输入：

```bash
python3 scripts/assemble_workflow.py \
  --template /absolute/operator-repo/.cannbot/abs/workflow1/workflow1.template.yaml \
  --output /absolute/operator-repo/.cannbot/abs/workflow1/workflow1.yaml
python3 scripts/run_workflow.py \
  --yaml /absolute/operator-repo/.cannbot/abs/workflow1/workflow1.yaml \
  --work-dir /absolute/operator-repo/.cannbot/abs/workflow1 --provider codex \
  --harness-skill /absolute/installed-skills/workflow-orchestrator \
  --env-script /absolute/operator-repo/.cannbot/abs/workflow1/运行环境.sh \
  --prompt-file /absolute/operator-repo/.cannbot/abs/workflow1/original-task.txt
```

`--yaml` 与 `--template` 互斥且必选其一。`--yaml` 只接受完整 harness YAML，不展开引用或修改预算。脚本不自动选择模板、决定重试次数或判断文档是否需要；这些由 PM 在下发前确定。

`--prompt-file` 的 UTF-8 内容原样作为 harness 的 `--prompt` 参数传递，也可直接使用 `--prompt '任务内容'`，二者互斥。首次运行必须提供原始任务；再次调用已有运行时可省略，由 harness 决定恢复行为。省略 prompt 不会清除耗尽状态。

`--env-script` 为可选的 Bash 激活脚本；本流程按已确认环境提供，旧调用省略时保持继承环境的行为。脚本在实际子进程中加载，前台、tmux 后台及恢复均生效，不依赖 tmux server 的旧环境。激活失败不启动 harness。恢复时传入同一脚本，不重新选环境，不在其中安装或修改依赖。

`--harness-skill` 默认取启动脚本调用路径所在安装 Skill 的同级 workflow-orchestrator 目录；直接从源码目录调用或布局不同时显式指定。脚本只调用该目录下公开的 orchestrator.py CLI，不读取或修改内部实现。

默认使用 tmux 后台启动，返回会话名及 work_dir/orchestrator.log；日志追加写入，恢复时保留前次退出记录。启动成功不代表任务执行成功：用脚本打印的 tmux has-session 命令检查会话，结束后完整回传日志及其中的 exit status。同一 work_dir 使用固定会话名，已有活动会话时启动失败，不覆盖其运行。

加 `--foreground` 可前台运行，直接输出 harness 日志并返回其退出码；加 `--dry-run` 透传原 harness 的模拟执行选项。启动脚本不自行重试或读写调度状态。

每个普通节点先由 executor 执行，再由 verifier 核对 acceptance 交付件并按 procedure 审查内容与证据。harness 把 goal、acceptance 和 out_of_scope 发给两者，把 approach 仅发给 executor，把 procedure 仅发给 verifier。executor 据共享标准交付，负责构建与本阶段规定的测试范围（穿刺为代表用例，正式交付为全量），按测试执行模板保存命令、退出码、源码/测试/构建产物哈希、加载路径及逐用例原始结果。verifier 只读核对证据有效性及交付物质量，并独立检视代码；不重复构建或测试，不接受只有通过自述的证据。验收报告只由 verifier 交付。执行与验收结果遵循 harness 注入的当前协议；verifier 须按框架提示调用公开裁决命令，文本回复不能代替裁决；调度、同节点重试和耗尽处理均使用框架原生机制。

整轮退出后，PM 读取日志、退出结果和真实产物，汇总已完成步骤及阻塞证据。交付目标未满足时，使用 workflow2 等新目录，根据已完成任务、有效产物与剩余目标重新编排本轮 YAML，安排必要的修复与验收；复用产物不要求沿用前轮任务图。同一轮中断恢复则沿用原 YAML、work_dir 和环境脚本。需求、环境选择与修改授权按整个任务继承，启动输入确认仍遵循调度 Skill 的契约。

新轮引用或复制有效输入、只读示例仓、代码和证据，记录原路径、版本与适用范围，不复制 `.workflow/` 或修改通过状态；需要固定文件名时映射到本轮约定位置，只有输入、实现或环境变化影响的证据才重做。失败摘要及报告路径仍由 harness 回传；DSL 子图回滚仍使用原生机制。接口回归不证明真实 Agent 的修复效果，不另写状态机或无界重试脚本。

入口由工作区 PM 在当前用户会话中承接；PM 不进入调度图。节点角色仅使用 ops-direct-invoke-architect（方案）、ops-direct-invoke-developer（代码、调试与文档）及 ops-direct-invoke-verifier（验收与检视）。角色信息由安装后的客户端角色配置和 executor/verifier 名称衔接，不在任务里额外要求读取 agents 文件。真实 provider 的角色和 Skill 加载仍需验证，模拟执行通过不代表角色权限或 NPU 实测通过。

范围以所选工作流为准：AscendC basic 包含本地开发与功能交付，DSL op-dev 还包含性能采集、优化与回归；均不包含 PR、外部 CI 和合并。Skill 正文和参考资料只描述自身职责，不调用或路由到其他 Skill；跨 Skill 的组合由 Agent 或 task 的 approach/procedure 显式声明。

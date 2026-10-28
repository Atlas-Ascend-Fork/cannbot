# AscendC / CANNBot-DSL 性能调优快速入门

`ops-perf-optimize-workflow` 用于完成 AscendC / CANNBot-DSL 算子的端到端性能调优：冻结用例、建立可信基线、分析 profiling、隔离实施候选、执行精度与性能门禁，最后完成全量验收和原工程回集成。

本文面向使用者，说明如何安装、发起任务、查看进展和理解结果。精确的机器执行规则以 `skills/ops-perf-optimize-workflow/references/workflow-contract.md` 为准。

支持两种使用方式：**自动化调优**由工作流按已确认目标连续推进；**交互式调优**由用户通过多轮对话查看证据、选择方向、调整约束并决定何时继续。两者共用已安装的 Skills，交互式调优不是新的 `tuning_mode`，也不改变精度和性能验收要求。

## 触发边界

安装插件不会让所有性能相关问题都进入调优工作流。只有用户明确要求对某个具体 AscendC 算子或代码目录执行性能优化/性能调优时才触发。

会触发：

- “请优化 `maximum` 算子的性能”；
- “对 `/path/to/operator` 做性能调优，性能用例是 `/path/to/cases.csv`”；
- 上下文已有唯一算子时，“继续把这个算子的耗时降下来”。

不会触发：

- 安装、配置或使用咨询；
- 分析已有报告、日志、profiling 或加速比；
- 询问 msprof、cases.csv、性能指标的含义；
- 精度排障、普通代码检视；
- 只说“这里有性能目标”但没有要求执行优化，或没有具体目标算子。

不满足触发条件时，客户端应按普通请求直接回答，不加载工作流、不创建输出目录，也不派发性能调优专家。

## 1. 安装

### npx 安装（推荐）

**必须在实际要执行性能调优任务的工程目录下运行安装命令**。npx 安装器会把 Skills、`AGENTS.md` 和 `.cannbot/` 资产写入当前目录，因此不要在本仓库根目录、home目录或其他无关目录执行。

```bash
cd /path/to/your/tuning-project
npx @cannbot-plugin/cannbot@latest install ops-perf-optimize --tool opencode
```

`--tool` 可选 `opencode`、`claude` 或 `codex`。npx 安装会自动获取并复制完整的 Skill 资源，不需要克隆本仓库或初始化依赖子模块；后续也必须在同一个工程目录下启动 Agent 并执行调优任务。

### 源码安装

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
bash /path/to/cannbot/plugins-official/ops-perf-optimize/init.sh project opencode /path/to/your/project
```

`--tool` 可选 `opencode`、`claude` 或 `codex`。后续执行优化任务时，Agent 必须在安装目录 `/path/to/your/project` 下打开，工作流依赖该目录中的 Skills、`AGENTS.md` 和 `.cannbot/` 资产。

安装会自动完成：

1. **Skills 安装**：本插件自带的 9 个工作流 Skill（`ops-perf-optimize-workflow` 入口、五个阶段、验收标准、性能检视与特征提取）从插件目录软链，17 个共享 AscendC Skill（profiling、精度调试、Blaze 路由等）从 `vendor/cannbot-skills` submodule 软链到目标项目的工具 skills 目录；源码安装可用 `--skills <SHA|本地仓路径>` 锁定共享 Skill 版本。知识检索 Skill 使用下节知识仓自身的安装器，不再从该 submodule 安装旧版；
2. **参考仓准备**：浅克隆 cannbot-knowledge 知识仓、asc-devkit（经 `ascendc-docs-search` 清洗）与 cann-samples 到 `<项目>/.cannbot/dependencies/ops-perf-optimize/`，asc-devkit/cann-samples 在项目根暴露同名入口。克隆知识仓不等于已准备检索 Skill、资源与索引，需完成下节 consumer 安装；断网/离线时告警跳过，`CANNBOT_SKIP_DEPENDENCY_REPOS=1` 可整体关闭；
3. **主 Agent 与主提示词**：`AGENTS.md` 作为 `perf-optimize` 主 Agent 安装到客户端 agents 目录（opencode/claude 为 `.opencode/agents/perf-optimize.md`、`.claude/agents/perf-optimize.md`，codex 为 `.codex/agents/perf-optimize.toml`），并以标记块写入项目 `CLAUDE.md`（claude）或 `AGENTS.md`（其他工具）；五个阶段仍派发给客户端通用 subagent；
4. **hook 注册**（仅 claude 工具）：SessionStart 路由提示注册进 `.claude/settings.json`。

命令可以幂等重跑，用于刷新插件或复查安装。各客户端通用参数与安装控制详见[插件安装与工作流](../../script/docs/cannbot-workflows.md)。

### 知识库安装与配置

知识库用于方案设计和实施约束补证，安装方式参考 [ascendc-ops-perf-evolution 快速入门](../../plugins-community/ascendc-ops-perf-evolution/quickstart.md)，实际参数以[知识仓当前安装器](https://gitcode.com/cann/cannbot-knowledge/blob/master/install.sh)为准。在同一调优工程中安装 consumer：

```bash
# 使用插件已克隆的知识仓；opencode 可换成 claude 或 codex
bash /path/to/your/tuning-project/.cannbot/dependencies/ops-perf-optimize/cannbot-knowledge/install.sh \
  opencode /path/to/your/tuning-project consumer
```

若自动克隆被跳过，或使用 Marketplace 安装插件，可先检出知识仓：

```bash
git clone https://gitcode.com/cann/cannbot-knowledge.git /path/to/cannbot-knowledge
bash /path/to/cannbot-knowledge/install.sh opencode /path/to/your/tuning-project consumer
```

该安装器安装 `knowledge-query` 与 `ascendc-api-knowledge-query`，保留到完整知识仓的链接，准备运行依赖、文档/固定提交源码与检索索引，并在调优工程 `.cannbot/knowledge.env` 写入知识仓位置。普通检索可通过安装器 `--platform <已确认平台>` 配置缺省平台，任务目标不同时仍须按 Query 规则显式指定。

知识仓根是包含 `governance/` 与 `knowledge/` 的目录。可用 `export CANNBOT_KNOWLEDGE_ROOT=/path/to/cannbot-knowledge` 覆盖，或在工程/祖先的 `.cannbot/knowledge.env` 配置同名变量；Query 也可通过真实 Skill 链接定位其知识仓。仅配置路径不能替代完整 consumer 安装，不要独立复制检索 Skill。

升级已有工程时，先停止使用旧检索入口，按知识仓安装器提示迁移旧 `knowledge-query` 副本或链接；旧 Marketplace 依赖 `ops-perf-optimize-kb-skills` 也应卸载，避免继续加载 cannbot-skills 中的旧脚本。插件不再依赖该 bundle。

知识库不可用时，调优报告记录 `kb_unavailable` 与具体原因，并以无知识增强模式继续；精度与性能验收要求不变。索引缺失、损坏或陈旧交由知识仓安装器/维护者处理，调优阶段不自动重建。有效零命中记录为知识缺口，不视为技术不可行。

### 验证安装

统一安装器输出 `Installed ops-perf-optimize@4.1.0 for <tool>`、skills/agents 数量及 quickstart 路径即表示插件安装完成。也可在目标项目确认 `.agents/skills/`（opencode/codex）或 `.claude/skills/`（claude）下的 26 个插件 Skill、`.opencode/agents/perf-optimize.md`（claude/codex 为对应 agents 目录）中的主 Agent，以及 `.cannbot/plugins/ops-perf-optimize/` 下的 hooks 资产与 `quickstart.md`；工作流定义和脚本随 `ops-perf-optimize-workflow` Skill 的 `workflows/`、`scripts/` 目录安装。完成知识仓 consumer 安装后，另有两个知识消费 Skill 及 `.cannbot/knowledge.env`。

从调优工程运行一次只读覆盖检查（所有客户端均可使用安装器创建的 `.agents/skills/` 规范入口）：

```bash
cd /path/to/your/tuning-project
python3 .agents/skills/knowledge-query/scripts/knowledge_query.py discover --json
```

正常结果包含知识仓 `root` 与实际覆盖计数。调优中的检索流程以[当前 knowledge-query Skill](https://gitcode.com/cann/cannbot-knowledge/tree/master/.agents/skills/knowledge-query)为准：确认任务目标平台 → 按单个决策 `search` → 根据返回的路径、标题和描述选卡 → 阅读全文并按需沿链接补证；复杂性能任务按该 Skill 保存检索审计与真实实验结果。

## 2. 发起任务

| 使用方式 | 适用场景 | 如何发起 |
|---|---|---|
| 自动化调优 | 目标和约束明确，希望连续完成调优与交付 | 提供完整请求或已确认的 `optimization-request.json` |
| 交互式调优 | 希望先理解原理、审阅瓶颈，再逐步选择和验证方案 | 每次说明本步任务、约束和暂停点，参考本节末的多轮对话示例 |

### 使用方式一：自动化调优

直接用自然语言描述即可。建议明确写出代码、目标 SoC、用例、功能模式、优化目标、Python、CANN 和输出目录。输入确认后，工作流按轮次或目标连续推进；出现需要人工决策的缺口时仍会报告。

#### 启动时确认

| 输入 | 说明 |
|---|---|
| 待调优代码目录 | 可运行的直调 demo，或注册算子工程 |
| 目标 SoC | 本次会实际完成构建、功能和性能验证的代际；只验证 A5 就只写 Ascend950 |
| 性能用例 | 需要重点优化的用例，通常为网络用例 |
| 功能用例模式 | 用于验证性能优化是否引入功能问题；可复用性能用例、使用已有功能用例或自动生成功能用例 |
| 性能对标 | 其他算力卡、理论上限、小算子或原始实现；记录逐 case 目标比例 |
| 优化目标 | 可按轮次或具体指标调优；按轮次默认 3 轮，按指标可指定“有效 case 几何加速比 ≥ 1.2”或“指定 case 耗时 ≤ 10us” |
| Python 环境 | Python 可执行文件，以及需要时的激活命令 |
| CANN 环境 | `source .../setenv.bash` 等加载命令，或明确继承当前环境 |

确认后的输入会保存为 `optimization-request.json`。它包含模式、目标 SoC、代码/用例路径、功能模式、逐 case 对标配置、优化目标、Python 和 CANN，不包含某次运行的输出状态。

下次可以直接说：

```text
使用 /path/to/optimization-request.json 对其中的算子做性能优化，
本次输出到 /path/to/new-output。
```

工作流会先展示 JSON 摘要并校验路径和 Python 版本；仍有效时直接启动，不重复询问。环境失效或用户要求修改时，重新确认并生成新的 request。

#### 提示词范例

##### 性能用例 + 现有功能用例：按指标调优

```text
算子基线代码目录：/path/to/xlog1py_register/。
目标 SoC：Ascend950；工程其他代际必须保留原路径。
性能用例：/path/to/performance.csv。
功能用例：/path/to/functional.csv。
优化目标：有效 case 几何加速比 ≥ 1.2，最多优化 5 轮。
Python：/path/to/venv/bin/python；CANN 环境继承当前环境。
中间文件输出到 /path/to/output。
```

##### 性能用例 + 自动生成功能用例：按轮次调优

```text
优化 /path/to/operator。
目标 SoC：Ascend950；工程其他代际必须保留原路径。
性能用例是 /path/to/performance.csv。
功能用例由工作流自动生成。
固定优化 3 轮。
Python 使用 /path/to/venv/bin/python，CANN 环境继承当前环境。
中间文件输出到 /path/to/output。
```

### 使用方式二：交互式调优

按以下三步推进，将路径和目标 SoC 替换为实际配置。

#### Step 1：性能分析与方案生成

```text
对 /path/to/operator/，先只采集性能并分析瓶颈、输出方案，完成后暂停，等我选择再实施。
使用 ops-profiling 采集，结合 ascendc-perf-optimize 和 ascendc-performance-best-practices 分析。
目标 SoC：Ascend950；用例：/path/to/cases.csv；Python：/path/to/venv/bin/python。
CANN：source /path/to/Ascend/cann/bin/setenv.bash；输出到 /path/to/output/。
```

**Step 1 完成后，用户可以自主审视方案，并与 Agent 对话修改方案；确认要实施的方案后，再进入 Step 2。**

#### Step 2：按照生成的方案进行优化

```text
请对 /path/to/operator/ 做性能优化，采用审阅修改后确认的 <方案编号>。
沿用已确认的环境、用例、约束和输出目录，实施方案并验证精度与性能。
输出候选的逐 case 性能对比和精度结果，完成后暂停，等我确认再做全量验收与回集成。
```

#### Step 3：全量验收与原工程回集成

```text
使用上一步保留的可信实现，完成全量精度与性能验收，并回集成到 /path/to/operator/。
验证原工程调用方式，输出最终逐 case 性能对比、代码位置、验证报告和复现命令。
```

## 3. 工作流会做什么

以下阶段与第 4–10 节描述正式优化工作流。交互式使用中单独的原理解释、画图或采集分析任务，只交付该步约定的结果；进入完整优化后再按这些规则验收。

| 阶段 | 执行内容 | 主要交付 |
|---|---|---|
| 基线评估 | 依赖/NPU 检查、可选用例生成、逐 case 制定性能目标 | 环境检查报告.md、性能目标.md |
| 前处理(DSL程序调优跳过) | 剥离独立 demo，保持原调用方式，TTK 基线精度 | 剥离映射、构建/加载与精度证据 |
| 诊断分析 | 统一性能采集、逐 case 瓶颈、最多三套方案 | analysis.md、实施契约、冻结 scope |
| 实施验证 | 隔离实施、符合性/功能/序列门禁、性能终选、demo 全集验收 | 候选证据、最终 demo、逐轮报告 |
| 后处理 | 回集成原工程、芯片族保护、功能和性能两类全集检查、退化回原代码并复验 | 逐 case 性能 gate、路由证据、VERIFY_REPORT.md |

诊断分析与实施验证的方案设计、方案实施经 `knowledge-query` 引用 cannbot-knowledge 知识卡支撑（方案与符合性证据记录引用的 doc-id）；知识库不可用时以无知识增强模式继续，不改变精度与性能验收要求。

诊断与实施按已有轮次/目标循环。generalization 保留泛化全集、分层调优及涉及/不涉及路由检查。后处理对两套全集的每个 case 都检查修改前后性能；出现有效退化就将真实输入条件对应的范围切回原实现，新路由重新验证。不能用平均收益覆盖局部回退。

910b 和 910_93 默认同族、950 独立一族；未涉及芯片族的实现与依赖保持不变。同族归类不扩大实际验证范围，未验证型号仍走原代码。

同一代码、二进制、用例、设备和采集协议身份只保留一次可比较性能采集。下一轮直接复用上一轮终选证据，不为“最终确认”重复 profiling。

## 4. 人工如何介入

冻结输入并初始化状态后，输出目录包含：

```text
optimization-request.json 已确认的目标、环境和输入意图
run-manifest.json       冻结输入、配置、用例数量、SHA 和选择记录
workflow-state.json     阶段事件、证据身份、精度诊断和人工决策
性能调优报告.md          持续更新的现场报告，同时也是最终报告
```

执行中可以随时打开 `性能调优报告.md`，查看：

- 当前阶段、已耗时和最近进展；
- 已证实的基线失败和候选新增/恶化失败；
- 当前诊断假设、已排除假设和下一步；
- 每个候选的功能/性能状态；
- 每轮选择及安全恢复点；
- 每轮结束自动刷新的逐 case 耗时、加速比与分类，以及本轮和累计的总体性能结果；
- 是否正在等待人工决策。

常见人工介入点：

1. 性能全集超过 50 条时，确认工作流提出的 50 条代表性调优子集。
2. 功能库存缺少显式 golden、阈值或接口字段时，补充库存框架的可信生成契约。
3. 外部设备、环境或权限阻塞时，按报告中的安全恢复点处理后继续。

## 5. 如何理解精度结果

精度用例出现 FAIL 不等于整个任务失败。工作流会在未改动的原始实现上，以相同 case、seed、比较器、环境和构建身份复现：

| 情况 | 结论 | 后续动作 |
|---|---|---|
| 原始实现同样失败，候选没有恶化 | `known_baseline_failure` / `conditional_pass` | 保留该 case，流程继续 |
| 原始失败、候选改善或通过 | `improved_baseline_failure` | 流程继续 |
| 原始通过但候选失败，或候选误差恶化 | `new_or_worsened_failure` | 只修复或淘汰当前候选 |
| 尚无可信原始对照 | `under_diagnosis` | 持续诊断，不能冒充基线失败 |

工作流不会删除失败 case、放宽阈值或替换 golden 来制造通过；已知基线失败也不能作为终止整个 workflow 的理由。

## 6. 输出目录

典型结构：

```text
output/
├── optimization-request.json
├── run-manifest.json
├── workflow-state.json
├── 性能调优报告.md
├── baseline/
│   ├── 环境检查报告.md
│   ├── preflight-report.json
│   ├── 性能目标.md
│   └── performance-targets.json
├── performance-full-cases.csv
├── performance-tuning-cases.csv
├── functional-full-cases.csv 或 functional-full/
├── functional-acceptance-cases.csv
├── round1/
│   ├── analysis.md
│   ├── implementation-contract-<scheme>.json
│   ├── candidates/<scheme>/...
│   ├── perf/<scheme>/effect-details.csv
│   ├── perf/<scheme>/effect-summary.json
│   └── selection.json
├── round2/...
├── final-functional-regression.md
├── final-performance-comparison.md
├── final_optimized/
└── integration/
    ├── postprocess-performance-<soc>.json
    ├── regression-routing.md
    └── VERIFY_REPORT.md
```

generalization 模式以 `generalization-full-cases.csv`、每轮 `generalization-tuning-cases.csv` 和 `optimized-involved-cases.csv` 替代 standard 的性能全集/调优子集布局。

注册与直调输入都会产生集成计划和验证报告；用户明确要求 CANN-Bench 时会增加相应评测报告。

## 7. 轮次和停止方式

- 按轮次：未指定时提议并由用户确认默认 3 轮；也可固定为 N 轮。
- 按目标：必须确认可从落盘证据计算的指标、比较方向、数值和单位；达标后结束性能循环。
- 按目标可附加最大轮次；若不设置，不会暗中加上轮次上限。

没有有效提升时可以可信地保留原始基线，并记录 `NO_MATERIAL_IMPROVEMENT`；不会为凑结果交付有精度回归或未实测的组合。

精度诊断不受轮次设置限制。轮次约束控制性能优化循环，不会把尚未完成的精度问题强行截断。

## 8. 耗时预期

确定性输入准备通常是秒级。以历史 `dequant_swiglu_quant` 的 32 条性能用例、200 条功能用例和 40 条验收子集实测，新脚本耗时约 **0.15 秒**、峰值内存约 **20 MB**。

端到端时间主要取决于：

- 单算子工程剥离、真实构建及加载产物身份验证；
- NPU 可用性及每个身份的一次 profiling；
- 候选数量和轮次；
- 功能全集规模；
- 精度问题的真实诊断复杂度。

因此“功能集准备”不应再出现分钟级编排耗时，但复杂精度诊断会持续到问题被分类、候选被修复/淘汰或确认存在外部资源阻塞。

## 9. 恢复与版本兼容

中断后使用同一输出目录继续时，工作流会验证 `run-manifest.json` 和已完成 artifact 的 SHA，只复用仍然有效的保存点。输入身份改变应新建 run；工作流版本改变需要影响审计，只失效受影响阶段。

v3 之前的历史运行目录继续作为原始证据保留，但不能直接当作 v3 状态自动恢复。需要重新运行时，应创建新的 v3 输出目录，避免把旧状态和新契约混在一起。

## 10. 完成判定

任务完成时应能回答：

- 已确认的优化目标、Python 和 CANN 环境是什么；
- 当前模式要求的冻结集合分别有多少 case，身份和选择规则是什么；
- 每个候选为什么通过、淘汰或未进入性能比较；
- 每轮最终选择了什么，保留和放弃了哪些手段；
- 最终功能全集是否 `strict_pass` 或可信 `conditional_pass`；
- 原始基线到最终实现的有效 case 提升、回退和几何加速比；
- 注册输入是否已回集成并通过接口验证；
- 当前报告、机器状态、源码和二进制身份是否一致。

如果这些结论不能从落盘证据和 `性能调优报告.md` 中直接找到，工作流还没有完成。

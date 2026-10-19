# HCCLBot 算法模板开发快速入门指南

## 概述

HCCLBot 当前对外支持 **AICPU 标准通信算子开发**，在 HCCL 源码仓 `src/ops/` 标准结构中新增/修改算法模板（template）、执行器（executor）、选择器（selector）。CCU/AIV/HostDPU 暂不支持，相关请求会在路由阶段阻断。

### 适用场景

| 场景 | 说明 |
|------|------|
| 新增 AICPU 算法模板 | 为已有算子类型新增 AICPU 算法分支（如 AllReduce Mesh1D OneShot 变体） |
| 修改已有算法 | 定位到具体 template 文件修改逻辑 |
| 为新拓扑添加算法分支 | 在 selector 中按拓扑条件选择新算法 |

### 支持算子类型

AllReduce / AllGather / ReduceScatter / Broadcast / Reduce / AlltoAll / Scatter / Barrier

## 一、环境搭建

### 前置条件

- 已安装 Git 和 Node.js **≥ 20**，且 `git`、`node` 命令在当前终端的 `PATH` 中可用
- 已安装 CANN Toolkit（建议 ≥ 9.0.0）
- 已安装 OpenCode

`init.sh` 是 Bash 入口，实际安装由 Node.js 程序执行。统一入口会先检查 `node` 是否可运行且版本 ≥20，不满足时显示安装指引并退出，不会自动安装 Node.js。即使 OpenCode 已能启动，也需单独确认 `node` 可用。使用 npm/npx 安装方式时还需对应命令可用。

安装前检查：

```bash
git --version
node --version       # 应为 v20 或更高版本
opencode --version
```

> 已有 HCCL/HCOMM 仓库和 CANN 安装时，在需求中明确路径或环境文件，优先复用并执行只读检查；只有缺项时才按需准备，不重复下载已有仓库。环境工作目录 `WORKSPACE` 与插件安装目标目录可以不同。

### OpenCode 安装

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot
bash plugins-official/hccl-op-generator/init.sh project opencode   # 项目级（默认）
opencode
```

`init.sh` 默认安装到 cannbot 仓根，当前仅支持项目级安装。从插件目录执行 `bash init.sh` 也使用该默认目标，安装后需回到 cannbot 仓根启动 OpenCode。安装目录如下：

```text
<目标项目>/
├── AGENTS.md                              # HCCLBot 编排指令
├── .agents/skills/                        # 8 个技术 Skill
├── .opencode/
│   ├── agents/                            # 4 个子 Agent
│   └── cannbot-plugin.json                # 安装记录与版本
└── .cannbot/plugins/hccl-op-generator/
    └── workflows/                         # 工作流、模板与校验脚本
```

`init.sh` 不探测 HCCL/CANN 环境。源码安装的 Skills 软链接到 `vendor/cannbot-skills/communication/`；安装器会初始化公共 Skill 子模块并获取与 cannbot 当前分支同名的最新版本，缺少同名分支时回退到 `master`。

### 使用本地 Skill 开发仓

测试个人仓或本地未提交的 Skill 修改时，使用 `--skills` 指定本地 `cannbot-skills` Git 工作树根目录：

```bash
cd /path/to/cannbot
bash plugins-official/hccl-op-generator/init.sh project opencode /path/to/your_project \
  --skills /path/to/cannbot-skills

cd /path/to/your_project
readlink -f .agents/skills/hccl-aicpu-best-practice
# 应指向 /path/to/cannbot-skills/communication/hccl-aicpu-best-practice
```

本地路径模式直接链接指定工作树，不拉取或更新公共 Skill 子模块；后续本地修改会通过软链接生效。安装后重新启动 OpenCode 并新建会话，核对 `.opencode/cannbot-plugin.json` 中 `source.revisions.cannbot-skills` 的 `selection` 为 `local-path`，且 `path` 指向该本地仓。记录中的提交 SHA 是安装时的版本，不会随之后的文件修改自动更新。

### 环境复用与安装目标

若已在 HCCL 源码仓工作，可按下方「在其他目录执行」指定该仓为安装目标。安装器保留目标根 `AGENTS.md` 原有内容，在 `<!-- cannbot:hccl-op-generator:start -->` 和对应结束标记之间追加或更新插件说明。

Claude Code 的源码仓 `.claude-plugin/marketplace.json` 是另一条安装途径：在 cannbot 仓根先执行 `claude plugin marketplace add .`，再执行 `claude plugin install hccl-op-generator@cannbot --scope project`；它不使用 OpenCode 的 `init.sh`，也不会因为克隆源码仓而自动安装。

首次提交算子开发需求时，HCCLBot 按工作流确认并加载已有环境，先执行 `hccl-env-check`；全部满足要求时直接复用，缺项时才按需准备并复检。只有路径、没有环境文件时，按已确认路径生成供后续 Agent 加载的文件。变量缺失时报告缺项，不自行搜索 `~/Ascend` 或系统安装。环境准备脚本只适用于其约定的 workspace 布局，不能为套用布局而重复 clone 用户已有仓库。下载、安装或仓库更新遵守用户授权，环境未就绪时报告阻塞原因。

### 在其他目录执行

```bash
# 安装到指定项目
bash /path/to/cannbot/plugins-official/hccl-op-generator/init.sh project opencode /path/to/your_project
cd /path/to/your_project
opencode
```

### 验证安装

以下命令在安装目标项目根目录执行；默认目标是 cannbot 仓根。

```bash
opencode agent list
# 应看到 hccl-architect / hccl-developer / hccl-reviewer / hccl-verifier

ls .agents/skills/
# 应看到 8 个技术 Skill

cat .opencode/cannbot-plugin.json
# 找到 plugins 中 plugin 为 hccl-op-generator 的记录
# 检查 skills（8 项）/ agents（4 项）及 source.revisions
```

## 二、快速上手

### 启动

在安装目标项目根目录启动 OpenCode：

```bash
opencode
```

### 开发算子示例

本地已有hccl代码：/xxx/hccl,请按 HCCLBot 多 Agent 工作流处理以下 AICPU 开发需求：完成aicpu引擎的allgather ring算法,完成后给我呈现报告

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

HCCLBot 会先判定引擎，AICPU 任务按工作流分派给四个 Agent。把**算子类型**（AllReduce/ReduceScatter 等）、**算法名称**、**引擎**、**拓扑场景**、**数据类型**写清楚即可。

### 核心工作流

```text
AICPU: 环境 → 设计 → 基线 → 开发 → 独立检视 → 候选构建与双轨测试 → estimate 性能估算 → 完成
CCU/AIV/HostDPU: 暂不支持，路由阶段阻断
```

双轨功能验证通过后，Verifier 对同一候选算法执行 estimate，默认使用 112 组网；用户指定组网时按需求调整 `mock-comm`。估算结果写入 `TEST_REPORT.md` 并在最终汇报中呈现，包含实际条件、算法耗时、观察、限制和证据路径。缺少成功估算或原始证据不能宣布完成；该结果是仿真估算，不设性能收益阈值。

AICPU 只有同一源码身份上的 Review PASS 与双轨 Test PASS 同时有效才能完成，详见 AGENTS.md。

### 产出物示例

算法模板开发完成后，产出在 `${HCCL_ROOT}/src/ops/{op_type}/`：

```
${HCCL_ROOT}/src/ops/all_reduce/
├── all_reduce.h / .cc                 # 算子入口（已有）
├── selector/
│   ├── all_reduce_auto_selector.h     # 选择器（已有）
│   └── all_reduce_auto_selector.cc    # 修改 SelectAicpuAlgo() 添加分支
├── algorithm/
│   ├── executor/
│   │   ├── ins_v2_all_reduce_sole_executor.h / .cc  # 已有 Sole 执行器（复用）
│   │   └── ins_v2_all_reduce_{new_algo}_executor.cc # 新建（若需自定义编排）
│   └── template/
│       ├── aicpu/
│       │   ├── ins_temp_all_reduce_mesh_1D_one_shot.h / .cc  # 已有（参考）
│       │   └── ins_temp_all_reduce_{new_algo}.h / .cc        # 新增模板
│       ├── aiv/                      # AIV 引擎（非本范围）
│       └── ccu/                      # CCU 引擎（非本范围）
├── op_graph/                          # 图模式 proto
├── CMakeLists.txt
└── docs/                              # 开发文档（工作流生成）
    └── <task-id>/                     # AICPU 每个任务独立目录
        ├── task-index.json
        ├── environment.md
        ├── TASK_SPEC.md / DATAFLOW_SPEC.md
        ├── dataflow/                   # 按 template 一份实际 Dataflow Spec（需要时）
        ├── DESIGN.md / PLAN.md / TEST_PLAN.md
        ├── BASELINE_REPORT.md / LOG.md
        └── REVIEW.md / TEST_REPORT.md / HANDOFF.md
```

`DATAFLOW_SPEC.md` 始终作为适用性索引存在：不需要数据流规格时标记 `NOT_REQUIRED`；需要时索引到 `dataflow/*.md`。AICPU 产物使用 `workflows/templates/` 中的 `aicpu-*-template.md`，`DESIGN.md`、`PLAN.md` 和 `LOG.md` 使用同目录共享模板。模板头部的 owner、状态、源码身份、revision 和哈希字段用于状态门禁，不能删除。

HCCLBot 在首次调用 Verifier 前还会创建任务专属外部证据目录，并写入 `task-index.json.external_evidence_roots`。构建日志、包归档和源码快照只能由 Verifier 写入该白名单目录；目录必须位于 HCCL 源码仓之外，并以任务 ID 单独隔离。

每次状态推进前，HCCLBot 会自动调用 `workflows/scripts/validate_aicpu_artifacts.py` 检查产物、真实 Agent 调用、源码身份、依赖哈希、角色写入边界及旧 Review/Test 失效状态。该结构门禁通过不等于功能测试通过，最终仍以 Reviewer 和 Verifier 针对同一源码身份的真实证据为准。

引擎路由、正常阶段角色和失败修复链由 `workflows/scripts/workflow_policy.py` 自动复核。例如在安装目标项目根目录诊断路由：

```bash
python3 .cannbot/plugins/hccl-op-generator/workflows/scripts/workflow_policy.py route \
  --requirement "新增 AICPU AllReduce Mesh 算法" \
  --json
```

显式 CCU、AIV 或 HostDPU 需求会阻塞并标明能力待完善；多引擎关键词冲突时会要求澄清。Review/Test 共用最多三轮修复预算；环境类测试失败不会错误派给 Developer。

### 查看开发报告

完整流程中的构建、安装、HCCL-VM 双轨验证和 estimate 性能估算由 Verifier 执行。HCCLBot 最终汇报会提供代码、任务报告和原始证据的实际路径；任务报告位于 `${HCCL_ROOT}/src/ops/{op_type}/docs/{task_id}/`。

| 文件 | 查看内容 |
|------|----------|
| `task-index.json` | 当前任务状态、源码身份和有效报告 |
| `LOG.md` | 实现变更和开发期静态检查结果 |
| `REVIEW.md` | 独立检视结论和发现的问题 |
| `BASELINE_REPORT.md` | 基线验证结果和证据路径 |
| `TEST_REPORT.md` | 候选构建、双轨测试结果、算法性能估算、失败或未验证项及原始证据路径 |

完成判定要求同一源码身份上的 Review PASS 和 Test PASS 同时有效；阻塞或失败任务以报告中的实际状态和证据为准。

## 三、可用技能

| Skill | 用途 | 触发时机 |
|-------|------|---------|
| `hccl-aicpu-design` | 需求、分层方案、Dataflow Spec 与选路设计 | AICPU 设计或设计检视 |
| `hccl-aicpu-best-practice` | template/executor/selector/TopoMatch 实现实践；内含 template 专项检视指南与脚本 | AICPU 实现、检视或独立只读审查 |
| `hccl-aicpu-debug` | AICPU 构建、选路、Checker 与同步故障的证据化定位 | AICPU 故障诊断时 |
| `hccl-aicpu-whitebox-design` | 从源码分支和数据流推导测试用例及预期 | AICPU 测试计划设计或检视时 |
| `hccl-aicpu-perf-optimize` | AICPU 性能基线与候选的可复现实验方法 | 明确要求性能优化时；收益需真实测量 |
| `hccl-env-check` | 环境检查 | Step 1b |
| `hccl-env-setup` | HCCL 环境搭建（探测/安装 CANN） | Step 1a |
| `hccl-test-tool-hvm` | HCCL-VM 虚拟机测试 | 算子开发完成后验证 |

以上 8 项由当前插件安装清单提供。Agent 中按需引用的 `hccl-doc-search` 未包含在该清单中，不能据此认定已安装。

### AICPU template 独立检视

在 cannbot 仓根重新运行安装入口，更新目标项目的 OpenCode 能力目录：

```bash
bash plugins-official/hccl-op-generator/init.sh project opencode /path/to/your_project
```

直接向 Agent 提交任务即可：

```text
使用 hccl-aicpu-best-practice，审查 /path/to/hccl 中
src/ops/all_reduce/algorithm/template/aicpu/ins_temp_example.cc。
这是相对 HEAD 的未提交改动，spec 为 /path/to/example-spec.md。
只评审不改代码，报告写到 /path/to/REVIEW.md。
```

没有 spec 时明确写“无 spec”。仅审查不需要先安装 CANN、编译或运行完整开发流程。
通过 HCCLBot 开发流程调用时，Reviewer 在独立检视和修复后复审阶段加载 `hccl-aicpu-best-practice` 的内部检视指南，
汇总报告到 `${HCCL_ROOT}/src/ops/{op_type}/docs/{task_id}/REVIEW.md`。

也可从 cannbot 仓根直接运行检查器；需先初始化 `vendor/cannbot-skills` 子模块，无需安装到 Agent 客户端：

```bash
SKILL_DIR="$(pwd)/vendor/cannbot-skills/communication/hccl-aicpu-best-practice/review"
# 已安装时，也可从目标项目根使用：
# SKILL_DIR="$(pwd)/.agents/skills/hccl-aicpu-best-practice/review"
export HCCL_REPO=/path/to/hccl

# 单模板检查；路径相对 HCCL 仓根
python3 "$SKILL_DIR/scripts/review_template.py" --repo "$HCCL_REPO" \
  src/ops/all_reduce/algorithm/template/aicpu/ins_temp_example.cc

# 未提交/已暂存/未跟踪改动；自动找受影响的 template
python3 "$SKILL_DIR/scripts/review_template.py" --repo "$HCCL_REPO" --base HEAD

# 单模板与 spec 对照（增量任务可再加 --base <固定 commit>）
python3 "$SKILL_DIR/scripts/review_template.py" --repo "$HCCL_REPO" \
  src/ops/all_reduce/algorithm/template/aicpu/ins_temp_example.cc --spec /path/to/example-spec.md

# 全仓扫描；只显示有 BLOCKER/MAJOR 的目标
python3 "$SKILL_DIR/scripts/review_template.py" --repo "$HCCL_REPO" --all --quiet
```

把示例路径替换成实际文件。最近一次已提交改动用 `--base HEAD^`；分支评审指定目标基线，
首次将 ref 解析为 commit 并在各轮复审中保持不变。`--strict` 让 MAJOR 也返回非 0；
`--show-baseline` 展开存量问题，`--rules` 查看规则目录。

脚本将结果打印到终端，完整 Markdown 报告由 Agent 按 skill 的报告模板整理。
只覆盖当前 `algorithm/template/aicpu/` 布局及 `InsAlgTemplateBase` 模板；CCU/AIV 不适用。
默认有 BLOCKER 时退出码为 1，`--strict` 下 MAJOR 也为 1；退出码 0 不代表人工清单已完成，
也不替代编译、hccl-vm 等功能验证。ring/HD 的实验判据会单独标注。

## 四、开发资源

| 资源类型 | 路径 | 说明 |
|---------|------|------|
| HCCL 源码仓 | `${HCCL_ROOT}/src/ops/` | 标准算子三层结构实现 |
| AllReduce 已有实现 | `${HCCL_ROOT}/src/ops/all_reduce/algorithm/template/aicpu/` | Mesh1D OneShot/TwoShot 参考 |
| AllGather 已有实现 | `${HCCL_ROOT}/src/ops/all_gather/algorithm/template/aicpu/` | Mesh 参考 |
| ReduceScatter 已有实现 | `${HCCL_ROOT}/src/ops/reduce_scatter/algorithm/template/aicpu/` | Ring 参考 |
| 通信算子开发指南 | `${HCOMM_DOCS}/comm_op_dev_guide/` | 官方开发指南 |
| API 参考（控制面） | `${HCOMM_DOCS}/api_ref/comm_opdev/control_plane_api/` | 拓扑查询、资源管理 |
| API 参考（数据面） | `${HCOMM_DOCS}/api_ref/comm_opdev/data_plane_api/` | 任务编排、算子下发 |

## 五、常见问题

### Q: 如何查看帮助信息？

```bash
bash /path/to/cannbot/plugins-official/hccl-op-generator/init.sh --help
```

### Q: HCCL_ROOT 是什么？

HCCL_ROOT 是已确认的 HCCL 源码路径（含 `src/ops/` 目录）。优先使用用户提供的路径或已有环境文件。需要准备缺失仓库且采用脚本约定布局时，脚本将其 clone 到显式指定的 `${WORKSPACE}/hccl`，并写入 `${WORKSPACE}/hccl-env.sh`。`WORKSPACE` 不必等于插件安装目标目录；复用已有仓库时保留其实际路径，不为生成环境文件而重复下载。

### Q: init.sh 提示 Node.js 缺失或版本不满足？

统一安装入口在读取插件清单和执行安装器前检查 Node.js。未安装、无法运行、版本无法识别或低于 20 时，会显示原因和安装指引，并以非零退出码停止。先安装 Node.js ≥20，或修正当前终端的 `PATH`，确认 `node --version` 正常后再运行 `init.sh`。脚本不会自动补装 Node.js。

### Q: 如何更新？

```bash
cd /path/to/cannbot
bash plugins-official/hccl-op-generator/init.sh project opencode /path/to/your_project
```

### Q: x86_64 开发机编译报 `cannot find -lccl_kernel`？

这是 x86_64 开发机最常见问题。设备 kernel 库 `libccl_kernel.so` 仅 aarch64 架构，需由 Verifier 按 `hccl-aicpu-best-practice` 的构建约束处理。

### Q: selector algName 与 REGISTER_EXEC_V2 name 不一致？

这是最常见编译/运行错误。selector 返回的 `selectAlgName` 字符串必须与 `REGISTER_EXEC_V2` 的 name 参数**完全一致**（区分大小写）。

---

## 总结

1. HCCLBot 当前支持 AICPU 标准算子开发；CCU/AIV/HostDPU 待完善
2. 使用 `init.sh` 一键安装；运行任务时再由环境 Skill 检测 HCCL/HCOMM/CANN
3. 接收需求后先判定引擎：AICPU 走设计、基线、开发、独立检视、双轨测试状态机；其他引擎阻断
4. AICPU 由 Verifier 在 HVM 目录通过 `build_pkg.sh --install hccl` 统一构建、安装并部署设备库，再执行 `AI_CPU` 双轨 Checker；默认不追加 HCCL ST/UT

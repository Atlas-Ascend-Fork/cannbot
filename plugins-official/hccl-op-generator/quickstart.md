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

- 已安装 CANN Toolkit（建议 ≥ 9.0.0）
- 已安装 OpenCode

> HCCL 源码仓和 HCOMM 文档仓无需提前准备。首次提交算子开发需求时，HCCLBot 会自动 clone 到当前工作目录（cannbot-hccl 所在目录）。

### OpenCode 安装

```bash
git clone https://gitcode.com/gcw_ceFcSOhT/cannbot-hccl.git
cd cannbot-hccl
bash plugins-official/hccl-op-generator/init.sh project opencode   # 项目级（默认）
# bash plugins-official/hccl-op-generator/init.sh global opencode  # 全局级
opencode
```

init.sh 仅负责安装 Skills/Agents/配置文件到 `.opencode/` 目录，不探测 HCCL/CANN 环境。

若已在 HCCL 源码仓工作，也可在仓根执行 `npx --yes @cannbot-ai/install-helper install hccl-op-generator --tool opencode --level project --yes`。当前 `init.sh` 遇到已有的仓根 `AGENTS.md` 会保留原文件，并把 HCCLBot 工作流说明写到 `.opencode/hccl-op-generator/AGENTS.md`；源码仓需从自己的 `AGENTS.md` 显式指向该入口。该 npx 路径依赖 CANNBot 上游发布新版本，发布前仅以本地仓隔离安装测试为准。

Claude Code 的源码仓 `.claude-plugin/marketplace.json` 是另一条安装途径：先 `claude plugin marketplace add .`，再 `claude plugin install hccl-op-generator@hccl-source --scope project`；它不使用 OpenCode 的 `init.sh`，也不会因为克隆源码仓而自动安装。

HCCL 和 HCOMM 仓库的环境准备在首次提交算子开发需求时自动完成：
- HCCLBot 运行 `communication/hccl-env-setup/scripts/setup-env.sh`，clone hccl/hcomm 到工作目录
- 探测 CANN_HOME，生成 `hccl-env.sh`（含 HCCL_ROOT/HCOMM_CODE_HOME/HCOMM_DOCS/CANN_HOME）
- 已存在的仓库会询问用户是否 `git pull` 更新

### 在其他目录执行

```bash
# 安装到指定项目
bash /path/to/cannbot-skills/plugins-official/hccl-op-generator/init.sh project opencode /path/to/your_project
```

### 验证安装

```bash
opencode agent list
# 应看到 hccl-architect / hccl-developer / hccl-reviewer / hccl-verifier

ls .opencode/skills/
# 应看到 9 个技术 skill

cat .opencode/hcclbot-manifest.json
# 检查 installed_skills / installed_agents 是否完整

# 环境变量在首次开发需求时自动生成：
cat ../hccl-env.sh
# 检查 HCCL_ROOT / HCOMM_CODE_HOME / HCOMM_DOCS / CANN_HOME 是否正确
```

## 二、快速上手

### 启动

```bash
opencode
```

### 开发算子示例

新增 AllReduce Mesh1D OneShot 算法模板：

```
帮我为 AllReduce 新增一个基于 Mesh1D OneShot 的 AICPU 算法模板，
支持 fp16/fp32 数据类型，小数据量场景（≤8MB），rank 数量动态获取。
```

为 ReduceScatter 新增 Ring 算法：

```
帮我为 ReduceScatter 新增一个基于 Ring 的 AICPU 算法模板，
支持 int32 数据类型，跨 server 场景。
```

HCCLBot 会先判定引擎，AICPU 任务按工作流分派给四个 Agent。把**算子类型**（AllReduce/ReduceScatter 等）、**算法名称**、**引擎**、**拓扑场景**、**数据类型**写清楚即可。

### 核心工作流

```text
AICPU: 环境 → 设计 → 基线 → 开发 → 独立检视 → 候选构建与双轨测试 → 完成
CCU/AIV/HostDPU: 暂不支持，路由阶段阻断
```

AICPU 只有同一源码身份上的 Review PASS 与双轨 Test PASS 同时有效才能完成，详见 AGENTS.md。

### 产出物示例

算法模板开发完成后，产出在 `${HCCL_ROOT}/src/ops/{op_type}/`：

```
${HCCL_ROOT}/src/ops/all_reduce/
├── all_reduce_op.h / .cc              # 算子入口（已有）
├── selector/
│   ├── all_reduce_auto_selector.h     # 选择器（已有）
│   └── all_reduce_auto_selector.cc    # 修改 SelectAicpuAlgo() 添加分支
├── executor/
│   ├── ins_v2_all_reduce_sole_executor.h / .cc  # 已有 Sole 执行器（复用）
│   └── ins_v2_all_reduce_{new_algo}_executor.cc # 新建（若需自定义编排）
├── template/aicpu/
│   ├── ins_temp_all_reduce_mesh_1D_one_shot.h / .cc  # 已有（参考）
│   └── ins_temp_all_reduce_{new_algo}.h / .cc        # 新增模板
├── template/aiv/                      # AIV 引擎（非本范围）
├── template/ccu/                      # CCU 引擎（非本范围）
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

引擎路由、正常阶段角色和失败修复链由 `workflows/scripts/workflow_policy.py` 自动复核。例如诊断路由：

```bash
python3 plugins-official/hccl-op-generator/workflows/scripts/workflow_policy.py route \
  --requirement "新增 AICPU AllReduce Mesh 算法" \
  --json
```

显式 CCU、AIV 或 HostDPU 需求会阻塞并标明能力待完善；多引擎关键词冲突时会要求澄清。Review/Test 共用最多三轮修复预算；环境类测试失败不会错误派给 Developer。

需要人工诊断门禁失败时可运行：

```bash
python3 plugins-official/hccl-op-generator/workflows/scripts/validate_aicpu_artifacts.py \
  --task-dir "${HCCL_ROOT}/src/ops/<op_type>/docs/<task_id>" \
  --target-state <ENV_READY|DESIGN_READY|BASELINE_READY|IMPLEMENTED|REVIEW_PASS|TEST_PASS|COMPLETE> \
  --json
```

### 开发完成后如何使用

编译安装后，通过 hccl-vm 验证：

```bash
source ${CANN_HOME}/set_env.sh
cd ${HCCL_ROOT}
bash build.sh --pkg --full   # 编译 host + device 全量包

# HCCL-VM 测试（加载 /hccl-test-tool-hvm skill）
# 选择 AICPU 的 AI_CPU 模式 → 选择算子 → 选择数据类型 → 执行
```

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
| `hccl-doc-search` | 文档搜索 | 查询 API 文档 |

### AICPU template 独立检视

在 cannbot-hccl 仓根重新运行安装入口，更新 OpenCode 能力目录：

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
通过 HCCLBot 开发流程调用时，Reviewer 在 Step 5 和修复后的 Step 6 加载 `hccl-aicpu-best-practice` 的内部检视指南，
汇总报告到 `${HCCL_ROOT}/src/ops/{op_type}/docs/REVIEW.md`。

也可从仓根直接运行检查器，无需安装到 Agent 客户端：

```bash
SKILL_DIR="$(pwd)/communication/hccl-aicpu-best-practice/review"
export HCCL_REPO=/path/to/hccl
# 已 source hccl-env.sh 时也可使用：export HCCL_REPO="$HCCL_ROOT"

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
| AllReduce 已有实现 | `${HCCL_ROOT}/src/ops/all_reduce/template/aicpu/` | Mesh1D OneShot/TwoShot 参考 |
| AllGather 已有实现 | `${HCCL_ROOT}/src/ops/all_gather/template/aicpu/` | Mesh 参考 |
| ReduceScatter 已有实现 | `${HCCL_ROOT}/src/ops/reduce_scatter/template/aicpu/` | Ring 参考 |
| 通信算子开发指南 | `${HCOMM_DOCS}/comm_op_dev_guide/` | 官方开发指南 |
| API 参考（控制面） | `${HCOMM_DOCS}/api_ref/comm_opdev/control_plane_api/` | 拓扑查询、资源管理 |
| API 参考（数据面） | `${HCOMM_DOCS}/api_ref/comm_opdev/data_plan_api/` | 任务编排、算子下发 |

## 五、常见问题

### Q: 如何查看帮助信息？

```bash
bash init.sh --help
```

### Q: HCCL_ROOT 是什么？

HCCL_ROOT 是 HCCL 源码路径（含 `src/ops/` 目录）。首次提交算子开发需求时，`setup-env.sh` 会自动 clone HCCL 仓库到当前工作目录下的 `hccl/` 子目录（cannbot-hccl 的兄弟目录）并设置该变量。无需手动指定。

### Q: 如何更新？

```bash
cd cannbot-skills/plugins-official/hccl-op-generator && bash init.sh
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
4. AICPU 由 Verifier 独占全量构建与 `AI_CPU` 双轨 Checker，默认不追加 HCCL ST/UT

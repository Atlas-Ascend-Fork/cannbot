# pypto-op-orchestrator

PyPTO 算子开发编排插件：以 harness 工作流（workflow-orchestrator）驱动 PyPTO 算子
**7 阶段状态机**（需求规划 → Golden 生成 → 设计 → 验证准备 → 按模块编码闭环 →
最终 E2E 验证 → 性能调优）。安装与使用见 [QUICKSTART.md](QUICKSTART.md)。

## 新特性

### 【2026-10-15】

- Stage 7 达标判定放宽：重试预算用完之前，**达标（`optimized_us <= perf_target_us`）
  或达到硬件极限**（`hw_limit_reached: true` 且 tuning_report 含硬件极限论证节）均判
  pass，其他异常一律 fail；`stage7-tune` 的 `max_retries` 2→5；`tune_result.json`
  新增 `hw_limit_reached` 字段（默认 false）。
- 新增 [QUICKSTART.md](QUICKSTART.md)：安装与三种典型使用场景的操作指南，README
  回归插件本身的契约与设计说明。

## 功能概览

本插件提供 PyPTO 算子从需求到性能调优的完整编排流程，两个工作流覆盖两类入口：

| 工作流 | 用途 |
|---|---|
| `workflows/pypto-op-develop.yaml` | 完整 生成 + 调优 流程（9 节点） |
| `workflows/pypto-op-tune.yaml` | 仅调优 流程（tune-preflight → stage7-tune，2 节点） |

**调度交给 harness，知识交给 cannbot-skills 的 Skill，节点即 agent。** 所有节点
`executor: general-executor` / `verifier: general-verifier`（纯协议薄壳，零 PyPTO
业务逻辑）；PyPTO 角色 agent 的行为定义 100% 落在 yaml 节点字段
（goal/approach/acceptance/out_of_scope），阶段专门知识经 approach 首行指令挂载
Skill（安装时从 cannbot-skills 仓拉取），裁判方法论写进 `procedure`（只进 verify
提示词）。节点派发、执行与验收、重试及状态管理全部由 harness 框架承担；
`max_parallel: 1`（单设备纪律），`depends_on` 串 DAG；阶段门禁保留——hooks
（state_transition + pypto-op-lint）随依赖仓装配进工作区，各阶段节点照旧经
`state_transition` 写 `.orchestrator_state.json`，成功判定为 Stage 1-7 全 completed。

交互式入口由入口 skill `pypto-op-orchestrator`（`skills/`）承担：语义命中
"生成/开发/实现 PyPTO 算子"类自然语言（`pypto` 关键词 + 算子开发意图）后，分流到
`workflow-orchestrator` 收集四项输入并向用户确认，确认后拉起 harness 工作流；
无头场景由调用方直接给 `orchestrator.py` 指定 `--yaml` 与 `--prompt`，不经过
入口 skill。

安装与首次使用见 [QUICKSTART.md](QUICKSTART.md)。

## 整体流程

```text
 交互式客户端                  ┌──────────────────────────────────────────────┐
 "请生成一个 pypto 实现的       │ 入口 skill：pypto-op-orchestrator             │
  relu 算子"          ───────►│ 语义分流（pypto 关键词 + 算子开发意图命中）     │
                              └──────────────────┬───────────────────────────┘
 无头调用方                    ┌─────────────────▼───────────────────────────┐
 orchestrator.py      ───────►│ skill：workflow-orchestrator                │
 --yaml ... --prompt ...      │ 收集四项输入 → 用户确认 → link_agent_config │
                              └─────────────────┬───────────────────────────┘
                                                ▼ 拉起 harness orchestrator.py
 ┌──────────────────────────────────────────────────────────────────────────┐
 │            pypto-op-develop.yaml  串行 DAG（max_parallel: 1）             │
 │                                                                          │
 │  preflight-env ──► prepare-case                                          │
 │   （环境/装配）      └──► prepared_case.json（后续节点唯一权威输入）        │
 │                        │                                                │
 │                        ▼                                                │
 │  stage1-plan     需求规划与 API 可行性 → SPEC.md / API_REPORT.md         │
 │  stage2-golden   Golden 生成           → <op>_golden.py                  │
 │  stage3-design   设计与模块接口         → DESIGN.md / module_interfaces.yaml│
 │  stage4-verify-prep 独立检查/验证准备   → eval/ 三件套（L0 单模块短路跳过） │
 │  stage5-impl     按模块编码闭环         → <op>_impl.py                    │
 │                  （模块循环与 debugger 补丁循环在节点内部完成）             │
 │  stage6-e2e      最终 E2E 验证         → test_<op>.py 全绿               │
 │  stage7-tune     性能调优              → <op>_tuning_report.md /         │
 │                  （max_retries=5；达标     <op>_tune_result.json          │
 │                   或硬件极限论证判 pass）                                 │
 │                                                                          │
 │  每个节点：general-executor 执行 → general-verifier 按 acceptance 机检    │
 │  裁判；fail 由 harness 按节点 max_retries 自动重试，耗尽则工作流失败       │
 └──────────────────────────────────────────────────────────────────────────┘

 仅调优短路径：pypto-op-tune.yaml = tune-preflight → stage7-tune（2 节点，
 stage7-tune 节点定义与 develop yaml 一致）。
```


## 7 阶段 → harness 映射

| Stage | 角色 agent → 产物（行为来源） | harness 节点 | approach 挂载 skill | acceptance（机检锚点） | 拆分/合并/跳过记录 |
|---|---|---|---|---|---|
| - | （用例准备） | `preflight-env` / `prepare-case` | -（装配/准备脚本） | 装配 JSON status=ok；`prepare_case.py --verify` exit 0 | 保留 2 节点；direct 交互场景由入口引导先写 REQUIRE.md，节点幂等 |
| 1 需求规划与 API 可行性 | pypto-op-planner → SPEC.md、API_REPORT.md | `stage1-plan` | pypto-op-plan + pypto-intent-understand + pypto-api-explore | 两文件非空 + API map 无未解释 unsupported + state stage1 completed | 1:1 |
| 2 Golden 生成 | pypto-op-mathematician → golden.py、GOLDEN_PERF_REPORT | `stage2-golden` | pypto-golden-generate | golden 非空 + inventory 注释 + allclose 证据 + state stage2 completed | 1:1 |
| 3 设计与模块接口 | pypto-op-architect → DESIGN.md、module_interfaces.yaml | `stage3-design` | pypto-op-design | 两文件非空 + validate_yaml.py 无 violation + state stage3 completed | 1:1 |
| 4 独立检查与验证准备 | pypto-op-verifier (scaffolding) → eval/ 三件套 | `stage4-verify-prep` | pypto-op-verify（procedure 给 verifier） | state stage4 completed；L1: 三件套存在 + `--self-test` exit 0 | **合并**：L0（module_count==1）在角色 agent 体系即跳过 scaffolding，节点内 short-circuit（acceptance 对 L0 自动满足），不单设分支 |
| 5 按模块编码闭环 | pypto-op-coder/verifier/debugger 三角循环 → impl+README | `stage5-impl` | pypto-op-develop + pypto-memory-template（失败时 pypto-general-debug/pypto-precision-debug） | impl+README 非空 + state stage5 completed +（需求文件预置场景）桥接文件存在 | **合并**：per-module phase 循环与 debugger 补丁循环保留在节点内部（harness 节点=单 agent 进程，三角交互拆节点会割裂上下文；debugger 调查方法论下沉到 debug skill 挂载）；cycles≤10 内层上限不变，harness max_retries 做外层兜底 |
| 6 最终 E2E 验证 | pypto-op-verifier (final E2E) | `stage6-e2e` | pypto-op-verify（procedure） | test 运行 exit 0（hash 未变走 structure-only 短路）+ state stage6 completed | 1:1；artifact hash 未变的 structure-only 短路逻辑保留 |
| 7 性能调优 | pypto-op-optimizer，S1→S5 子状态机 | `stage7-tune` | pypto-op-perf-tune（内部再加载 tune-orchestrator） | tuning_report 存在 + 回归 PASS + complete_stage(7) + check_artifacts ARTIFACTS_OK + perf_target_us 非空时 `<op>_tune_result.json` 达标断言（达标或硬件极限论证均 pass，否则自动重试） | **合并**：S1_SETUP…S5_REPORT 与 ≤N 轮 swimlane/incore 循环由节点内 tune-orchestrator skill 状态机驱动；**跳过**：PANKO auto-tuner 路径 v1 不进 yaml（实验性 relay，默认未启用） |

仅调优 yaml（`pypto-op-tune.yaml`）：`tune-preflight`（环境/装配校验 +
impl/test/精度证据校验 + 缺最小 MEMORY.md 时按模板生成占位；**合并记录**：develop 的
`preflight-env` 环境/装配职责并入本节点）→ `stage7-tune`（节点定义与 develop yaml
中同节点保持一致，保证两条路径调优行为一致）。

## 输入契约（两种模式）

本插件自包含、不依赖任何外部仓文件；输入契约只有两种模式。**对提示词格式不作任何
要求**：任意自然语言均可触发，下文与 `workflows/templates/require_template.md` 的
字段清单/模板仅为建议参考（非必需）；算子名缺失时由 `prepare-case` 节点 agent 按
算子语义自行拟定合法 Python 标识符并经 `--op-name` 传入，设备号缺失时
`prepared_case.json` 记 `device_id: null`（后续节点按 `TILE_FWK_DEVICE_ID` 环境
变量或默认设备执行），性能目标缺失即无硬性目标。

### interactive 模式（自然语言 / REQUIRE.md 直达）

任意自然语言提示词或既有 `REQUIRE.md` 路径即可触发完整生成流程（交互会话中由入口
skill `pypto-op-orchestrator` 命中自然语言，分流到 `workflow-orchestrator` 启动
`workflows/pypto-op-develop.yaml`）。`prepare-case`
节点按 `$USER_PROMPT` 内容收敛到两条通路：

- 已有 `custom/<op>/REQUIRE.md`：`prepare_case.py --from-require` 合成最小
  `prepared_case.json`（`mode: "interactive"`，`task_desc: null`，无 ModelNew
  桥接契约；算子名 `--op-name` 优先、缺省取 REQUIRE.md 父目录名，不解析
  REQUIRE.md 内容）；
- 无任何用例文件、只有算子需求描述：`prepare_case.py --from-desc` 接受任意
  自然语言文本（不校验章节结构、不解析 front matter、不要求文本含任何
  特定字段），把需求文本落盘为 `custom/<op>/REQUIRE.md`（缺必备节结构时按
  `workflows/templates/require_template.md` 包一层，原文完整保留），随后走与
  `--from-require` 相同的 interactive 通路。算子名必须经 `--op-name` 显式
  传入（由 prepare-case 节点 agent 从 `$USER_PROMPT` 解析，提示词未给出时
  按算子语义拟定；脚本不解析需求文本提取任何字段）。

### 需求文件预置（prepared_case.json 记为 `staged`）

外部调用方在触发前把三个产物预写到 `$OP_DIR`（即
`custom/<op>/`）：

- `REQUIRE.md`：算子需求文档（内容格式由调用方自定，插件不解析）；
- `task_desc.py`：官方用例（输入生成 + 参考 Model）；
- `gen_prompt.md`：用例事实与桥接契约（内容由调用方负责，插件不渲染）。

并在 `$USER_PROMPT` 中携带用例事实（op_name/op_dir/device_id/性能目标/
调优轮次/容差等）。`prepare-case` 节点对该模式只做核对（verify）：节点
agent 从 `$USER_PROMPT` 解析出算子名等事实后运行
`prepare_case.py --verify --work-dir $WORK_DIR --op-dir <op_dir> --op-name <op>`，
脚本确认三个产物存在且非空后，由命令行参数合成 `prepared_case.json`
（`mode: "staged"`；算子名以 `--op-name` 为准，缺省仅以 `$OP_DIR` 目录名
兜底——脚本不打开/解析任何用例文件提取字段，从提示词解析事实是节点
agent 的职责）。用例事实缺失时有明确兜底：算子名取目录名、`device_id`
记 `null`、性能目标缺失即无硬性达标断言，均不报错卡住。该场景的桥接产物
`<op>_pypto_impl.py`（ModelNew）由 Stage 5 按 gen_prompt.md 契约产出。

### prepared_case.json 契约

两种模式殊途同归，均合成 `$WORK_DIR/prepared_case.json` 作为后续节点的唯一权威
输入记录：

| 字段 | 含义 | 缺省 |
|---|---|---|
| `op` | 算子名（合法 Python 标识符） | `--op-name` 优先，目录名兜底 |
| `op_dir` | 算子产物目录（`custom/<op>/`） | - |
| `require` / `task_desc` / `gen_prompt` | 三产物路径 | interactive 模式后两者为 `null` |
| `device_id` | NPU 设备号 | `null`（按 `TILE_FWK_DEVICE_ID` 或默认设备执行） |
| `perf_target_us` | 硬性性能目标（us） | `null`（无硬性目标，Stage 7 达标断言自动满足） |
| `tune_rounds` | Stage 7 调优轮次 | 3 |
| `mode` | 提示词触发记 `interactive` / 需求文件预置记 `staged` | 按输入通路判定 |

## Stage 7 性能达标与自动重试

`stage7-tune` 的 acceptance 含一条**确定性性能达标断言**：节点收尾时把最终
实测最优值落盘 `$OP_DIR/<op>_tune_result.json`（字段 `optimized_us` /
`perf_target_us` / `target_met` / `hw_limit_reached`），verifier 机检该文件。

- 断言触发条件：`prepared_case.json` 的 `perf_target_us` 非空（需求文件预置
  场景注入硬性目标）才断言；为 `null`（提示词触发无硬性目标）时该项自动
  满足，不会误伤交互场景。
- pass 条件（重试次数用完之前，**达标 OR 达到硬件极限**都认为 pass）：
  `tune_result.json` 存在且 `optimized_us` 为有效正数，且
  `optimized_us <= perf_target_us` **或** `hw_limit_reached == true` 且
  tuning_report 含硬件极限论证节；文件缺失/字段非法/回归失败等其他异常一律
  fail。
- 硬件极限出口（诚信义务）：当连续多轮优化无提升且 agent 依据 profiling 数据
  判断当前实现已触及硬件极限（如内存带宽/计算单元利用率饱和）时，置
  `hw_limit_reached: true`，并在 `<op>_tuning_report.md` 中写明硬件极限论证
  （哪些硬件指标饱和、为什么继续优化无空间）；**禁止无论证置 true**——verifier
  会核对论证存在，无论证或论证空泛判 fail。
- 未通过 → verifier 判 `fail` → 编排器按 `max_retries: 5` 自动重跑本节点
  （重跑 prompt 自动携带 `Previous-Verification-Failure`，含实测值与目标值
  差距，供下一轮调优参考）；重试耗尽后按 `on_exhaust: exit` 终止，工作流
  整体失败。
- 调用方解读：调用方看到工作流失败且失败节点为 `stage7-tune` 时，应判
  该算子性能未达标且未论证硬件极限（而非编排器故障）；通过即 Stage 1-7 全
  `completed` 且 `<op>_tuning_report.md` / `<op>_tune_result.json` 在场。

## 安装详解

普通用户推荐在目标工作区使用 `npx` 统一安装器；开发者推荐克隆源码后运行插件的
`init.sh`。两种方式的最短操作步骤见 [QUICKSTART.md](QUICKSTART.md)。

### 环境要求

需要 Node.js 20.11+、Python 3、PyYAML 和已安装并配置好的 Agent CLI（目前验证的
客户端为 OpenCode、Codex、Claude Code）。运行算子开发与调优还需要可导入的
`pypto`（CANN 环境）与可见的 NPU 设备（`npu-smi`）；指定设备号时以
`TILE_FWK_DEVICE_ID` 为唯一权威。

### 安装入口

```bash
# npm（npx 统一安装器）
npx @cannbot-plugin/cannbot@latest install pypto-op-orchestrator --tool opencode

# 源码（init.sh 为薄壳，转发统一安装器，等同 --source 安装）
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-official/pypto-op-orchestrator
bash init.sh
```

安装需要网络（克隆 cannbot-skills 依赖仓），与现有 dependencies 机制一致。

### 依赖仓资产装配（plugin-install.json）

本插件在 cannbot 仓**不包含任何 pypto skill / pypto 角色 agent / hook 实体**。
`plugin-install.json` 声明依赖 [cannbot-skills](https://gitcode.com/cann/cannbot-skills)
仓（`ref: master`）及 `assets.plugin: plugins-official/pypto-op-orchestrator`；
安装器克隆依赖仓到 `<项目>/.cannbot/dependencies/pypto-op-orchestrator/cannbot-skills/`，
读取其 `plugin-assets.json` 清单（不存在则跳过；`plugin-install.json` 内联
`assets.skills/hooks/agentsMd` 键可覆盖），随后**即时创建相对软链/装配**：

- skills → 相对软链到 `<项目>/.agents/skills/<name>`（opencode/codex 布局）；
- hooks → 装配到 `<项目>/.cannbot/plugins/pypto-op-orchestrator/hooks`
  （Claude 走 hooks.json 注册，`${CLAUDE_PLUGIN_ROOT}` 重写为装配路径）；
- AGENTS.md（交互入口引导）→ 按 marker 块合并进项目根 `AGENTS.md`/`CLAUDE.md`。

`plugin-sources.json` 另声明仓内 `harness/workflow-orchestrator` Skill 的软链
（`skillsRepository: "."`，`skillInstallMode: "symlink"`），调度能力来自本仓
harness，不重复分发。

## 架构与目录说明

```text
pypto-op-orchestrator/
├── README.md                        # 新特性、契约与设计（本文件）
├── QUICKSTART.md                    # 安装与使用操作指南
├── agents/                          # 节点即 agent 的两个通用协议薄壳
│   ├── general-executor.md          # 执行协议：按 task 交付并自验，返回 executed
│   └── general-verifier.md          # 裁判协议：只按 acceptance 裁决，返回 pass/fail
├── init.sh                          # 统一安装器（script/bin/source-plugin-init.sh）的薄入口
├── plugin-install.json              # cannbot-skills 依赖仓与资产清单（assets）声明
├── plugin-sources.json              # 仓内 harness/workflow-orchestrator Skill 软链声明
├── skills/pypto-op-orchestrator/    # 入口 Skill：自然语言分流到 workflow-orchestrator 启动工作流
├── example/                         # 输入样例（relu/ 为 ReLU 算子的输入文件样例与用法说明）
├── .claude-plugin/plugin.json       # Claude 客户端插件清单
├── .codex-plugin/plugin.json        # Codex 客户端插件清单
├── .gitignore                       # 排除 .cannbot/ 运行产物
└── workflows/
    ├── pypto-op-develop.yaml        # 生成 + 调优完整流程（9 节点）
    ├── pypto-op-tune.yaml           # 仅调优流程（tune-preflight → stage7-tune）
    ├── scripts/
    │   ├── assemble_workspace.py    # 装配薄封装：调安装器完成依赖拉取+资产软链，补 opencode hooks 接线；--cannbot-root 省略时 verify-only
    │   ├── prepare_case.py          # 用例准备：--verify（预置核对并合成 prepared_case.json）/ --from-require / --from-desc（任意自然语言落盘 REQUIRE.md，--op-name 必传）
    │   ├── check_artifacts.py       # 产物契约自检：必备产物 + Stage 1-7 completed + 扁平布局，输出 ARTIFACTS_OK <op>
    │   └── tests/                   # 脚本黑盒测试（prepare_case 三通路）
    └── templates/
        └── require_template.md      # 算子需求文档模板（interactive 手写依据 + --from-desc 缺结构文本的封装模板）
```

## 运行产物

工作区 `.cannbot/` 下的运行产物（`.workflow/` 状态、session 归档等）与 `custom/<op>/`
算子产物不随插件入库（见 `.gitignore`）。进度查看、失败恢复与产物说明见
[QUICKSTART.md](QUICKSTART.md)。

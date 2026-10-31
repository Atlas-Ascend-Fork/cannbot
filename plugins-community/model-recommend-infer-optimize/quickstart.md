# 推荐模型整网推理优化快速入门

## 概述

`model-recommend-infer-optimize` 是推荐模型（搜索/推荐/排序/视觉编码类网络）昇腾 NPU 推理整网优化 plugin。以 **GE 图模式为核心优化基座**（onnx 直接进入；pytorch/HF 经 torchair 转入），先把模型跑通到可复现精度的单卡基线，再在基线上按「性能分析 → 分层优化 → 双门禁验收 → 动作表更新」持续循环收敛。

- **主工作流**：`workflows/model-recommend-infer-workflow.md`，编排条目 0-14 与持续优化循环，调度 4 个 subagent（runner / analyzer / implementer / reviewer）。
- **原子 skills**：18 个 `model-recommend-*` skill 维护在 cannbot-skills 仓 `community/model/`，安装时装配到 `skills/`；按条目承接具体技术与判定标准。

> **安装器说明**：本插件的 `init.sh` 为自带实现（需在安装时把内置执行框架复制到工程根），与仓内共享安装器 `script/bin/source-plugin-init.sh` 的行为差异仅此一项；支持的客户端与安装级别以 `bash init.sh --help` 为准（`--help` 不依赖子模块，未初始化时也可查看）。**18 个 Skill 不在本插件仓库内**：它们由 `plugin-sources.json` 从 `vendor/cannbot-skills` 子模块的 `community/model/` 装配——`init.sh` 安装时链接到配置根的 `skills/`，npm 分发包由 `script/lib/plugin-bundle.js` 打包进 `skills/`；Marketplace 一键安装则通过依赖包 `model-recommend-skills` 提供（见下文 Claude Code 段）。因此安装前需先 `git submodule update --init --depth 1 vendor/cannbot-skills`（或设置 `CANNBOT_SKILL_SRC_ROOT` 指向该仓）。

## 一、环境搭建

### 前置条件

- 已安装 CANN Toolkit（9.1.0；版本配套关系随 CANN 发行说明提供）；GE v2 组件 `libge_runner_v2.so` 存在
- 已配置 NPU 设备（Ascend 910B 系列单卡场景为主，A5 平台走 cannbot-dsl 路径）
- 工具链 `atc` / `msopgen` / `msprof` 可用；`g++`（C++17）与 `nlohmann/json.hpp` 已安装
- Python 侧 `onnx` / `numpy` 可用；golden 需 CPU `onnxruntime` 或用户提供 `reference/` 标杆
- **GE_SESSION_DEMO 执行框架已就位并编译通过**（onnx 输入路径的标准执行入口，随插件内置；pytorch / HuggingFace 路径不需要它，见下节）
- 已安装 OpenCode、Claude Code、TRAE、Cursor、Codex、Copilot、CodeArts 等受支持的 AI 编程工具

> 全量外部依赖清单（25 项，含核对命令与缺失处置）见 `workflows/references/external-dependencies.md`。本工作流不引用任何外部链接。

### 就位执行框架 GE_SESSION_DEMO（onnx 输入路径必做）

框架随插件内置在 `framework/GE_SESSION_DEMO/`，无需下载。两种安装方式的落位不同：

- 用本插件 `init.sh` 安装：会自动复制到工程根，无需操作。
- 用仓库统一安装器（`cannbot install` / npm 分发）安装：框架随包落在 `.cannbot/plugins/model-recommend-infer-optimize/framework/`，**需手工放一份到工程根**（框架必须与工程同级，安装器不代放）：

```bash
cp -r .cannbot/plugins/model-recommend-infer-optimize/framework/GE_SESSION_DEMO <工程根>/GE_SESSION_DEMO
cd <工程根>/GE_SESSION_DEMO && bash compile.sh   # 产出 ./GEsession_test_acl
```

框架目录布局、使用方式与维护约定见 `framework/README.md`（含 Apache License 2.0 许可与 `NOTICE`）；安装后路径写入 `cannbot-manifest.json` 的 `framework_dir`，交付时随环境基线一并归档。pytorch / HuggingFace 输入路径不依赖该框架。

### OpenCode（推荐）

```bash
# 在已获取的插件目录执行（插件由 marketplace 或离线包提供）
cd plugins-community/model-recommend-infer-optimize
bash init.sh project opencode   # 项目级（默认）
bash init.sh global opencode    # 全局级
```

验证：

```bash
opencode agent list
# 应看到 4 个 agent：model-recommend-infer-runner / -analyzer / -implementer / -reviewer
```

### 其他工具

<details>
<summary>Claude Code</summary>

**首选：Plugin Marketplace（一键安装）**

```text
/plugin marketplace add <本仓库地址，由分发渠道提供>
/plugin install model-recommend-infer-optimize@cannbot
/reload-plugins
```

安装后新开会话，或在当前会话执行 `/clear` 触发插件上下文加载。`model-recommend-infer-optimize` 是主对话入口，会把 AGENTS.md 注入上下文，并按强制规则读取 `workflows/model-recommend-infer-workflow.md`。

> **Skill 由依赖包一并安装**：插件声明 `dependencies: ["model-recommend-skills"]`，该 skills 包在 marketplace 中登记为 `git-subdir`（`cannbot-skills` 仓 `community/model`，pin 与 `vendor/cannbot-skills` 同一 sha）。支持依赖解析的渠道一键装完即有 18 个 Skill；若所在渠道不支持依赖，退回下面的 `init.sh` 路径。

验证：

```bash
claude plugin list
# 应看到 model-recommend-infer-optimize@cannbot ✔ enabled
```

**备选：init.sh 脚本**

```bash
cd plugins-community/model-recommend-infer-optimize
bash init.sh project claude     # 项目级
bash init.sh global claude      # 全局级
```

</details>

<details>
<summary>TRAE</summary>

项目级与全局级都支持；global 时按已装变体落在 `~/.trae-cn`（IDE）/ `~/.marscode`（Plugin）/ `~/.traecli`（CLI）。

```bash
cd plugins-community/model-recommend-infer-optimize
bash init.sh project trae     # 项目级：生成 .trae/ / .marscode/ / .traecli/
bash init.sh global trae      # 全局级：写入 ~/.trae-cn / ~/.marscode / ~/.traecli
```

安装后自动检测 TRAE 环境并选择对应目录；若三者都不存在，project 级回退到 `.trae/`。

</details>

<details>
<summary>Cursor</summary>

```bash
cd plugins-community/model-recommend-infer-optimize
bash init.sh project cursor     # 项目级
bash init.sh global cursor      # 全局级
```

</details>

<details>
<summary>Codex</summary>

Codex 的 Skill 与 Subagent 使用不同发现目录：项目级 Skill 在 `.agents/skills/`，项目级 Subagent 在 `.codex/agents/*.toml`。

```bash
bash init.sh project codex
bash init.sh global codex
```

</details>

<details>
<summary>Copilot</summary>

```bash
bash init.sh project copilot    # 项目级，生成 .github/
bash init.sh global copilot     # 全局级，生成 ~/.copilot/
```

</details>

<details>
<summary>CodeArts</summary>

```bash
bash init.sh project codearts   # 项目级，生成 .codeartsdoer/
bash init.sh global codearts    # 全局级，生成 ~/.codeartsdoer/
```

</details>

<details>
<summary>dsh</summary>

```bash
bash init.sh project dsh        # 项目级，生成 .dsh/
bash init.sh global dsh         # 全局级，生成 ~/.dsh/
```

</details>

### 验证安装

```bash
# OpenCode
opencode agent list          # 应有 4 个 model-recommend-infer-* agent

# Claude Code
claude plugin list           # 应看到 model-recommend-infer-optimize@cannbot ✔ enabled

# 目录形态（以 TRAE / Cursor 为例）
ls .trae/ .cursor/           # skills/ agents/ workflows/ AGENTS.md cannbot-manifest.json
```

## 二、快速上手

在目标模型仓中提出需求：

```text
帮我优化 M200 这个视觉编码器模型的 NPU 推理性能，目标是单并发 avg 降到 6ms 以内
```

primary 会按 AGENTS.md 的强制规则分流：无基线 → 从条目 0 起走全流程；有基线 → 续跑循环或做单点专项。

### 三条典型用法

| 场景 | 说法示例 | 走向 |
| --- | --- | --- |
| 从零优化一个新模型 | 「优化 XX 模型的推理性能」 | 条目 0 → 14 全流程，再进循环 |
| 已有基线继续压 | 「XX 已经有基线了，继续压 QPS 到 1500」 | 条目 5 → 循环 |
| 只做某专项 | 「只对 attention 链做 FA 融合」「帮我定位一下精度」 | 直接调对应原子 skill |

## 三、安装内容

| 内容 | 说明 |
| --- | --- |
| 原子 skills（18 个） | `model-recommend-*`（源仓 cannbot-skills `community/model/`），覆盖环境、模型分析、基线、并发、精度、性能、图模式、算子适配、FA、多线程、访存、融合规划、kernel、自定义算子、运行时、回归与循环编排 |
| workflow 文档 | `workflows/model-recommend-infer-workflow.md` + `references/` 细则 + `templates/` 强制交付件模板 |
| Subagents | `agents/model-recommend-infer-{runner,analyzer,implementer,reviewer}.md` |
| hooks | 阶段提醒 + 角色越界保护（前置防护，非沙箱；只挂 Edit/Write/MultiEdit，Bash 写入不受控） |
| tests | **源仓自测，不随安装落位**：`tests/test_pre_tool_use.py`（守卫放行/阻断 26 例）、`tests/test_loop_state.py`（循环状态 12 例）；在本插件源目录下 `python3 tests/xxx.py` 运行 |
| 配置入口 | `AGENTS.md`，强制读取主工作流 |

## 四、核心工作流

```text
0 环境基线与路由 → 1 模型分析 → 2 单卡基线 → 3 并发与限核策略 → 4 精度基线门禁
    ↓
持续优化循环（一轮一动作，双门禁全程有效）
  5 性能分析（三表 + 四项专项）→ 6 图模式与 shape → 7 算子与图适配（含 FA）
  → 8 多线程与图并行 → 9 访存优化 → 10 融合规划 → 11 Kernel 生成
  → 12 自定义算子开发 → 13 运行时诊断（贯穿）→ 14 回归验收与基线管理
    ↓
终止条件：目标达成 / 连续 3 轮无收益 / 无可执行动作 / 轮次预算用尽
```

每个改动项都遵循：**分析 → 方案确认 → 实施（可开关可回退）→ 精度门禁 → 性能门禁 → 落地记账**。

## 五、可用技能（原子 skills）

| Skill | 用途 |
| --- | --- |
| `model-recommend-ascend-env-baseline` | 环境自检、输入格式路由、产物目录约定 |
| `model-recommend-structure-analysis` | 结构档案、算子构成、显存估算、可执行判定 |
| `model-recommend-baseline-run` | 首基线采集（时延 / QPS / HBM / profile / 精度） |
| `model-recommend-concurrency-strategy-analysis` | `THREAD_NUM` / `CORE_NUM` / batch 推荐（只分析） |
| `model-recommend-precision-comparison` | golden 标杆、精度门禁、分节点定位 |
| `model-recommend-performance-analysis` | 三表分析、bound 判定、性能门禁执行 |
| `model-recommend-profiling-deep-analysis` | 四项专项（算子执行 / 多流 / H2D-D2H / host） |
| `model-recommend-optimization-loop` | 持续优化循环编排与终止判定 |
| `model-recommend-ge-graph-optimization` | shape 策略、GE 编译选项、torchair / torch.compile |
| `model-recommend-fusion-operator-adaptation` | 算子替换、图融合 pass、等价改写 |
| `model-recommend-flash-attention-fusion` | FA 族融合确认与接入 |
| `model-recommend-multi-thread-optimization` | 并发与限核实施、sweep 验收 |
| `model-recommend-memory-access-optimize` | 访存优化：布局/等价改写、搬运与计算重叠（memory-bound 热点） |
| `model-recommend-fusion-planning-estimation` | 融合候选清单、Roofline bound、收益排序 |
| `model-recommend-kernel-generation` | AscendC / cannbot-dsl 融合 kernel 开发 |
| `model-recommend-custom-op-development` | 功能补齐向算子开发与 GE 接入 |
| `model-recommend-runtime-debug` | 报错 / 卡死定界与修复路径 |
| `model-recommend-regression-baseline-mgmt` | 台账、双门禁验收、收口报告与动作表 |

端到端流程由 `workflows/model-recommend-infer-workflow.md` 承载，不作为可独立调用的 skill 暴露。

## 六、可用 Agents

| Agent | 职责 |
| --- | --- |
| `model-recommend-infer-runner` | 环境自检、单卡基线、profiling 采集（只跑不改） |
| `model-recommend-infer-analyzer` | 模型分析、并发策略、性能与四项专项分析、融合规划（只读） |
| `model-recommend-infer-implementer` | 按单条动作实施改动，保留开关与回退 |
| `model-recommend-infer-reviewer` | 双门禁复核、台账核对、收口核验（不改代码） |

## 七、常见问题

### Q: 如何查看帮助信息？

```bash
bash init.sh --help
```

### Q: 循环什么时候停？

四种终止原因：`target_reached`（目标连续 2 次复测达标）、`converged_no_gain`（连续 3 轮无收益）、`no_actionable`（无可执行动作）、`budget_exhausted`（默认 10 轮上限）。判据见 `workflows/references/loop-rules.md`。

### Q: 为什么每轮只改一个动作？

为了保证归因唯一：一轮多改会让收益无法归属到具体手段，回退时也无法二分定位。

### Q: 性能目标由谁定？

必须由用户指定（指标 + 阈值，如 `avg ≤ 1.0ms`）。缺失时 primary 会来问，不会自行设定。

### Q: 低精度能不能默认开？

不能。`FORCE_16` / `ENABLE_HF32` / `precision_mode` 等默认关闭，启用须「用户人工确认 + 精度门禁记录误差」双前置。

### Q: 单点优化和整网优化如何选择？

| 场景 | 推荐方式 |
| --- | --- |
| 模型从适配到性能达标的完整链路 | 整网流程（「帮我优化 XX 模型的推理性能」） |
| 已有基线，继续榨性能 | 整网流程的循环段（「XX 有基线了，继续压」） |
| 只做 FA 融合 / 精度定位 / profiling 分析 | 直接调用对应原子 skill |

### Q: 如何更新？

```bash
cd cannbot/plugins-community/model-recommend-infer-optimize && bash init.sh
# Claude Code：/plugin update model-recommend-infer-optimize@cannbot
```

---

## 总结

1. 一条主工作流：条目 0-14 线性建基线 + 持续优化循环收敛，全程双门禁。
2. 四个 subagent 分工：采集、分析、实施、验收互不越界，primary 只编排。
3. 十八个原子 skill 承接具体技术判定，单点诉求可直接调用、不进整网流程。
4. 所有改动可开关、可回退、可归因；台账、每轮报告、状态矩阵与动作表全在约定目录。

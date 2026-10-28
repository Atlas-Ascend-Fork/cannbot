# CANNBot Ascend C 算子自动生成快速入门指南

## 概述

Ascend C 算子自动生成模式适用于**从 PyTorch Model 自动生成 Ascend C Kernel**场景，支持双路径：简单算子走 ops-direct-invoke 工作流（Architect 设计 → Developer 实现 → Reviewer 审查），复杂算子走 TileLang 设计表达 → AscendC 转译优化，端到端完成算子开发。

### 工作流

```
Phase 0: 参数确认 + 算子分类  (解析输入，判定简单/复杂路径)
Phase 1: 环境准备 + 工程初始化  (复制算子文件 + 初始化 kernel 工程)
Phase 2: Case 精简           (tilelang2ascend-case-simplifier)
Phase 3: 设计表达            (分支)
  ├─ 简单算子: 架构设计 + 设计串讲 (ops-direct-invoke: DESIGN.md + PLAN.md + WALKTHROUGH.md)
  └─ 复杂算子: TileLang 设计  (tilelang2ascend-tilelang-designer + 退化检测 + 迭代)
Phase 4: AscendC 生成与验证   (分支)
  ├─ 简单算子: 开发实现 + 代码审查 + 修复循环 (ops-direct-invoke: 渐进式开发 + REVIEW.md + 最多3轮修复)
  └─ 复杂算子: 转译          (tilelang2ascend-translator + 退化检测 + 迭代)
Phase 5: 性能分析            (ops-profiling --compare 模式)
Phase 6: 全量验证
Phase 7: Trace 记录 + 知识演进  (tilelang2ascend-trace-recorder: trace.md →
                                经 ops-knowledge-ingest 路由按 OKF 格式写入共享知识库
                                runbooks/，供后续任务经 knowledge-query 检索复用)
```

### 算子分类路由

| 路径 | 算子类型 | Skill 链 |
|------|---------|---------|
| 简单算子 | Index, IndexPut, Gather, Scatter, Nonzero, RepeatInterleave, EmbeddingDenseBackward | ops-direct-invoke（Architect → Developer → Reviewer） |
| 复杂算子 | Attention, MatMul 变体, Norm 变体, Sort, TopK, 多输入融合 | tilelang2ascend-tilelang-designer → tilelang2ascend-translator |

## 一、环境搭建

### 前置条件

- 已安装 Python 3.8 或更高版本
- 已安装 PyTorch 2.0 或更高版本
- 已安装 tilelang-ascend，具体安装方式请查阅 [tilelang-ascend readme](https://github.com/tile-ai/tilelang-ascend/blob/ascendc_pto/README.md#method-3-compile-and-install-from-source)
- 已安装 CANN Toolkit（建议 ≥ 9.0.0），具体版本配套关系请查阅 [CANN Release Notes](https://www.hiascend.com/cann/document)
- 已配置 NPU 设备（支持 Ascend 910/950 PR 等芯片）
- 已安装 OpenCode、Claude Code、Codex、DeepSeek Harness（DSH）、TRAE、Cursor、Copilot、CodeArts 等受支持的 AI 编程工具

### 安装

安装器支持 8 个工具、两级安装范围。**目标目录可省略，默认当前工作目录**；也可用位置参数或 `--target` 显式指定。

| 工具 | `tool` 参数 | 项目级 | 全局级 | 项目级安装位置 |
| --- | --- | --- | --- | --- |
| OpenCode | `opencode` | ✅ | ✅ | `.opencode/{skills,agents,hooks}/` |
| Claude Code | `claude` | ✅ | ✅ | `.claude/{skills,agents,hooks}/` |
| Codex | `codex` | ✅ | ✅ | `.agents/skills/` + `.codex/agents/` |
| DSH | `dsh` | ✅ | ✅ | `.dsh/{skills,agents}/` |
| TRAE | `trae` | ✅ | ❌ | `.trae/{skills,agents}/` |
| Cursor | `cursor` | ✅ | ✅ | `.cursor/{skills,agents,hooks}/` |
| Copilot | `copilot` | ✅ | ✅ | `.github/{skills,agents,hooks}/` |
| CodeArts | `codearts` | ✅ | ✅ | `.codeartsdoer/{skills,agents,hooks}/` |

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git ~/cannbot

# 缺省：装到当前目录（在算子工程根执行）
cd /path/to/your/operator-project
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh project dsh

# 显式指定目标目录：位置参数或 --target 均可
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh project codex /path/to/your/operator-project
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh project codex --target /path/to/your/operator-project
```

> 本插件的 19 个 Skill 全部来自子模块 `vendor/cannbot-skills`，因此克隆必须带 `--recurse-submodules`；
> 若已经克隆过仓库，先执行 `git submodule update --init --recursive`。
>
> 项目级安装把 skill / agent / 配置写入目标目录；全局级写入各工具的用户配置根（见下表），此时目标目录参数会被忽略。
> 安装结束会逐个校验依赖 Skill 是否可达（缺失或断链会报错并以非零码退出），全部通过才返回 0。
> 安装器只替换自己创建的软链：目标目录里同名的用户软链、真实文件/目录会被保留并告警，不会被删除。
> Codex / DSH 的项目根默认取最近的 `.git` 祖先（可用 `CANNBOT_PROJECT_ROOT` 覆盖）；显式传入目标目录时以参数为准。

全局级安装位置：

| 工具 | 全局根 |
| --- | --- |
| OpenCode | `~/.config/opencode` |
| Claude Code | `~/.claude` |
| Codex | `~/.agents/skills/` + `~/.codex/` |
| DSH | `$DSH_HOME`（默认 `~/.dsh`） |
| Cursor | `~/.cursor` |
| Copilot | `~/.copilot` |
| CodeArts | `~/.codeartsdoer` |

#### Claude Code（推荐）

**首选：Plugin Marketplace（一键安装）**

```bash
# 注册 marketplace（首次，GitCode 仓库需完整 URL）
/plugin marketplace add https://gitcode.com/cann/cannbot.git

# 安装插件
/plugin install tilelang2ascendc-ops-generator@cannbot
```

**备选：init.sh 脚本**

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/tilelang2ascendc-ops-generator
bash init.sh project claude     # 项目级（当前目录）
bash init.sh global claude      # 全局级
```

#### 其他工具

<details>
<summary>OpenCode</summary>

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/tilelang2ascendc-ops-generator
bash init.sh project opencode                  # 项目级（默认，当前目录）
bash init.sh project opencode /path/to/proj    # 项目级，指定目录
bash init.sh global opencode                   # 全局级
```

</details>

<details>
<summary>Codex</summary>

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git ~/cannbot
cd /path/to/your/operator-project
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh project codex
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh global codex    # 全局级
```

安装后在项目根生成 `.agents/skills/`（Skill 索引）与 `.codex/`（`agents/*.toml` 自定义 Agent 和 `AGENTS.md`）——Codex 的技能根与配置根是分开的；全局级分别落在 `~/.agents/skills/` 与 `~/.codex/`。

> 项目级安装**不会覆盖**项目已有的 `AGENTS.md`；如需 CANNBot 编排配置，请手动合并插件自带的 `AGENTS.md`，或改用 `global` 级安装。

</details>

<details>
<summary>DeepSeek Harness（DSH）</summary>

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git ~/cannbot
cd /path/to/your/operator-project
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh project dsh
bash ~/cannbot/plugins-community/tilelang2ascendc-ops-generator/init.sh global dsh     # 全局级
```

安装后在项目根生成 `.dsh/`（项目级）或 `$DSH_HOME/`（全局级，默认 `~/.dsh`），包含 `skills/`、`agents/` 和 `AGENTS.md`。

> 同 Codex：项目级不会覆盖已有的 `AGENTS.md`（此时插件编排协议不加载，需要手动合并）。DSH 没有命名 Agent 注册机制，`.dsh/agents/` 下的文件是角色定义参考，子 Agent 由 prompt 驱动。
>
> `global dsh` 会以受管块方式写入 `$DSH_HOME/AGENTS.md`：保留文件里已有的用户内容与 `dsh/install.sh` 的派发协议块，重复安装不会重复追加。

</details>

<details>
<summary>TRAE</summary>

仅支持项目级安装。

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/tilelang2ascendc-ops-generator
bash init.sh project trae
```

> 仅支持 Trae CLI；如使用 Trae IDE，需要在对话框手动创建智能体。

</details>

<details>
<summary>Cursor</summary>

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/tilelang2ascendc-ops-generator
bash init.sh project cursor                    # 项目级
bash init.sh project cursor /path/to/proj      # 项目级，指定目录
bash init.sh global cursor                     # 全局级
```

安装后在目标目录生成 `.cursor/` 目录（项目级）或 `~/.cursor/` 目录（全局级），包含 skills/、agents/ 和 AGENTS.md。

</details>

<details>
<summary>Copilot</summary>

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/tilelang2ascendc-ops-generator
bash init.sh project copilot                   # 项目级
bash init.sh project copilot /path/to/proj     # 项目级，指定目录
bash init.sh global copilot                    # 全局级
```

安装后在目标目录生成 `.github/` 目录（项目级）或 `~/.copilot/` 目录（全局级），包含 skills/、agents/ 和 AGENTS.md。

</details>

<details>
<summary>CodeArts</summary>

```bash
git clone --recurse-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/tilelang2ascendc-ops-generator
bash init.sh project codearts                  # 项目级
bash init.sh project codearts /path/to/proj    # 项目级，指定目录
bash init.sh global codearts                   # 全局级
```

安装后在目标目录生成 `.codeartsdoer/` 目录（项目级）或 `~/.codeartsdoer/` 目录（全局级），包含 skills/、agents/ 和 AGENTS.md。

</details>

#### DeepSeek Harness（DSH）附加说明

DSH 的使用分两部分，第二部分可选：

1. **默认安装面**：`bash init.sh project dsh`（或指定目录）即可。Skill 落在 DSH 原生根 `<项目根>/.dsh/skills/`，角色定义落在 `<项目根>/.dsh/agents/`，`AGENTS.md` 由 DSH 原生加载。项目级安装不会修改 `$DSH_HOME` 下的任何配置。
2. **可选：DSH 派发协议适配器**。DSH 没有命名 Agent 注册机制，Orchestrator 需要按"读取角色定义正文 → 连同任务输入作为子代理 prompt"的方式派发。如需把这段协议写入 DSH 用户级指令：

```bash
bash dsh/install.sh --dsh-home "${DSH_HOME:-$HOME/.dsh}"
```

   该脚本只在 `$DSH_HOME/AGENTS.md` 写入一个受管标记块——**只有 DSH 读取该文件**，不影响 Claude Code / Codex / OpenCode / TRAE；执行幂等，可随时卸载：

```bash
bash dsh/uninstall.sh --dsh-home "${DSH_HOME:-$HOME/.dsh}"
```

   DSH 的指令文件是用户级的（DSH 未提供项目级配置通道），因此该受管块对本机所有 DSH 会话生效；块内自带"仅当项目根存在 `.dsh/agents/` 时适用"的限定。详见 [dsh/README.md](dsh/README.md)。

   若之后重装 `global dsh`，安装器会保留该受管块，无需手动重装适配器。

#### Codex / DSH 适配边界

| 部件 | OpenCode / Claude / TRAE / Cursor / Copilot / CodeArts | Codex | DSH |
| --- | --- | --- | --- |
| Skill 索引与路由 | 原生目录 + 逐项符号链接 | ✅ `.agents/skills/` | ✅ `.dsh/skills/` |
| Agent | 原生 subagent 注册 | ✅ `.codex/agents/*.toml` 自定义 Agent | ⚠️ 仅角色定义参考（子 Agent prompt 驱动） |
| Hook（文档门禁 / 精度门禁） | Claude settings.json / OpenCode plugin / Trae hooks.json | ❌ 未适配 | ❌ 未适配（DSH 无项目级 hook 机制） |
| 主配置 AGENTS.md | 目标目录 / 配置根 | ✅ 项目根 / `~/.codex` | ✅ 项目根 / `$DSH_HOME` |

Codex / DSH 下的文档门禁与精度门禁未适配为 hook，改由 `AGENTS.md`、Agent 定义与 `SKILL.md` 的 prompt 约束承担；7 Phase 工作流、Skill 调用、Agent 调度与评测脚本执行不受影响。

## 二、快速上手

### 使用方式

#### 场景一：单算子生成
在交互界面中输入算子开发需求：

```
生成ascendC算子，npu=0，算子描述文件为 /path/to/op/model.py，输出到 /path/to/output/op_name/
```

CANNBot 会自动调度 tilelang2ascendc-kernel-generator 按 7 Phase 流程执行：
1. 解析参数、判定算子类型（简单/复杂）
2. 准备环境、初始化 kernel 工程
3. 精简测试用例（≤ 10 个代表性 case）
4. 设计表达（简单算子走 ops-direct-invoke 架构设计 + 设计串讲，复杂算子做 TileLang 设计）
5. AscendC 生成与验证（简单算子走开发实现 + 代码审查 + 修复循环，复杂算子走转译 + 迭代验证）
6. 性能分析（对比 reference 和 ascendc）
7. 全量用例验证 + 生成 trace.md 并完成知识演进（共享知识库 runbooks/ 更新）

#### 场景二：批量性能测试

适用于对多个已生成算子进行批量性能对比测试，支持单 NPU 串行或多 NPU 并行执行。

**操作步骤**：

1. 确保每个算子目录下已有 `model.py`、`model_new_ascendc.py` 和测试用例文件
2. 执行批量测试脚本：

```bash
# <skills-root> 按工具取：.claude/skills（Claude）、.opencode/skills（OpenCode）、
# .agents/skills（Codex）、.dsh/skills（DSH）等
bash <skills-root>/ops-profiling/scripts/msprof_profile_run.sh --batch \
    --base-dir /path/to/output_performance \
    --max-jobs 7 \
    --device-start 1
```

**参数说明**：
- `--base-dir`: 包含多个算子输出子目录的根目录（必填）
- `--max-jobs`: 最大并发数（默认 7）
- `--device-start`: 起始 NPU 设备 ID（默认 1）
- `--warm-up`: 预热次数（默认 3）

### 产出物示例

```
{output_dir}/
├── model.py                  # 算子描述文件（只读）
├── <op_name>.json            # 原始测试用例文件（备份保留）
├── <op_name>.json.bak        # 原始 .json 备份
├── docs/
│   ├── DESIGN.md             # 架构设计文档（简单算子路径）
│   ├── PLAN.md               # 开发计划（简单算子路径）
│   ├── WALKTHROUGH.md        # 设计串讲记录（简单算子路径）
│   └── REVIEW.md             # 代码审查报告（简单算子路径）
├── design/
│   ├── block_level/          # Block-level 设计（复杂算子路径）
│   └── tile_level/           # Tile-level 设计（复杂算子路径）
├── kernel/                   # AscendC kernel 实现
├── model_new_tilelang.py     # TileLang 实现（复杂算子路径）
├── model_new_ascendc.py      # AscendC 实现
├── performance.json          # 性能数据
└── trace.md                  # 执行记录
```

## 三、可用技能

| Skill | 用途 | 适用路径 |
|-------|------|---------|
| `tilelang2ascend-case-simplifier` | 测试用例精简 | 所有 |
| ops-direct-invoke (Architect + Developer + Reviewer) | 简单算子架构设计、开发实现、代码审查 | 简单算子 |
| `tilelang2ascend-tilelang-designer` | TileLang kernel 设计表达 | 复杂算子 |
| `tilelang2ascend-translator` | TileLang→AscendC 转译 | 复杂算子 |
| `tilelang2ascend-operator-project-init` | Kernel 工程初始化 | 所有 |
| `ops-profiling` | 性能测试分析（--compare 模式） | 所有 |
| `tilelang2ascend-trace-recorder` | 执行记录生成 | 所有 |

## 四、常见问题

### Q: 如何查看帮助信息？

```bash
bash init.sh --help
```

### Q: 支持全局安装吗？

支持。OpenCode / Claude Code / Codex / DSH / Cursor / Copilot / CodeArts 均支持 `global` 级安装，写入各自用户配置根；TRAE 仅支持项目级。global 与项目级可共存，项目级优先。

### Q: 目标目录可以省略吗？

可以。省略时安装到当前工作目录；也可用位置参数（`init.sh project codex /path/to/proj`）或 `--target` 指定。全局级安装忽略目标目录。

### Q: 简单算子和复杂算子有什么区别？

简单算子（Index, Gather, Scatter 等）走 ops-direct-invoke 工作流：Architect 架构设计 → Developer 渐进式开发 → Reviewer 代码审查（100分制评分 + 修复循环）。复杂算子（Attention, MatMul, Norm, Sort 等）需要先做 TileLang 设计表达，再转译为 AscendC 代码。

### Q: TileLang 验证失败了怎么办？

TileLang 当前主要用于设计表达，不是 correctness gate。若 TileLang 验证失败但设计意图正确，可跳过 TileLang 验证直接进入 AscendC 转译阶段。在 trace.md 中会记录跳过原因。

### Q: AscendC 验证迭代上限是多少？

最多 3 轮迭代。超过上限后停止并报告当前状态。

---

## 总结

1. 从 PyTorch Model 出发，支持双路径（简单/复杂）端到端完成算子开发
2. 使用 `init.sh` 脚本一键安装，支持 OpenCode / Claude Code / Codex / DSH / TRAE / Cursor / Copilot / CodeArts 八个工具，项目级与全局级（TRAE 仅项目级）
3. 7 Phase 工作流（含 Phase 7 知识演进闭环），自动算子分类路由，退化检测，迭代修复
4. 产出物包含设计文档/设计表达、kernel 代码、性能报告、trace 记录和演进知识库条目

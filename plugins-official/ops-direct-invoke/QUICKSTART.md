# ops-direct-invoke 快速开始

先准备 Git（支持 worktree 与 switch）、Node.js 20.11+、Python 3（含 PyYAML）、tmux 和 Agent 客户端，详见 [环境要求](README.md#环境要求)。以下以 OpenCode 为例；使用 Codex 或 Claude Code 时，将命令中的 `opencode` 换成 `codex` 或 `claude`。

## 普通用户：在工作区用 npx 安装（推荐）

```bash
cd /path/to/your-workspace
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool opencode
```

无需克隆仓库，安装完成即可在当前工作区使用。

## 开发者：克隆仓库，用 init 安装

```bash
git clone https://gitcode.com/cann/cannbot.git
cd cannbot
bash plugins-official/ops-direct-invoke/init.sh project opencode /path/to/your-workspace
```

已有本地 cannbot-skills 仓库时，用下面的命令复用：

```bash
bash plugins-official/ops-direct-invoke/init.sh project opencode /path/to/your-workspace \
  --skills /path/to/cannbot-skills
```

## 开始使用

在目标工作区启动客户端：

```bash
cd /path/to/your-workspace
opencode
```

向 Agent 提出需求：

> 请使用 ops-direct-invoke 开发一个 abs 算子，开发语言为 Ascend C 直调，(开发目标平台为 Ascend950PR/Kirin9030/...)。

根据 Agent 的集中问卷补齐算子规格、目标芯片、conda/Python 与 CANN 环境，以及允许修改的范围；也可在最初请求中直接提供。完成后查看 Agent 的交付说明；运行记录在工作区 `.cannbot/` 下。

详细安装参数见 [README](README.md#安装详解)。


DSL 全流程自动执行性能优化并回集成，替换原性能摸底。初始问卷会按安装版本的性能 Skill 确认优化轮数或目标、对标和环境；恢复时沿用有效确认。优化结果见本轮 `perf-optimize/run/`，最终版本及证据索引见 `perf-optimize/HANDOFF.md`。无有效收益时按原规则保留基线，实际结论以报告为准。

## DSL 版本与回退

新 DSL 工作流会创建独立本地代码仓，每轮修改在验证前提交；并行 Unit 使用独立 worktree。`WORK_DIR` 保持工作流目录，代码与测试使用脚本返回的 `CODE_DIR`。失败版本会保留；需要恢复时指定完整 SHA，恢复后重新验证。

无需用户逐次手工提交；Agent 按[代码版本协议](skills/ops-direct-invoke/references/code-versions.md)执行，verifier 审查证据。最终交付附 Git bundle、版本清单与恢复说明。已有运行目录不自动迁移；更新插件后在新一轮工作流使用此功能。

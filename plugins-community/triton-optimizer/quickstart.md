# Triton Optimizer 快速入门

## 概述

`triton-optimizer` 是 Triton Ascend NPU 算子 workflow 插件。它提供优化与转换两个入口 Skill（`triton-npu-optimize`、`triton-npu-convert`）、随插件 `skills/` 目录一起提供的 14 个配套支撑 Skills，以及用于 Claude Code 的 workflow 状态 hooks（`.helix/` 运行态目录）。

它适合两类任务：

- 优化已有 Triton Ascend NPU 算子，按 baseline/round 迭代记录。
- 将 PyTorch 算子转换为 PyTorch-facing、Triton Ascend NPU-backed 的实现，并完成验证。

## 一、安装

### 方式一：npm 统一安装器

```bash
cd /path/to/your/triton/project
npx @cannbot-plugin/cannbot@latest install triton-optimizer --tool claude --target .
```

`--tool` 支持 `opencode` / `codex` / `claude` / `trae` / `dsh`；workflow hooks 仅在 Claude Code 下生效，其它客户端只安装 Skills 与配置入口。

### 方式二：源码 init.sh

```bash
git clone https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/triton-optimizer

bash init.sh project claude /path/to/your/triton/project
```

`init.sh` 是统一安装器的源码入口（等价于 `cannbot install triton-optimizer --source <cannbot 仓库>`），当前仅支持 project 级安装。本插件的 Skills 全部自包含在插件 `skills/` 目录，不依赖 `vendor/cannbot-skills` submodule。

## 二、安装内容

| 内容 | 来源 | 安装位置 |
| --- | --- | --- |
| Skills（16 个 `triton-npu-*`） | 插件 `skills/` 目录 | 工具 Skills 目录（如 `.claude/skills/`、`.agents/skills/`） |
| Hooks（SessionStart / PreToolUse） | 插件 `hooks/` 目录 | 插件资产拷贝至 `.cannbot/plugins/triton-optimizer/hooks/`，并合并进 `.claude/settings.json`（仅 Claude Code） |
| 配置入口 | 插件 `AGENTS.md` | 项目根 `CLAUDE.md` / `AGENTS.md` 的 `cannbot:triton-optimizer` 标记块 |

## 三、使用

1. 在目标 Triton Ascend NPU 算子项目中启动 AI 编程工具
2. 优化任务：

```text
请使用 triton-npu-optimize 优化当前目录的 Triton 算子，并从 baseline 开始记录每轮结果。
```

3. 转换任务：

```text
请使用 triton-npu-convert 将 /path/to/op.py 转成 Triton Ascend NPU 实现，输出到 /path/to/triton_op.py 并验证。
```

## 四、验证安装

```bash
# 查看安装注册表
cat .claude/cannbot-plugin.json

# 查看 skills
ls .claude/skills | grep triton-npu
```

Claude Code 下还应能看到 `.claude/settings.json` 中合并的 SessionStart / PreToolUse hooks，指向 `.cannbot/plugins/triton-optimizer/hooks/`。

## 五、更新

```bash
cd cannbot
git pull
bash plugins-community/triton-optimizer/init.sh project claude /path/to/your/triton/project
```

或使用 npm 方式重新执行安装命令即可（重复安装幂等）。

# ops-direct-invoke 快速开始

先准备 Node.js 20.11+、Python 3（含 PyYAML）、tmux 和 Agent 客户端，详见 [环境要求](README.md#环境要求)。以下以 OpenCode 为例；使用 Codex 或 Claude Code 时，将命令中的 `opencode` 换成 `codex` 或 `claude`。

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

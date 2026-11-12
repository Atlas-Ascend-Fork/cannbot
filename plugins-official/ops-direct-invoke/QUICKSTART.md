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

首次安装依次选择平台、芯片型号、工程框架、开发语言和交互偏好，菜单只显示当前选择适用的选项，仅剩一个选项时自动采用并跳过。用 ↑/↓ 移动、回车确认，也可按数字跳转；每道问题前的括号显示已完成百分比；芯片选择“其他（自行输入）”可填写具体型号；芯片或语言尚未明确时选“暂不确定”，留待具体开发任务确认。目标目录已有内容时会先询问是更新现有组件还是清空重装，选更新时仍会完整走一遍问卷、已保存的答案作为默认选项。问卷完成后进入安装，每个步骤前会显示该步骤的内容和完成百分比；安装结束以绿色输出安装目录，并给出后续使用方法。使用 dsh 客户端时，安装开始前会确认是否安装 CANNBot DSH 插件（装在当前目录之外的用户全局 DSH 环境，装完需重启 DSH）；非交互安装可用 `CANNBOT_INSTALL_DSH_PLUGIN=1/0` 控制。

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

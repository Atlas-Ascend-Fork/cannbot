# CANNBot torch-compile 快速入门

`torch-compile` 是 PyTorch `torch.compile` 图模式的编排入口，通过专业 Agent 处理不同图模式。当前提供 `torch-npugraph-ex`，覆盖昇腾 NPU 的 npugraph_ex / aclgraph 配置、脚本迁移、自定义算子入图、编译/运行错误及性能诊断。

## 仓库分工

- `cannbot/plugins-official/torch-compile/` 维护编排指令、Agent、Hook、评测、插件清单及安装入口。
- `cannbot-skills/graph/` 维护全部 7 个基础 Skills，名称和内容保持不变，可独立使用。
- `plugin-sources.json` 声明共享 Skills。源码安装使用软链，npm 构建将这些 Skills 复制进自包含包。

## 源码安装

需要 Node.js >= 20 和 Git。统一安装器支持项目级 OpenCode、Codex、Claude Code、TRAE、DSH 和 CodeArts。

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot
bash plugins-official/torch-compile/init.sh project opencode /absolute/project
```

将 `opencode` 换成 `codex`、`claude`、`trae` 或 `dsh` 即可。脚本可从任意目录调用；省略目标项目时默认安装到 cannbot 仓库根目录。

共享 Skills 默认跟随应用仓的同名远端分支，分支不存在时使用 `master`。联调两个本地仓库时，用 `--skills` 指定基础技能仓：

```bash
bash plugins-official/torch-compile/init.sh project codex /absolute/project \
  --skills /absolute/cannbot-skills
```

`--skills <SHA>` 可固定共享 Skills 的提交。全局安装及 Cursor、Copilot 不属于当前统一安装器的支持范围；需要独立技能时可直接安装 cannbot-skills 的基础 Skills。

## npm 安装

在目标项目中执行：

```bash
npx @cannbot-plugin/cannbot@latest install torch-compile --tool opencode
```

此命令要求 npm 包已发布并包含 `torch-compile`。在迁移尚未发布时，使用上面的源码安装方式；本次本地改动不会更新已发布的 npm 包。

## Claude Code 插件市场

```text
/plugin marketplace add https://gitcode.com/cann/cannbot.git
/plugin install torch-compile@cannbot
```

市场中的 `torch-npugraph-ex-skills` 依赖仍从 cannbot-skills 的 `graph/` 获取。`SessionStart` Hook 注入编排上下文和当前安装的技能、Agent 路径。

## 安装结果

| 客户端 | Skills | Agent |
|--------|--------|-------|
| OpenCode | `.agents/skills/` | `.opencode/agents/torch-npugraph-ex.md` |
| Codex | `.agents/skills/` | `.codex/agents/torch-npugraph-ex.toml`（由统一安装器生成） |
| Claude Code | `.claude/skills/` | `.claude/agents/torch-npugraph-ex.md` |
| TRAE | `.trae/skills/`（已有变体配置时跟随变体） | 相应配置目录的 `agents/` |
| DSH | `.dsh/skills/` | `.dsh/agents/torch-npugraph-ex.md` |

编排指令合并到项目 `AGENTS.md`（Claude Code 为 `CLAUDE.md`），安装记录保存在客户端配置目录的 `cannbot-plugin.json`。Claude Code 同时安装 SessionStart Hook；其他客户端以项目指令和 Agent 定义为入口。

## 使用

启动客户端，直接描述需求，例如：

```text
把这个 Eager 推理脚本接入 npugraph_ex，保持原来的代码结构。
torch.compile 在 capture 阶段报错，帮我采集日志并定位问题。
这个自定义算子如何注册 Meta 推导并进入图模式？
```

主 Agent 负责识别需求与图模式，npugraph_ex 专业 Agent 加载对应 Skill 执行。新增图模式时扩展 `agents/` 和插件清单，基础技能继续在 cannbot-skills 维护。

## 开发验证

在 cannbot 根目录执行：

```bash
git submodule update --init --depth 1 vendor/cannbot-skills
npm --prefix script test
npm --prefix script run pack:check
```

更完整的安装选项见 [统一安装指南](../../script/docs/cannbot-workflows.md)。

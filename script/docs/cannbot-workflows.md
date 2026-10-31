# CANNBot 工作流安装与使用指南

## 安装方式

安装 `ops-direct-invoke` 时，统一安装器按其 `plugin-install.json` 的 `initializeBefore` 声明，先完整初始化 `ops-perf-optimize`，再初始化直调。源码与 npm 安装使用相同顺序、客户端和目标目录；源码两次安装复用同一个已选公共 Skill checkout。性能插件维护自身的 Skill、角色、hooks 和知识依赖，安装记录保留两个插件。

普通用户在目标项目中执行各插件下方的 `npx` 命令。源码安装进入对应插件目录执行：

```bash
cd plugins-official/<plugin>
bash init.sh
```

对声明公共 Skill 依赖的源码插件，统一安装器会初始化 `vendor/cannbot-skills`，每次安装从其 `origin` 获取与 CANNBot 当前分支同名分支的最新提交；远端没有同名分支时回退到 `master`。CANNBot 处于 detached HEAD 时也使用 `master`。Skill 软链接到目标项目，不需要先手动初始化子模块。此操作不更新 CANNBot 主仓；主仓更新仍由用户执行。

统一 CLI 和使用通用入口的插件 `init.sh` 均支持 `--skills <SHA|path>`：

```bash
# 默认同步 cannbot-skills 同名分支，不存在则使用 master
node script/bin/cannbot.js install ops-direct-invoke --source "$PWD" --tool codex --target /absolute/project

# 指定完整提交；本地已存在的提交也可使用 7 位以上短 SHA
bash plugins-official/ops-direct-invoke/init.sh project codex /absolute/project --skills <SHA>

# 使用本地开发仓；相对路径以命令执行目录为基准
bash plugins-official/ops-direct-invoke/init.sh project codex /absolute/project --skills /absolute/cannbot-skills
```

已有目录优先按路径识别，要求路径是 Git 工作树根目录且含插件声明的 Skill。路径模式不联网、不修改子模块，保留本地未提交内容。SHA 模式只接受 commit 的十六进制 SHA；远端缺失提交需提供完整 SHA，找不到的短 SHA 会报错。显式 `--skills` 跳过默认分支选择。默认更新和指定 SHA 前会检查子模块工作树，存在未提交修改时停止，不自动清理。远端查询或拉取失败即安装失败，不当作分支缺失触发回退，也不回退旧版本。

公共仓的最新版本可能与某个工作流当前声明的 Skill 名称不一致；缺少声明的 Skill 时安装失败，需通过 `--skills` 选择与该工作流兼容的提交或本地检出。版本记录用于追溯选择，不代替跨仓兼容性验证。

上述行为仅适用于统一 CLI 和使用通用入口的插件 `init.sh`；`ascendc-port-orchestrator/init.sh` 等独立入口未接入，保留原有安装方式。统一安装器对打包安装和不依赖公共 Skill 的插件使用 `--skills` 会明确报错。npm 打包安装仍复制包内资源。

统一安装记录位于 `<目标项目>/<客户端配置目录>/cannbot-plugin.json`，例如 `.codex/cannbot-plugin.json`；同一插件重装会更新记录。`source.revisions` 保存 CANNBot 主仓 SHA，以及 `cannbot-skills` 的完整 SHA、选择模式、原始参数、dirty 标志和本地模式的绝对路径。自动选择时 `selection` 为 `latest-branch`，`requested` 保存实际选中的分支名（回退时为 `master`）。

```json
{
  "source": {
    "kind": "repository",
    "revisions": {
      "cannbot": "<主仓完整 SHA>",
      "cannbot-skills": {
        "selection": "local-path",
        "requested": "/absolute/cannbot-skills",
        "commit": "<公共仓完整 SHA>",
        "dirty": false,
        "path": "/absolute/cannbot-skills"
      }
    }
  }
}
```

默认更新或指定 SHA 可能使子模块 HEAD 与主仓记录的 Gitlink 不同，主仓状态因此显示子模块版本变化。源码安装的软链接指向可变工作树：以后更新该仓，会影响此前安装的项目（指定 SHA 模式也一样）。记录追溯的是安装当时的版本；dirty 为 true 时，SHA 不包含本地未提交内容。需要冻结多个项目的不同版本时，使用独立检出目录并分别通过 `--skills <path>` 安装。

声明 `cannbot-knowledge` 依赖的插件在克隆后，统一调用该仓的 `install.sh <tool> <target> consumer`；仓库更新由统一 CLI 负责，consumer 复用该 checkout。知识仓安装器负责运行依赖、完整仓库 Skill 链接、`.cannbot/knowledge.env`、资源和索引。统一 CLI 再通过安装后的规范 Query 入口执行只读 `discover`，确认知识根后将 `knowledgeIndex` 记为 `ready`。初始化或检查失败会输出原因和修复命令，保留 `pending`，不阻断插件安装。

`CANNBOT_SKIP_DEPENDENCY_REPOS=1` 跳过依赖仓及 consumer；`CANNBOT_SKIP_KNOWLEDGE_INDEX=1` 仅跳过 consumer 初始化。显式离线、仅消费知识卡时使用 `CANNBOT_SKIP_KNOWLEDGE_RESOURCES=1`，会映射到 consumer 的 `--skip-resources`，仍准备并检查检索索引。Python 解释器可通过知识仓支持的 `CANNBOT_PYTHON` 指定。索引生命周期由知识仓当前安装器管理，旧版 `CANNBOT_REBUILD_KNOWLEDGE_INDEX` 不再控制索引构建；正常调优与查询不自动重建索引。

## 算子领域

### 算子生成

#### Step 1：一键安装

通过 npm 插件化一键安装。

OpenCode：

```bash
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool opencode
```

Codex：

```bash
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool codex
```

Claude Code：

```bash
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool claude
```

TRAE：

```bash
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool trae
```

DSH：

```bash
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool dsh
```

#### Step 2：启动 Agent 客户端

在当前项目根目录启动 Agent 客户端。以 OpenCode 为例：

```bash
opencode
```

#### Step 3：提示词样例

```text
请使用 ops-direct-invoke 工作流，根据当前项目中的算子需求生成完整的 Ascend C Kernel 直调算子。
先分析需求和运行环境，再完成方案设计、代码实现、测试、精度与性能验收。
```

### TileLang 算子开发

```bash
npx @cannbot-plugin/cannbot install tilelang-op-orchestrator --tool codex
# 或从源码安装，默认配置写入 TileLang 插件自身目录：
bash plugins-official/tilelang-op-orchestrator/init.sh project codex --skills /absolute/cannbot-skills
```

`--tool` 支持 `opencode`、`codex`、`claude`、`trae`、`dsh`。启动客户端后描述需求，例如：

```text
使用 tilelang-op-orchestrator 开发一个 float16 的 Abs 算子。先识别本机芯片，按对应平台流程完成设计、生成与测试。
```

TileLang 源码入口省略安装路径时固定安装到 `plugins-official/tilelang-op-orchestrator/`，安装后从该目录启动客户端；显式传入路径可选择其他项目。安装时只配置 13 个共享技能、6 个原有角色和完整的 `AGENTS.md` 入口；工作流保留原来的 `workflows/` 目录及正文。会话中依据完整 SoC / NpuArch 证据选择独立的 Ascend910 / Ascend950 工作流，再按该分支准备框架源码与运行环境。详见 [TileLang 快速入门](../../plugins-official/tilelang-op-orchestrator/quickstart.md)。

## 模型领域

### 模型迁移与推理优化


#### Step 1：一键安装

通过 npm 插件化一键安装。

OpenCode：

```bash
npx @cannbot-plugin/cannbot install model-infer-optimize --tool opencode
```

Codex：

```bash
npx @cannbot-plugin/cannbot install model-infer-optimize --tool codex
```

Claude Code：

```bash
npx @cannbot-plugin/cannbot install model-infer-optimize --tool claude
```

TRAE：

```bash
npx @cannbot-plugin/cannbot install model-infer-optimize --tool trae
```

DSH：

```bash
npx @cannbot-plugin/cannbot install model-infer-optimize --tool dsh
```

#### Step 2：启动 Agent 客户端

在当前项目根目录启动 Agent 客户端。以 OpenCode 为例：

```bash
opencode
```

#### Step 3：提示词样例

```text
使用 model-infer-optimize，把当前 PyTorch 模型迁移到昇腾 NPU 推理。先建立 CPU 基线，再处理不支持算子和设备适配，最后完成精度对齐、性能分析和优化，并输出可复现的验证命令。
```

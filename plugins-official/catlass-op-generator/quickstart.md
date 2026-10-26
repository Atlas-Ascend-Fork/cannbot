# CATLASS 算子生成快速开始

通过 CANNBot 安装 `catlass-op-generator`。安装器从 cannbot-skills 的 `ops/` 接入六个 `catlass-cpp-*` Skills，并从 cannbot-knowledge 提供 `knowledge/ops/catlass/`；项目中不生成私有知识副本。

## 环境要求

- Git、Node.js ≥20；使用 npm 方式时还需 npm/npx。
- 对应客户端：OpenCode、Codex、Claude Code、TRAE 或 DSH。
- 使用初始化和知识读取脚本时需要 Python 3，建议 3.10 或更高版本。
- 算子编译、运行另需目标架构的 CANN、CATLASS 源码及设备环境。安装 Skills 和知识库不代表这些运行环境已就绪。

## 源码安装（当前可用）

使用官方主仓最新 `master`，安装器自动初始化共享 Skills submodule 并下载知识库：

```bash
git clone --branch master https://gitcode.com/cann/cannbot.git /path/to/cannbot
bash /path/to/cannbot/plugins-official/catlass-op-generator/init.sh \
  project codex /path/to/workspace
```

`/path/to/workspace` 是开发项目，不是插件源码目录。安装后进入该项目启动 `codex`。
客户端参数可以替换为 `opencode`、`claude`、`trae` 或 `dsh`。不提供目标路径时默认安装到 cannbot 仓根，建议明确目标路径。

## npx 安装

```bash
npx @cannbot-plugin/cannbot@latest install catlass-op-generator \
  --tool codex --target /path/to/workspace
```

npx 默认拉取官方主仓最新源码及共享 Skills，再安装插件并下载知识库。

## 自动安装的依赖

| 仓库 | 分支 | 资源 |
|---|---|---|
| `https://gitcode.com/cann/cannbot-skills.git` | 默认匹配主仓分支，不存在时使用 `master` | `vendor/cannbot-skills/ops/` 下六个 `catlass-cpp-*` Skills |
| `https://gitcode.com/cann/cannbot-knowledge.git` | `master` | `knowledge/ops/catlass/` 下的知识卡 |

```text
<workspace>/
├── .agents/skills/catlass-cpp-*        # Codex / OpenCode 的六个 Skill
└── .cannbot/dependencies/catlass-op-generator/
    └── cannbot-knowledge/knowledge/ops/catlass/
```

六个 Skill 为 `catlass-cpp-interface`、`catlass-cpp-reference`、`catlass-cpp-design`、
`catlass-cpp-develop`、`catlass-cpp-test`、`catlass-cpp-knowledge`。
Claude Code 使用 `.claude/skills/`；其他客户端使用其对应 Skill 目录。
项目配置目录下的 `cannbot-plugin.json` 记录知识库依赖路径及六个已安装 Skill 的路径。
源码入口把 Skills 链接到主仓的 `vendor/cannbot-skills/ops/`；npx 安装复制到客户端 Skill 目录，并为 Codex 生成包含六个 Skill 的原生插件。

六个 Skill 和知识库均为完整工作流所必需。安装后执行下面的知识读取验证，确认知识库可用。
源码安装的 `--skills <SHA|path>` 可选择共享 Skills 版本，不改变知识库下载位置。

本插件通过 `catlass-cpp-knowledge` 直接读取这些 Markdown 卡片，不要求另行执行知识仓的 `install.sh`、建立通用检索索引或下载全部外部文档归档。
`CANNBOT_KNOWLEDGE_ROOT` 和 `--knowledge-root` 若用于知识读取，均指向知识**仓根目录**，不是其 `knowledge/` 子目录；它们不会改变安装器下载依赖的位置。

## 安装验证

以下命令在目标项目执行，适用于 Codex / OpenCode；Claude Code 将 `.agents/skills` 换为 `.claude/skills`：

```bash
cd /path/to/workspace
python3 .agents/skills/catlass-cpp-knowledge/scripts/record_knowledge.py \
  initialize --project-root "$PWD"
python3 .agents/skills/catlass-cpp-knowledge/scripts/record_knowledge.py \
  query --project-root "$PWD" --type operators --family sparse_flash_mla --compact
```

初始化应返回 `status=passed` 和卡片数量。查询返回相对 `path` 后，传给同一脚本的 `get --project-root "$PWD" --path <返回路径>` 读取完整正文。
如果配置了自定义知识根，以上命令会读取该配置；验证默认安装目录时先确认未设置其他根。

## 开始开发

工作区根目录应有 CATLASS 源码 `catlass/include`、`catlass/examples` 和目标算子的 `operators/`。先确定算子的数学语义和目标架构，再使用 `catlass-cpp-interface` 初始化工程：

```bash
bash <installed-catlass-cpp-interface>/scripts/init_operator_project.sh my_operator
bash <installed-catlass-cpp-interface>/scripts/init_operator_project.sh my_attention --algorithm-family flash_attention
```

不指定家族时使用 `general`。初始化后依次完成 interface、reference、design、implementation、validation；每次继续前校验 `operators/<name>/docs/workflow.json`。设计阶段通过 `catlass-cpp-knowledge` 查询 `guides/` 与目标家族的 Operator 卡，按返回的完整路径读取正文。

启动客户端后可使用以下提示词，将路径和架构替换为实际值：

```text
请使用 catlass-op-generator 开发 CATLASS C++ 算子。
CATLASS 源码：/path/to/workspace/catlass；目标架构：<实际架构>。
需求和 PyTorch 标杆：<实际文件路径>。
先检查环境、读取已安装的 Skill 和知识，确认接口与数学语义，再按五阶段推进。
```

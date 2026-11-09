---
name: tilelang2ascendc-knowledge
description: Use when querying, initializing, recording, or promoting project-local tilelang2ascendc staging knowledge in the OKF v0.2 project bundle
---

# tilelang2ascendc 暂存知识管理

本 Skill 管理**插件暂存知识**，不管理固定知识库。

| 知识 | 位置 | 权限 | 检索方式 |
|---|---|---|---|
| 固定知识 | `<cannbot>/vendor/cannbot-knowledge/knowledge/` | 只读 | `knowledge-query` Skill（由知识仓安装器提供） |
| 插件内置暂存 | `<plugin>/knowledge/` | 只读 | 本 Skill 的 `query --scope builtin` |
| 项目暂存副本 | `<project>/.tilelang2ascendc/knowledge/` | 可写（仅 `learned/`） | 本 Skill 的 `query` |

固定知识是唯一权威来源；本 Skill 不复制、不修改、不提升写入固定知识库。

## 路径

```text
PROJECT_ROOT   = 当前算子工程根目录
PLUGIN_KNOWLEDGE = <插件配置根>/knowledge
PROJECT_BUNDLE = $PROJECT_ROOT/.tilelang2ascendc/knowledge
SCRIPT = <插件配置根>/skills/tilelang2ascendc-knowledge/scripts/knowledge_store.py
```

项目副本不存在时先执行 `initialize`；`initialize` 只复制缺失文件，不覆盖已有内容。

## 初始化

```bash
python3 "$SCRIPT" initialize \
  --project-root "$PROJECT_ROOT" \
  --builtin-root "$PLUGIN_KNOWLEDGE"
```

## 查询

```bash
python3 "$SCRIPT" query \
  --project-root "$PROJECT_ROOT" \
  --builtin-root "$PLUGIN_KNOWLEDGE" \
  [--scope auto|project|builtin|all] \
  [--category learned|optimization|debug] \
  [--type Runbook] [--tag sync] [--status draft] \
  [--text "<报错 / API 名 / 现象短语>"] [--limit 5] [--json]
```

- 默认 `--scope auto`：项目副本存在时查项目副本，否则查内置 Bundle；`all` 同时查两者，
  同一相对路径以项目副本为准。
- 文本检索按标题、描述、标签、路径和正文加权；零命中时明确返回 `matched: 0`，不得据此
  推断“没有相关知识”，也不得编造卡片。
- 命中后读取卡片全文，核对 `platforms`、`status` 和正文中的适用条件。

## 记录（Phase 7 唯一写入口）

```bash
python3 "$SCRIPT" record \
  --project-root "$PROJECT_ROOT" \
  --title "<一句话结论>" \
  --description "<现象、触发条件、修复与验证的摘要>" \
  --kind implementation_trap \
  --tags ascendc,tilelang,sync,precision \
  --platform a2 \
  [--slug <snake_case_slug>] \
  [--body "<正文>"] [--body-file <path>] \
  [--source "<可核验来源>"] [--force]
```

约束：

- 只写入 `$PROJECT_BUNDLE/learned/<slug>.md`，并自动重建 `learned/index.md`；
- 固定 `status: draft`，不写 `verified`，不伪造来源；
- 写入前必须先在项目副本和固定知识中查重；同主题优先更新而不是新建；
- 标题、触发条件、探针、修复和验证信号必须来自本轮 `trace.md`，不得补造；
- `--force` 仅用于确认覆盖同一 slug 的旧草稿。

## 提升（只输出，不写源码仓）

```bash
python3 "$SCRIPT" promote \
  --project-root "$PROJECT_ROOT" \
  --path learned/<slug>.md \
  [--target-root <plugin-root>] \
  [--format patch|json]
```

`promote` 只生成评审清单和 unified diff，不写入插件仓库，更不写入 `cannbot-knowledge`。
提升条件：至少两个项目复现，或用户明确要求；随后人工提交插件仓库 PR 并走固定知识库评审。

## 失败语义

- 知识不可用或写入失败不阻断算子生成主流程；在 `trace.md` 记录
  `knowledge_writeback: skipped` 及原因。
- 不得为了“完成任务”把项目经验直接写入 `cannbot-knowledge`。

# A2/A3（arch 2201）legacy 工作流

`plugins-official/ops-registry-invoke/a2-a3/` 是 A2/A3 旧架构的**完整、隔离**工作树，与
cannbot 现有的 `ops-registry-invoke` 架构（`skills/`、`agents/`、`workflows/`）互不混用：

- 自己的 Skill：`skills/spec-to-design/`、`workflow/`（legacy `ops-registry-invoke-workflow`）；
- 自己的 agents：`agents/` 下 7 个 `ascendc-ops-*`；
- 自己的安装入口：`init.sh`（`--plugin-dir` 直接交给 `script/bin/cannbot.js`，项目级、
  幂等，不写 `AGENTS.md` 指令块）；
- 其余共享 Skill（`ops/*`、`infra/*`）不复制正文，见 `skills.txt`：dispatch 阶段按名从
  `https://gitcode.com/cann/cannbot-skills.git` 安装。

## 上下文

A2/A3 是 legacy 架构，不再演进，只保留原有能力；cannbot-skills 仓的
`plugins-official/ops-registry-invoke/` 目录后续会被删除，因此本目录只**复制**该目录里
legacy 工作流必需的内容（`workflow/`、`skills/spec-to-design/`、`agents/`），不复用也不
依赖它。来源 commit 记录在 `PROVENANCE.json`。

## 本地适配

本目录内容复制自 cannbot-skills 的 legacy 工作树，但有两处文件名在复制时做了适配（否则无法通过
cannbot 的 CodeCheck 门禁），文件内容与行为不变：

- `skills/spec-to-design/templates/` 下两个模板改名为 `DESIGN.template.md`、`PLAN.template.md`：
  `.templ` 是未知扩展名，OAT/RAT 的高字节启发式会把以中文开头的文件误判成二进制文件
  （`OAT.1 二进制文件`）；以 `.md` 结尾后按文本分类，与本仓其它中文 Markdown 一致；
- `workflow/resources/` 下两个 CLI 脚本改名为 `git_checkpoint.py`、`validate_workflow_state.py`，
  满足编码规范 `G.NAM.01` 的 snake_case 模块命名；脚本仍由工作流按路径调用。

## 安装

```bash
bash init.sh project opencode /path/to/work_dir
```

只从本 cannbot 检出解析 Skill/agent/资产，绝不读取或 clone `cannbot-skills` 的
`ops-registry-invoke` 目录；`ops/*`、`infra/*` 的 Skill 由 `npx skills add` 另行安装，
需要网络与 npm registry。

## 入口

唯一与现有架构共用的是 `ops-registry-invoke` 入口 Skill：它经 `workflow-dispatch`
把 A2/A3 路由到
`plugins-official/ops-registry-invoke/skills/ops-registry-invoke/workflows/a2-a3-op-develop.yaml`
（工作流的 dispatch 落点），由该工作流安装并驱动本目录。

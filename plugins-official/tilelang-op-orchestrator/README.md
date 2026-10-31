# TileLang 算子开发插件

本插件从 cannbot-skills 迁入，保留原有 `AGENTS.md`、`agents/`、`workflows/`、`references/`、`scripts/` 和 `hooks/` 的组织方式与工作流内容。

```bash
cd plugins-official/tilelang-op-orchestrator
bash init.sh project codex
# 本地技能仓联合开发：
bash init.sh project codex --skills /absolute/cannbot-skills
```

默认在插件目录生成项目配置，安装后从该目录启动客户端。13 个共享技能通过安装声明从 cannbot-skills 获取；npm 包携带这 13 个技能。安装适配只处理技能来源、客户端发现路径和安装记录。

安装到已有项目时，入口保留现有规则和其他插件内容，只新增或更新 `cannbot:tilelang-op-orchestrator` 受管区块；重复安装不会重复登记路由。指向其他来源的入口软链接、损坏或重复的区块标记、修改过且没有区块标记的旧 TileLang 入口会报错退出。插件自身的 `AGENTS.md` 保持原样。

- [完整入口](AGENTS.md)
- [快速入门](quickstart.md)
- [Ascend910 工作流](workflows/Ascend910/workflow.md)
- [Ascend950 工作流](workflows/Ascend950/workflow.md)

Ascend950 原始文件保留 [MIT 许可证](workflows/Ascend950/LICENSE)；跨平台钩子包装器复用仓内 CANN-2.0 实现，来源与声明见 [README.OpenSource](README.OpenSource)。其余内容适用仓库根许可证。

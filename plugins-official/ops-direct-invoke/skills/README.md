# Skill 目录

主入口与定制实现按以下职责维护，golden 保留需求和设计基准。

| 目录 | 职责 | 不包含 |
|---|---|---|
| `maintain/` | 工作流维护、检视与测试；`golden/` 保存需求与设计基准 | 用户算子的开发任务 |
| `orchestrator/` | 需求对齐、模板选择、工作区准备与调度 | 平台、语言的具体开发步骤 |
| `custom-skills/` | 按适用条件选择的定制能力 | 外部 Skill 和性能工作流的实现副本 |

直接链接选中的实现目录；工作区注册名由 `SKILL.md` 的 `name` 确定。主入口为 `ops-direct-invoke`，其余本插件 Skill 使用 `ops-direct-invoke-` 前缀。

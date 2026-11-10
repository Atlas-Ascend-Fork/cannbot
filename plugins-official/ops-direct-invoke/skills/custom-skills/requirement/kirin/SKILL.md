---
name: ops-direct-invoke-requirement
description: 在当前会话对齐 Kirin AscendC 算子的规格、Simulator 范围、工程、环境与权限。
---

# Kirin 需求分析

按[需求对齐](references/intake.md)与[需求清单](references/requirement-checklist.md)完成任务约定。仓库规则由已选 `ops-direct-invoke-repo-guide` 提供。

Kirin 当前只支持 AscendC，不提供 DSL 或独立 TensorAPI 选项。Kirin 是端侧 AI 处理器，当前主要支持使用模拟器 Simulator 的开发方式，环境检查不要求服务器存在对应物理 NPU，以 Simulator 支持情况为准。

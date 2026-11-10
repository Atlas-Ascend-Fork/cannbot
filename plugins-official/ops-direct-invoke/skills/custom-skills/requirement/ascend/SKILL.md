---
name: ops-direct-invoke-requirement
description: 集中对齐算子需求、conda/Python 与 CANN 环境及修改权限，形成跨重试复用的任务约定。也用于后续需求修订。
---

# Ascend 需求分析

按[需求对齐](references/intake.md)与[需求清单](references/requirement-checklist.md)完成用户会话中的需求分析。仓库规则由已选 `ops-direct-invoke-repo-guide` 提供。

Ascend 平台支持 AscendC 和 CANNBot-DSL；具体芯片与工具链支持由环境检查核对。Tensor API 当前作为 AscendC 实现路线，后续独立语言能力尚未提供。

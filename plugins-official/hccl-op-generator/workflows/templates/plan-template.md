---
schema_version: 1
artifact: PLAN
engine: "{AICPU|CCU}"
owner: hccl-architect
task_id: "{task_id}"
status: "{FROZEN|DESIGN_ISSUE|BLOCKED}"
source_identity: "{设计输入源码身份}"
artifact_revision: "{修订号}"
semantic_tbd_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# {算子类型} {算法名称} 实施计划

> 本计划分配产物和依赖，不复制 Skill 技术步骤。AICPU 状态流转以 `aicpu-multi-agent-workflow.md` 为准；CCU 以兼容工作流为准。

## 1. 工作流绑定

| 字段 | 值 |
|---|---|
| 引擎 | {AICPU/CCU} |
| 流程真源 | |
| 设计 revision/SHA-256 | |
| 测试计划 revision/SHA-256 | |
| 当前源码身份 | |

## 2. 变更文件计划

| 序号 | 层级/模块 | 文件 | 动作 | 唯一写入 owner | 输入设计条目 | 完成证据 |
|---:|---|---|---|---|---|---|
| | | | {新增/修改/删除} | hccl-developer | | |

## 3. 阶段与依赖

| 序号 | 角色 | 输入状态/产物 | 角色输出 | 客观门禁 | 失败返回 |
|---:|---|---|---|---|---|
| | | | | | |

AICPU 必须保留 Architect、Verifier 基线、Developer、Reviewer、Verifier 候选五次角色调用；HCCLBot 是状态 owner，不代替角色工作。CCU 按原兼容顺序填写。

## 4. 检查计划

| 检查 | 执行 owner | 输入 | 结果产物 | 不替代的门禁 |
|---|---|---|---|---|
| 设计期静态检查 | hccl-architect | | | Review/Checker |
| 开发期静态检查 | hccl-developer | | `LOG.md` | 完整构建/Checker |
| 独立检视 | hccl-reviewer | | `REVIEW.md` | Checker |
| 基线/构建/功能验证 | hccl-verifier | | `BASELINE_REPORT.md`/`TEST_REPORT.md` | HCCLBot 最终状态判定 |

## 5. 共享环境与串行约束

| 资源 | 唯一 owner | 冻结输入 | 清理/交接要求 |
|---|---|---|---|
| 构建目录、CANN 安装、Checker、配置、共享内存 | hccl-verifier | | |

## 6. 风险与停止条件

| 风险 | 触发证据 | 返回角色/状态 | 不允许的扩大行为 |
|---|---|---|---|
| | | | |

## 7. 冻结记录

| 冻结时间 | 内容 SHA-256 | Architect 结论 |
|---|---|---|
| | | {PASS/DESIGN_ISSUE/BLOCKED} |

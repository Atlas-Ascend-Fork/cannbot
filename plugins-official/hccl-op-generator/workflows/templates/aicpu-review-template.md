---
schema_version: 1
artifact: REVIEW
engine: AICPU
owner: hccl-reviewer
task_id: "{task_id}"
status: "{PASS|REVIEW_FAIL|BLOCKED}"
source_identity: "{待审候选源码身份}"
task_spec_sha256: "{TASK_SPEC.md SHA-256}"
dataflow_index_sha256: "{DATAFLOW_SPEC.md SHA-256}"
design_sha256: "{DESIGN.md SHA-256}"
plan_sha256: "{PLAN.md SHA-256}"
test_plan_sha256: "{TEST_PLAN.md SHA-256}"
baseline_sha256: "{BASELINE_REPORT.md SHA-256}"
round: "{round}"
blocking_issue_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# AICPU 独立检视报告

## 1. 输入绑定

| 输入 | revision/SHA-256 | 路径 | 与待审身份一致 |
|---|---|---|---|
| 原始需求/`TASK_SPEC.md` | | | |
| `DATAFLOW_SPEC.md` 及实际 specs | | | |
| `DESIGN.md` / `PLAN.md` | | | |
| `TEST_PLAN.md` / `BASELINE_REPORT.md` | | | |
| Developer 变更清单/静态证据 | | | |

## 2. 审查范围

| 文件/模块 | 审查函数或区域 | 改动类型 | 独立读取证据 |
|---|---|---|---|
| | | | |

## 3. 契约检查

| 检查域 | 结论 | 证据位置 | 未确认项 |
|---|---|---|---|
| 需求与默认选路批准范围 | | | |
| Dataflow/offset/length/repeat/stride/scratch | | | |
| thread/notify/channel/资源消费者 | | | |
| 注册名/Selector/TopoMatch/跨层一致性 | | | |
| host/device CMake 接线 | | | |
| 架构边界、错误处理和编码规范 | | | |
| 源码与输入产物身份 | | | |

## 4. 独立静态检查

| 命令 | 退出码 | 报告路径 | 结论边界 |
|---|---:|---|---|
| | | | {不替代完整构建/Checker} |

## 5. 问题清单

| ID | 级别 | 文件/函数/日志证据 | 可触发反例 | 影响范围 | 必须修复项 | 重跑范围 |
|---|---|---|---|---|---|---|
| | {BLOCKER/MAJOR/MINOR/NOTE} | | | | | |

## 6. 身份与失效

| 字段 | 值 |
|---|---|
| 待审源码身份 | |
| 可恢复快照/差异路径 | |
| 报告内容 SHA-256 | |
| 源码变化后是否失效 | 是 |

## 7. 结论

- Reviewer 结论：`{PASS|REVIEW_FAIL|BLOCKED}`
- 阻塞问题数：
- 非阻塞 notes：
- 需要 Developer 修复的最小范围：

只有当前源码身份没有阻塞问题时才可写 `PASS`；本报告不声明构建或 Checker 通过。

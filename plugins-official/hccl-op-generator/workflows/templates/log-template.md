---
schema_version: 1
artifact: DEVELOPMENT_LOG
engine: "{AICPU|CCU}"
owner: hccl-developer
task_id: "{task_id}"
status: "{PASS|DESIGN_ISSUE|BLOCKED}"
input_source_identity: "{实现前源码身份}"
output_source_identity: "{实现后源码身份}"
task_spec_sha256: "{TASK_SPEC.md SHA-256}"
dataflow_index_sha256: "{DATAFLOW_SPEC.md SHA-256}"
design_sha256: "{DESIGN.md SHA-256}"
plan_sha256: "{PLAN.md SHA-256}"
baseline_sha256: "{BASELINE_REPORT.md SHA-256}"
round: "{round}"
static_failure_count: "{非负整数}"
updated_at: "{ISO-8601 时间}"
---

# {算子类型} {算法名称} 开发日志

> 本文件只记录 Developer 的源码/CMake 修改和开发期静态证据。基线、候选全量构建、安装与 Checker 由 Verifier 报告，不能在这里补写 PASS。

## Round {round}

### 1. 输入绑定

| 输入 | revision/SHA-256 | 路径 | 核对结果 |
|---|---|---|---|
| `TASK_SPEC.md` | | | |
| `DATAFLOW_SPEC.md`/实际 specs | | | |
| `DESIGN.md`/`PLAN.md` | | | |
| `BASELINE_REPORT.md` | | | |
| 失败报告（修复轮） | | | |

### 2. 变更记录

| 序号 | 文件 | 动作 | 对应设计/问题 ID | 修改摘要 |
|---:|---|---|---|---|
| | | {新增/修改/删除} | | |

### 3. 开发期静态检查

| 命令/检查 | 退出码 | 原始输出路径 | 结论 | 边界 |
|---|---:|---|---|---|
| | | | {PASS/FAIL/SKIP} | {不替代完整构建/Checker} |

### 4. 关键实现决策

| 决策 | 冻结设计值 | 实际实现 | 真实源码/Skill 依据 | 是否偏离 |
|---|---|---|---|---|
| | | | | |

### 5. 问题与处理

| ID | 现象/证据 | 根因状态 | 本轮处理 | 剩余影响 |
|---|---|---|---|---|
| | | {已证实/待证实} | | |

### 6. 输出身份与失效

| 字段 | 值 |
|---|---|
| 输入源码身份 | |
| 输出源码身份 | |
| 可恢复快照/差异路径 | |
| 变更文件清单 SHA-256 | |
| 应失效的旧 Review/Test | |

### 7. Developer 结论

- 结论：`{PASS|DESIGN_ISSUE|BLOCKED}`
- 未解决项：
- 需要 Reviewer 重点核对：

后续轮次在文件末尾追加完整 Round，不覆盖旧身份和旧失败记录。

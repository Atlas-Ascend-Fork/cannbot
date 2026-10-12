---
schema_version: 1
artifact: HANDOFF_LOG
engine: AICPU
task_id: "{task_id}"
owner_policy: current_stage_agent
latest_sequence: "{序号}"
latest_owner: "{hccl-architect|hccl-developer|hccl-reviewer|hccl-verifier}"
latest_status: "{PASS|FAIL|DESIGN_ISSUE|REVIEW_FAIL|TEST_FAIL|BLOCKED}"
latest_source_identity: "{本次输出源码身份}"
entry_count: "{正整数}"
updated_at: "{ISO-8601 时间}"
---

# AICPU 交接记录

> 本文件按调用顺序追加记录。当前阶段 Agent 只能更新顶部 `latest_*` 字段并追加自己的完整记录；已有记录不可覆盖、改写或补成 PASS。HCCLBot 只读取本文件并更新自己拥有的 `task-index.json`。

## HANDOFF-{序号} · {角色} · Round {round}

| 字段 | 值 |
|---|---|
| 调用/会话 ID | |
| 当前 Agent | {hccl-architect/hccl-developer/hccl-reviewer/hccl-verifier} |
| 输入状态 | |
| 建议输出状态 | |
| 开始/结束时间 | |
| 输入源码身份 | |
| 输出源码身份 | |
| 角色结论 | {PASS/FAIL/DESIGN_ISSUE/REVIEW_FAIL/TEST_FAIL/BLOCKED} |

### 输入产物

| 产物 | revision/SHA-256 | 路径 | 身份核对 |
|---|---|---|---|
| | | | |

### 输出产物

| 产物 | revision/SHA-256 | 路径 | 唯一 owner |
|---|---|---|---|
| | | | |

### 检查与证据

| 检查/动作 | 结果/退出码 | 原始证据路径 | 未验证边界 |
|---|---|---|---|
| | | | |

### 失效、阻塞与下一步

- 使以下旧状态/报告失效：{无或明确列表}
- 未确认项：
- 阻塞证据：
- 建议下一角色：{角色或 HCCLBot}
- 建议下一状态：{仅建议，由 HCCLBot 裁决}

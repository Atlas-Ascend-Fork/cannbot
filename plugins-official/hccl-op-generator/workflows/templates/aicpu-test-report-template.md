---
schema_version: 1
artifact: TEST_REPORT
engine: AICPU
owner: hccl-verifier
task_id: "{task_id}"
status: "{PASS|TEST_FAIL|BLOCKED}"
source_identity: "{已测试候选源码身份}"
review_source_identity: "{REVIEW.md 绑定的源码身份}"
baseline_sha256: "{BASELINE_REPORT.md SHA-256}"
review_sha256: "{REVIEW.md SHA-256}"
test_plan_sha256: "{TEST_PLAN.md SHA-256}"
round: "{round}"
build_pass: "{true|false}"
track_a_pass: "{true|false}"
track_b_pass: "{true|false}"
identity_match: "{true|false}"
environment_clean: "{true|false}"
test_failure_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# AICPU 候选构建与双轨测试报告

## 1. 输入门禁

| 输入 | 状态 | revision/SHA-256 | 身份核对 | 路径 |
|---|---|---|---|---|
| `BASELINE_REPORT.md` | | | | |
| `REVIEW.md` | PASS | | {与候选源码一致/不一致} | |
| `TEST_PLAN.md` | FROZEN | | | |

## 2. 候选构建与归档

| 字段 | 值 |
|---|---|
| 构建命令与唯一 run-id | |
| CANN/工具链身份 | |
| 真实退出码 | |
| 完整日志路径 | |
| 源码快照路径与 SHA-256 | |
| 候选包路径与 SHA-256 | |
| host/device 库哈希 | |

## 3. 安装与环境身份

| 安装包哈希 | 安装命令/退出码 | Checker/集群/rootinfo | 部署后库哈希 |
|---|---|---|---|
| | | | |

## 4. 轨道 A：候选算法定向

| case-id | 实际配置 | `--expect-algo` | observed algorithms/counts | Checker | 原始日志 |
|---|---|---|---|---|---|
| | | | | {PASS/FAIL} | |

## 5. 轨道 B：默认路径回归

| case-id | 实际配置 | baseline algorithms/counts | regression algorithms/counts | Checker | 选路判定 | 原始日志 |
|---|---|---|---|---|---|---|
| | | | | {PASS/FAIL} | {一致/符合批准矩阵/越界} | |

## 6. 选路验收

| 字段 | 值 |
|---|---|
| 模式 | {不变/按批准范围改变} |
| `evidence.py compare` | {PASS/FAIL/不适用} |
| baseline/regression `check --require-pass` | |
| 人工矩阵报告 | {批准改变时必填} |
| 范围外变化 | {无/列出 case-id} |

## 7. 额外授权测试

| 测试 | 是否执行 | 结果 | 证据 | 与双轨关系 |
|---|---|---|---|---|
| HCCL ST/UT | | | | 仅单列，不替代 Checker |

## 8. 失败与复跑证据

| run/case-id | 首次结果 | 复跑理由与唯一变量 | 复跑结果 | 两份原始证据 |
|---|---|---|---|---|
| | | | | |

## 9. 环境清理

| 配置覆盖恢复 | 后台进程 | 共享内存/临时资源 | 最终状态 |
|---|---|---|---|
| | | | {CLEAN/BLOCKED} |

## 10. 结论

- Verifier 结论：`{PASS|TEST_FAIL|BLOCKED}`
- 构建：
- 轨道 A：
- 轨道 B：
- 未验证范围/阻塞：

只有唯一完整构建、轨道 A、轨道 B、选路契约、身份核对和环境清理全部满足时才可写 `PASS`。该结论不代替 Reviewer 或 HCCLBot 的最终状态判定。

---
schema_version: 1
artifact: BASELINE_REPORT
engine: AICPU
owner: hccl-verifier
task_id: "{task_id}"
status: "{PASS|FAIL|BLOCKED}"
source_identity: "{旧包对应源码身份或不可恢复说明}"
task_spec_sha256: "{TASK_SPEC.md SHA-256}"
design_sha256: "{DESIGN.md SHA-256}"
test_plan_sha256: "{TEST_PLAN.md SHA-256}"
round: "{round}"
evidence_complete: "{true|false}"
unresolved_failure_count: "{非负整数}"
install_test_ready: "{true|false}"
created_at: "{ISO-8601 时间}"
---

# AICPU 基线报告

## 1. 输入绑定

| 输入 | revision/SHA-256 | 路径 | 核对结果 |
|---|---|---|---|
| `TASK_SPEC.md` | | | |
| `DESIGN.md` | | | |
| `TEST_PLAN.md` | | | |

## 2. 旧包与源码身份

| 字段 | 值 |
|---|---|
| 包路径与 SHA-256 | |
| host/device 库哈希 | |
| 包来源与构建记录 | |
| 源码 commit/快照 | |
| 可恢复性 | {可恢复/不可恢复及原因} |
| CANN/工具链身份 | |

## 3. 测试环境身份

| Checker/测试二进制 | 集群配置/rootinfo | iterations/warmup/runner | 环境覆盖 |
|---|---|---|---|
| | | | |

## 4. 基线结果

| case-id | 实际配置 | observed algorithms/counts | Checker | 原始日志 | 证据完整性 |
|---|---|---|---|---|---|
| | | | {PASS/FAIL} | | {完整/缺失} |

## 5. 恢复与补测记录

| 动作 | 目的 | 输入包哈希 | 结果 | 原始证据 |
|---|---|---|---|---|
| | | | | |

## 6. 完整性判定

| 检查 | 结果 | 证据 |
|---|---|---|
| 旧包已移出构建清理目录 | | |
| 矩阵与冻结 `TEST_PLAN.md` 一致 | | |
| 每例含算法名、次数和原始日志 | | |
| `evidence.py check --require-role baseline` | | |
| 未解释的基线 FAIL | | |
| 候选安装测试就绪 | | `repair.py ready` 输出或不就绪原因 |

## 7. 结论与缺口

- Verifier 结论：`{PASS|FAIL|BLOCKED}`
- 已验证范围：
- 缺失/失败证据：
- 禁止回填说明：{确认未用候选包或候选结果覆盖旧基线}

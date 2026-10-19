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
estimate_status: "{SUCCESS|FAILED|NOT_RUN}"
estimate_source_identity: "{估算候选源码身份，未执行写无}"
estimate_comm_domain: "{实际估算通信域，默认112，未执行写无}"
estimate_evidence_path: "{外部证据目录中的estimate.json绝对路径，未执行写无}"
estimate_evidence_sha256: "{estimate.json SHA-256，未执行写无}"
created_at: "{ISO-8601 时间}"
---

# AICPU 候选构建与双轨测试报告

## 1. 输入门禁

| 输入 | 状态 | revision/SHA-256 | 身份核对 | 路径 |
|---|---|---|---|---|
| `BASELINE_REPORT.md` | | | | |
| `REVIEW.md` | PASS | | {与候选源码一致/不一致} | |
| `TEST_PLAN.md` | FROZEN | | | |

## 2. 候选构建部署与归档

仅修改 HCCL 时使用 HVM `build_pkg.sh --install hccl`，由该命令完成构建、安装和 device 库部署。`build_pass=true` 要求整个统一入口成功，不能只依据内部编译成功。

| 字段 | 值 |
|---|---|
| 统一构建部署命令与唯一 run-id | |
| HVM 工作目录、build_pkg.sh 路径与 SHA-256 | |
| HCCL_CODE_HOME / HCOMM_CODE_HOME / HCCL_VM_PATH | |
| CANN/工具链身份 | |
| 真实退出码 | |
| 完整日志路径 | |
| 源码快照路径与 SHA-256 | |
| 候选包路径与 SHA-256 | |
| host/device 库哈希 | |

## 3. 安装与环境身份

安装步骤已包含在统一入口中，记录其日志证据；无需为填写此表重复安装。

| 本次安装包哈希 | 安装/设备部署日志与退出码 | Checker/集群/rootinfo | 部署后 host/device 路径与哈希 |
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

## 8. 算法性能估算

功能验证通过后必须按 `hccl-test-tool-hvm/references/estimate.md` 执行。默认 112；用户指定组网时按需求修改 `mock-comm` 并记录依据。参数与 `estimate.json` 格式以该参考为准。

| 字段 | 值 |
|---|---|
| 估算状态与失败/未执行原因 | |
| 算子、预期/实际算法注册名及命中证据 | |
| 候选源码身份、包路径/SHA-256、部署库身份 | |
| 集群配置路径/SHA-256、通信域与拓扑、用户需求依据 | |
| dtype、归约操作（适用时）、固定 1G 数据量 | |
| 完整命令与各步骤真实退出码 | |
| makespan/任务执行耗时（us） | |
| stream 完成时间、任务数、网卡统计及主要观察 | |
| 插件提示与估算适用范围/限制 | |
| estimate.json、测试/插件日志、profiling/trace 路径与 SHA-256 | |

只报告该条件下的仿真估算；“软件运行耗时”不作为算法耗时，无可比性能基线时不报告改善比例。`SUCCESS` 表示估算执行成功，不表示性能收益 PASS。

## 9. 失败与复跑证据

| run/case-id | 首次结果 | 复跑理由与唯一变量 | 复跑结果 | 两份原始证据 |
|---|---|---|---|---|
| | | | | |

## 10. 环境清理

| 配置覆盖恢复 | 后台进程 | 共享内存/临时资源 | 最终状态 |
|---|---|---|---|
| | | | {CLEAN/BLOCKED} |

## 11. 结论

- Verifier 结论：`{PASS|TEST_FAIL|BLOCKED}`
- 构建：
- 轨道 A：
- 轨道 B：
- 性能估算：
- 未验证范围/阻塞：

只有唯一完整构建、轨道 A、轨道 B、选路契约、身份核对、同身份目标算法 estimate 成功及原始证据完整、环境清理全部满足时才可写 `PASS`。估算阻塞时保留功能验证结果，返回 `BLOCKED` 并报告原因。该结论不代替 Reviewer 或 HCCLBot 的最终状态判定。

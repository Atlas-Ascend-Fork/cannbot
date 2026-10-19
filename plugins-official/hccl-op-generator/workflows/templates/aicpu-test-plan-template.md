---
schema_version: 1
artifact: TEST_PLAN
engine: AICPU
owner: hccl-architect
task_id: "{task_id}"
status: "{FROZEN|DESIGN_ISSUE|BLOCKED}"
source_identity: "{设计输入源码身份}"
artifact_revision: "{修订号}"
semantic_tbd_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# AICPU 测试计划

> 本计划必须在观察候选结果前冻结。基线与轨道 B 使用同一矩阵；轨道 A 在对应用例上增加强制算法与命中断言。

## 1. 验收输入

| 字段 | 值 | 依据 |
|---|---|---|
| 算子/算法 | {op_type}/{algo_name} | |
| 改动层级 | | |
| 默认选路模式 | {不变/按批准范围改变} | |
| 批准来源 | {不变时写“不适用”} | |
| 允许变化范围 | | |
| 期望注册全名 | | |
| `HCCL_ALGO` 配置 | {经目标源码核验的值} | |

## 2. 身份与环境要求

| 项 | 必须一致/记录的字段 |
|---|---|
| 源码 | 仓、分支、HEAD、未提交差异或可恢复快照 |
| 构建 | CANN 来源、工具链、命令、日志、退出码、包哈希 |
| Checker | 版本、测试二进制、集群配置、rootinfo、iterations、warmup、runner |
| 用例 | dtype、size、通信域、环境覆盖、期望算法及调用次数 |

## 3. 冻结矩阵

| case-id | 目的 | topology/rank | comm-domain | dtype | size/边界 | 基线期望算法/次数 | 轨道 A 期望算法/次数 | 轨道 B 期望算法/次数 | 特殊覆盖 |
|---|---|---:|---:|---|---|---|---|---|---|
| | | | | | | | | | {64bit/PROD/multi-loop/repeat/inplace 等} |

### 3.1 白盒路径映射（适用时）

按 `hccl-aicpu-whitebox-design` 从本次改动的可达源码分支推导；无适用分支时填写 `NOT_REQUIRED` 和源码依据。此表复用上面的 case-id，不增加未经批准的测试目标。

| case-id | 源码位置/分支条件 | 独立预期/反例 | 工具与原始证据 | 未覆盖原因 |
|---|---|---|---|---|
| | | | | |

## 4. 回归范围

| 受影响对象 | 最低回归范围 | 相邻/公共影响 | 依据 |
|---|---|---|---|
| | | | |

## 5. 轨道判据

- 基线：可信旧包、默认路径、不设置 `HCCL_ALGO`，逐用例保存算法名、调用次数、Checker 和原始日志。
- 轨道 A：使用已核验配置强制候选算法并以 `--expect-algo` 断言；Checker PASS 且失败数为 0。
- 轨道 B：不设置 `HCCL_ALGO`，与基线同矩阵；默认不变时执行 `evidence.py compare`，批准改变时按冻结矩阵人工核对。
- multi-loop 和 template `repeatNum > 1` 分别覆盖，并用源码公式与日志证明实际触发。

### 5.1 功能验证后的性能估算

候选双轨通过后，Verifier 必须按 `hccl-test-tool-hvm/references/estimate.md` 执行 estimate，写入 `TEST_REPORT.md`。性能估算使用独立会话与证据，不改变上述冻结功能矩阵，也不要求基线阶段执行候选估算。

| 条件 | 计划值与依据 |
|---|---|
| 估算算子、目标注册名、显式选路配置 | |
| `mock-comm` 与拓扑 | 默认 112；用户指定时记录需求与实际参数 |
| 集群配置、dtype、归约操作（适用时） | |
| 固定参数 | `-np 1 -b 1G -e 1G -w 0 -n 1 -c 0` |

若所选组网不支持目标算法，记录限制；不得估算其他算法后记为目标结果。estimate 完成是必需输出，不设性能收益或耗时阈值。

## 6. 额外测试授权

| 测试 | 授权状态 | 范围 | 结果在何处单列 |
|---|---|---|---|
| HCCL ST/UT | {未授权/已授权} | | `TEST_REPORT.md` |

ST/UT 不替代 A/B 双轨 Checker。

## 7. 原始证据要求

| 证据类型 | 持久路径规则 | 必填身份/哈希 |
|---|---|---|
| 旧包与基线 | 源码仓和构建清理目录之外 | |
| 候选包/源码快照 | 源码仓和构建清理目录之外 | |
| Checker 批次日志 | baseline/regression 独立目录 | |

## 8. 冻结记录

| 字段 | 值 |
|---|---|
| 冻结时间 | |
| 内容 SHA-256 | |
| Architect 结论 | {PASS/DESIGN_ISSUE/BLOCKED} |

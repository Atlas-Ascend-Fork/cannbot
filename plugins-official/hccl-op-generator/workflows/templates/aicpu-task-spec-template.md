---
schema_version: 1
artifact: TASK_SPEC
engine: AICPU
owner: hccl-architect
task_id: "{task_id}"
status: "{FROZEN|DESIGN_ISSUE|BLOCKED}"
source_identity: "{设计输入源码身份}"
artifact_revision: "{修订号}"
semantic_tbd_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# AICPU 任务规格

> `FROZEN` 要求本文没有语义 TBD；无法由源码或 Skill 消解的需求缺口列入第 7 节，并使用 `DESIGN_ISSUE` 或 `BLOCKED`。

## 1. 需求来源

| 字段 | 值 |
|---|---|
| 原始需求 | {保留原意，不扩写授权} |
| 需求来源/位置 | {会话、Issue 或文档位置} |
| 算子 | {op_type} |
| 算法名称 | {algo_name} |
| 目标仓与分支 | {仓路径、具名分支、HEAD、工作区状态} |

## 2. 目标与非目标

### 目标

- {可客观验收的目标}

### 非目标

- {明确排除的范围；没有则写“无”}

## 3. 已确认输入

| 输入 | 取值 | 证据/来源 |
|---|---|---|
| 拓扑与 rank | | |
| 数据类型与数据量 | | |
| 改动层级 | {template/executor/selector/topoMatch} | |
| 默认选路影响 | {不变/按批准范围改变} | |
| 选路变更批准来源 | {不变时写“不适用”} | |
| 功能验收范围 | | |
| ST/UT 额外范围 | {未授权/已授权范围} | |

## 4. 支持与排除矩阵

| 场景 | topology | rank | dtype | size | 支持状态 | 依据 |
|---|---:|---:|---|---|---|---|
| | | | | | {支持/排除} | |

## 5. 能力路由

| 改动对象 | 是否涉及 | 技术 Skill/参考 | 真实源码依据 |
|---|---|---|---|
| 需求与 Dataflow 设计 | | `hccl-aicpu-design` | |
| Template 实现 | | `hccl-aicpu-best-practice` | |
| Executor/注册 | | `hccl-aicpu-best-practice` 与引擎跨层契约 | |
| Selector | | `hccl-aicpu-best-practice` 与引擎跨层契约 | |
| TopoMatch | | `hccl-aicpu-best-practice` 与引擎跨层契约 | |

Dataflow Spec 判定：`{REQUIRED|NOT_REQUIRED}`；依据：{模式 A/B/C 与判断理由}。

## 6. 验收契约

- 设计产物：`TASK_SPEC.md`、`DATAFLOW_SPEC.md`、`DESIGN.md`、`PLAN.md`、`TEST_PLAN.md` 均达到各自有效状态。
- 实现产物：生产源码/CMake 与冻结设计一致，开发期静态证据完整。
- 独立检视：`REVIEW.md` 对候选源码身份给出 PASS。
- 功能验收：同一源码身份的唯一候选完整构建和 hccl-vm A/B 双轨满足父 Skill 客观判据。
- 默认选路：{不变时与基线一致；批准改变时按预先冻结矩阵验收}。

## 7. 上游输入缺口

| ID | 缺口 | 为什么不能由技术证据推导 | 影响范围 | 所需输入 owner |
|---|---|---|---|---|
| | | | | {HCCLBot/用户/外部系统} |

`status=FROZEN` 时本节必须为空或明确写“无”。

## 8. 冻结记录

| 字段 | 值 |
|---|---|
| 冻结时间 | |
| 冻结 revision | |
| 内容 SHA-256 | |
| Architect 结论 | {PASS/DESIGN_ISSUE/BLOCKED} |

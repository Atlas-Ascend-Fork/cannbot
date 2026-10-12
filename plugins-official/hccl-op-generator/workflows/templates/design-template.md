---
schema_version: 1
artifact: DESIGN
engine: "{AICPU|CCU}"
owner: hccl-architect
task_id: "{task_id}"
status: "{FROZEN|DESIGN_ISSUE|BLOCKED}"
source_identity: "{设计输入源码身份}"
artifact_revision: "{修订号}"
semantic_tbd_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# {算子类型} {算法名称} 技术设计

> 技术细节以对应引擎 Skill 和目标版本真实源码为准。本模板记录本任务的决策和证据，不复制通用 API、宏、目录或验证流程。

## 1. 输入绑定

| 输入 | revision/SHA-256 | 路径/来源 |
|---|---|---|
| 原始需求/任务规格 | | |
| Dataflow Spec 索引 | | {AICPU；不适用时写明} |
| 目标仓源码身份 | | |
| 引擎技术 Skill | | |

## 2. 设计目标与约束

| 维度 | 取值 | 来源/证据 |
|---|---|---|
| 算子/算法 | {op_type}/{algo_name} | |
| 引擎 | {AICPU/CCU} | |
| 拓扑/rank | | |
| dtype/size | | |
| 默认选路影响 | | |
| 支持/排除范围 | | |

## 3. 分层设计决策

只填写实际涉及的层级；不涉及项写“不涉及”并说明源码依据。

| 层级/对象 | 复用或新增 | 设计决策 | 接口/身份约束 | 真实源码证据 |
|---|---|---|---|---|
| Template/Kernel | | | | |
| Executor | | | | |
| Selector | | | | |
| TopoMatch | | | | |
| 公共层/注册映射 | | | | |

## 4. 数据流与资源接口

| 契约 | 设计值 | 生产者/消费者 | 核对方法 | 证据 |
|---|---|---|---|---|
| Dataflow Spec | | | | |
| slice/repeat/stride | | | | |
| scratch/buffer | | | | |
| thread/notify/channel | | | | |
| 注册名/selector 名称 | | | | |

## 5. 文件影响

| 文件 | 动作 | 设计原因 | Developer 写入范围 | 关联检查 |
|---|---|---|---|---|
| | {新增/修改/不变} | | | |

## 6. 测试接口

| 项 | 设计输出 |
|---|---|
| 测试计划路径/revision | |
| 必须命中的算法身份 | |
| 默认选路模式与批准范围 | |
| 特殊边界 | |
| 未纳入验收的非目标 | |

具体构建、基线和测试矩阵只在对应 Skill、`TEST_PLAN.md` 与验证报告中维护。

## 7. 风险与未确认项

| ID | 风险/缺口 | 影响 | 消解证据 | owner |
|---|---|---|---|---|
| | | | | |

`status=FROZEN` 时不得遗留会改变实现语义或验收范围的 TBD。

## 8. 冻结记录

| 冻结时间 | 内容 SHA-256 | Architect 结论 |
|---|---|---|
| | | {PASS/DESIGN_ISSUE/BLOCKED} |

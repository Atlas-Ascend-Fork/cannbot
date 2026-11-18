---
schema_version: 1
artifact: DESIGN
engine: CCU
hcomm_source_identity: "{与 task-index.json 相同的 HCOMM 身份}"
ccu_mode: "{CCU_SCHED|CCU_MS}"
source_report_file: "source-report.json"
source_report_sha256: "{source-report.json SHA-256}"
launch_contract_sha256: "{launch-contract.json SHA-256}"
sync_contract_sha256: "{sync-contract.json SHA-256}"
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

首次来源报告用 `source-report.json`；重新设计选择全新 `source-report-r<正整数修订号>.json`，更新 `source_report_file` 和 `source_report_sha256`，旧文件保留作历史证据。历史任务省略文件名时仍读取 `source-report.json`。

采用重新核验的知识基线时，由 Architect 在任务目录保存 `knowledge-baseline.json`，在本头部增加可选 `knowledge_baseline_sha256`（实际文件 SHA-256），并在输入绑定中记录变更范围、源码身份和逐项核验依据。来源报告与同步/算术检查均使用这一份基线；Reviewer 独立复核。省略此附件和字段时沿用 Skill 自带基线。来源报告、基线变化后均需按重绑定工作单重新核验下游报告。

## 1. 输入绑定

| 输入 | revision/SHA-256 | 路径/来源 |
|---|---|---|
| 原始需求/任务规格 | | |
| Dataflow Spec 索引 | | {不适用时写明} |
| 目标仓源码身份 | | |
| 引擎技术 Skill | | |

## 2. 设计目标与约束

| 维度 | 取值 | 来源/证据 |
|---|---|---|
| 算子/算法 | {op_type}/{algo_name} | |
| 引擎 | CCU | |
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

## 9. CCU 设计附件

- `source-report.json`：运行 `hccl-ccu-best-practice/scripts/inspect_sources.py` 的原始输出；记录 HCCL/HCOMM 来源、漂移核对结论及 Skill 路径/版本。
- `launch-contract.json`：依据 Skill 示例填写所有参与 kernel 的启动槽、LoadArg、缓存与更新声明，并通过 `check_launch_contract.py`。未使用 FastLaunch 时必须写明原因。
- `sync-contract.json`：每个接收 channel 表/去重边界的 XN 与 Notify slot/mask、同时存活 epoch、复用证明及源码依据；用目标 HCOMM 执行 `check_sync_contract.py`，按实现实际分配配额判定。
- 三个附件由 Architect 冻结，SHA-256 写入本文件头。修改附件必须重新冻结设计并使下游证据失效。
- 按 Skill 的 `assets/dataflow-spec-template.md` 在每template的spec维护数据流、地址、资源和同步证明；本文件引用spec与JSON，不复写完整参数表/数据流/测试矩阵。逐项关联真实源码，声明检查通过不代表 C++ 或通信语义正确。

## 10. 接入知识与差异记录

| 已用卡及适用分支 | 校验输出/内容哈希 | 直接复用结论 | 补查变化/新依赖与证据 | 剩余缺口 |
|---|---|---|---|---|
| | | | | |

后续角色消费同一份记录，来源未变只复核本次算法关键结论与增量，不重复写架构调查。


## 11. 运行期算术能力核验（冻结必填）

目标生成器、证据路径/哈希与当前部署适用性：

| compute_ops条目/实际源码位置 | 可翻译性与目标支持范围依据 | 不支持时的替代方案与边界证明 |
|---|---|---|
| | | |

完整表达式→rep映射维护在sync-contract.json.compute_ops，此处按条目引用并记录核验依据；使用check_contracts.py或独立check_arith_ops.py检查。未知目标采用交集；没有运行期算术也说明理由；API存在性/编译通过不代表可翻译。已完成任务的旧假设由Skill勘误，不回头改写完成链。

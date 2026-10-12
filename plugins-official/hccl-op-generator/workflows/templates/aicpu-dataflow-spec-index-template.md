---
schema_version: 1
artifact: DATAFLOW_SPEC_INDEX
engine: AICPU
owner: hccl-architect
task_id: "{task_id}"
status: "{PASS|NOT_REQUIRED|DESIGN_ISSUE|BLOCKED}"
source_identity: "{设计输入源码身份}"
artifact_revision: "{修订号}"
applicability: "{REQUIRED|NOT_REQUIRED}"
spec_count: "{非负整数}"
passed_spec_count: "{非负整数}"
semantic_tbd_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# AICPU Dataflow Spec 索引

> 本文件只记录适用性和实际 Dataflow Spec 的身份，不复制数据流技术正文。每个 template 对应一份按 `hccl-aicpu-design/dataflow-spec-template.md` 形成的独立 spec，建议放在 `{task_dir}/dataflow/`。

## 1. 适用性判定

| 字段 | 值 |
|---|---|
| 能力模式 | {A/B/C} |
| 是否改变 slice/scratch/同步点/收发模式 | {是/否} |
| 结论 | {REQUIRED/NOT_REQUIRED} |
| 真实源码与 Skill 依据 | |

`NOT_REQUIRED` 必须有依据且 `status=NOT_REQUIRED`；模式 C 必须为 `REQUIRED`，并在第 2 节至少登记一份通过检查的 spec。

## 2. Spec 清单

| spec-id | Template 类/文件 | Spec 路径 | `check_spec` | `check_layout` | 语义 TBD | SHA-256 |
|---|---|---|---|---|---:|---|
| | | `{task_dir}/dataflow/<template>.md` | {PASS/FAIL} | {PASS/FAIL} | {0} | |

## 3. 跨 Spec 关系

| 组合层级/兄弟 Template | 输入输出衔接 | 共享资源或同步约束 | 证据 |
|---|---|---|---|
| | | | |

## 4. 检查证据

| 命令 | 退出码 | 报告/原始输出路径 | 执行时源码身份 |
|---|---:|---|---|
| | | | |

## 5. 未解决项

| ID | 类型 | 问题 | 所需证据/上游输入 | 影响 |
|---|---|---|---|---|
| | {技术 TBD/需求缺口} | | | |

`status=PASS` 时语义 TBD 必须为 0；`status=NOT_REQUIRED` 时不允许伪造空 spec 为 PASS。

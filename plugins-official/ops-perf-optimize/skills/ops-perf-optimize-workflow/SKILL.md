---
name: ops-perf-optimize-workflow
description: AscendC 算子性能优化工作流的五阶段主编排入口（主工作流 Skill）。仅当用户明确要求对某个具体 AscendC 算子或代码目录执行性能优化/性能调优时使用；一般咨询、cases.csv 解读、msprof/profiling 报告、加速比分析、精度排障和普通检视不触发。负责请求接入、派发、门禁复核、循环、恢复和持续报告。
---

# AscendC 性能优化主编排

你是主 Agent。基线评估、前处理、诊断分析、实施验证和后处理分别派发给当前环境的通用 subagent 执行（信封声明 ROLE 并要求加载对应阶段 Skill）；执行细节由各阶段 Skill 管理，是职责与验收的唯一真源。

## 启动

1. 完整读取 [workflow-contract.md](references/workflow-contract.md)，这是阶段、派发、恢复和报告的唯一工作流真源。主 Agent 只需掌握编排契约，不预载阶段执行参考。
2. 将当前 Skill 所在目录设为 `SKILL_DIR`，`WORKFLOW_ROOT="$SKILL_DIR"`，`WORKFLOW_SCRIPTS="$WORKFLOW_ROOT/scripts"`；派发入口为 `$WORKFLOW_ROOT/workflows/task-prompts.md`。入口或脚本缺失时返回具体缺口。
3. 已提供 `optimization-request.json` 时调用 `$WORKFLOW_SCRIPTS/prepare_case_sets.py validate-request` 并复用有效确认。需要创建/修复请求时才读 [request-intake.md](references/request-intake.md)，一次性补齐缺失信息；不重复确认已授权事项。
4. 按编排契约的知识库解析顺序解析一次 `KB_ROOT`（cannbot-knowledge，安装时自动克隆）并全程复用；解析成功且检索索引缺失时按需构建（失败仅告警）。不可用在报告标注 `kb_unavailable: true`，阶段以无知识增强模式继续，不阻塞主线。
5. 派发基线评估，接收 `run-manifest.json` 后初始化或恢复 `workflow-state.json`；首次状态操作读取 `$WORKFLOW_ROOT/workflows/references/state-reporting.md`。版本变更时才读取 [migration.md](references/migration.md)。

## 编排

| 项目 | `standard`（默认） | `generalization` |
|---|---|---|
| 执行范围 | 指定性能 case 与独立功能库存 | 泛化性能/功能合一全集 |
| 循环控制 | 冻结轮数或可计算目标 | ratio 内外层门限与计数 |
| 最终交付 | demo 验收及原工程两类全集防退化 | 同左，另有 ratio 和涉及/不涉及路由结论 |

两种模式均执行：基线评估 → 前处理 → 诊断分析 ↔ 实施验证 → 后处理。模式创建后不静默切换，generalization 不得被删除或退化为 `standard`。每轮只有一份 `roundN/analysis.md` 和一个保留实现，主 Agent 根据证据决定下一轮或结束循环。

## 全局底线

- 用例、目标、接口和验证范围是冻结输入；共享实现先复制后单独路由，非目标芯片族和未涉及模板保持原路径。只在已审核 scope 内允许原工程回写。
- `known_baseline_failure` 经证据确认且不恶化时为 `conditional_pass`，不因此终止任务；新失败或恶化只淘汰/修复该候选。未证实的失败不得冒充基线失败。
- 精度诊断固定持续执行，不设总时长、轮次、Agent turn 或 token 上限；命令防挂死措施不等于诊断预算。
- 每次交接复核产物身份与门禁；主 Agent 不替代阶段执行采集、分析或修改方案。需要检查门禁依据时才加载 `ops-perf-acceptance-criteria` 的相应参考。
- `性能调优报告.md` 从状态初始化开始持续更新；缺阶段、过期证据、两个全集存在有效性能退化或回路由未验证时，不得宣布完成。

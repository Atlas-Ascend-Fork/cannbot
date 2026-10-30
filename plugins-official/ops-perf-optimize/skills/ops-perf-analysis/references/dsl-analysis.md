# DSL 诊断分析细则

本文件细化 `ops-perf-analysis` 的 DSL 方案评估与交付要求：净收益评估、调度契约展开与产物口径。共享验证与领域边界见 [cannbot-dsl.md](../../ops-perf-acceptance-criteria/references/cannbot-dsl.md)。

候选生成前必须完成方案净收益评估，逐方向/方案、逐 case × SoC 记录关键路径、新增成本、完整调用收益区间或 unknown、目标贡献、证据可信度与处置。融合多阶段、量化 MM 或讨论 MBU/小收益时，额外记录阶段流水、固定开销、理论空间与完整调用收益之间的关系。MC²、AscendC 静态性能检视和 AscendC API 文档检索不作为 DSL 参考输入。

启用 schedule_policy 时按 [调度契约](../../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 与 `ascendc-performance-review` 的 `references/async-schedule-templates.md` 完成 A1 独立程序恢复、A2 约束检查与 A3 候选；安全/同步关键未知先取证，纯性能收益 unknown 可进入合法候选实测。功能验证使用原 pytest/checker/golden。

## 分析产物

- 一份 `analysis/roundN/analysis.md`：逐 case 的 MBU/MFU/cost_bound/ceiling_us/headroom/verdict 与双 roofline（当前实现 + 算子内在最小成本）
- 本轮就绪方案的 `implementation-contract-<scheme_id>.json` 与 `source-isolation-<scheme_id>.json`（ready_for_implementation 才出契约）
- 调度契约启用时另交 `schedule-contract-<scheme_id>.json` 与 model `schedule-check-<scheme_id>.json`

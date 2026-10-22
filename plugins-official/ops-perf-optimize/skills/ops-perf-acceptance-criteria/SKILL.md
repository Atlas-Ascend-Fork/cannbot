---
name: ops-perf-acceptance-criteria
description: 性能优化阶段共用的验收判据：性能采集协议、精度判定、抖动/净收益效果判定、泛化 ratio 判定。只提供判定口径，不执行验证过程；用于阶段执行及门禁复核，按验证类型读取对应参考。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 性能任务共享验证

本 Skill 提供跨阶段一致的判定与取证口径，不负责编排阶段或制定优化方案。原始用例、golden、阈值和源码身份来自冻结 manifest；SDK、API 与设备事实必须取自可信文档或当前安装。

| 当前动作 | 只读取所需参考 |
|---|---|
| 采集/复用基线、小算子、候选或原工程性能 | [performance-collection.md](references/performance-collection.md)，实际采集加载 `ops-profiling`；MC² 加载 `ascendc-mc2-best-practice` |
| 基线/候选/原工程功能判定、定位新增失败 | [precision-policy.md](references/precision-policy.md)，TTK 操作加载 TTK 标准 skill（`ttk-how-run-test`/`ttk-how-diagnose`） |
| 比较性能、生成 effect 摘要、防止退化 | [performance-jitter-policy.md](references/performance-jitter-policy.md) |
| 泛化 ratio 计算与覆盖核验 | [ratio.md](references/ratio.md) |

修改范围安全契约与剥离/隔离验证用例不属于本 Skill，统一读取 `$PLUGIN_ROOT/workflows/references/source-isolation.md` 与 `validation-cases.md`。

不要默认读取整套参考。设备采集等待主 Agent 的排他调度；机器脚本位于信封传入的 `$PLUGIN_ROOT/scripts/`。数值/文件范围 gate 不替代源码路由审阅和真实构建/运行身份核验。

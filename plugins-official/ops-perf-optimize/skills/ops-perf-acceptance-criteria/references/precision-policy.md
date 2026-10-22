# 精度红线与判定

精度 FAIL 不是全局终止信号。先在未改动原始输入上，以同 case、seed、比较器、环境和构建身份复现：

| 对比结论 | 分类 | 工作流动作 |
|---|---|---|
| 原始实现同样失败，候选签名/误差不恶化 | `known_baseline_failure` | 候选 `conditional_pass`，继续 |
| 原始失败、候选改善或通过 | `improved_baseline_failure` | 继续 |
| 原始通过，候选失败；或原始失败但候选恶化 | `new_or_worsened_failure` | 修复或淘汰该候选；其他候选和当前基线继续 |
| 尚未得到可信对照 | `under_diagnosis` | 持续诊断，禁止冒充基线失败 |

`strict_pass` 要求全部 PASS。`conditional_pass` 要求全部原始 PASS case 仍 PASS、每个已证实基线失败不恶化、没有新失败。基线失败始终保留在后续集合中，不得删 case、放宽阈值或换 golden 来制造通过。

功能与精度故障定位统一使用 `ascendc-precision-debug`，由当前阶段代理执行，不得嵌套派发。每完成一个假设都用 `progress --kind diagnosis` 记录证据、排除项和下一步。

精度诊断没有自动停止预算，只在问题被解释并分类、候选被修复/淘汰或确有外部资源 blocker 时结束。任何候选失败都不得把已经可信的 baseline 或其他候选连带终止。

状态工具同时设置机械护栏：以 `known_baseline_failure` 或 `candidate_precision_regression` 作为 `finish --status failed|blocked` 的原因会被拒绝；前者应继续为 `conditional_pass`，后者应淘汰/修复对应候选后继续。

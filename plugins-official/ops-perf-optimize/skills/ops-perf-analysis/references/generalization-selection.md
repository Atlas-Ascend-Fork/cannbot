# 泛化调优子集选择

每轮从 `ratio < 1.0` 中确定性选择最多 30 条：优先 ratio 最低，同时覆盖 TilingKey/执行路径、dtype/attrs、shape 规模和边界。产出 `generalization-tuning-selection.json`，记录源 ratio SHA、选中 ID、覆盖标签和缺口。没有不达标 case 时跳过内层优化，直接进入全集验证。当前基线变化后必须重新计算 ratio 和选择，不能沿用旧候选的子集。

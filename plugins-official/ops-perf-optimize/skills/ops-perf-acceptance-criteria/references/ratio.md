# Ratio 计算与覆盖

逐 case 计算：

```text
ratio = gpu_total_us / npu_total_us
```

`ratio ≥ 1.0` 表示 NPU 不慢于竞品；`ratio ≥ 0.6` 表示 NPU 至少达到竞品 60%。每次计算产出 `ratio-analysis.json` 和 `ratio-analysis.md`，至少记录全部 case 的两侧耗时、ratio、geomean ratio、min ratio、匹配数量和 `ratio < 1.0` 数量。只要任一 case 缺失或身份不一致，本次 ratio 结论无效。


同一 ratio 计算口径供诊断选例、实施终选/全集验证和后处理复核共用；公式不因角色或阶段变化。

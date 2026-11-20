# 结果与参数

`OPPROF_*` 内可以有多个 kernel、设备和 launch 的子目录。按实际文件识别，避免用“最新目录”或首行替代目标选择。

| 产物 | 提取内容 |
|---|---|
| `OpBasicInfo.csv` | `Op Name`、`Op Type`、`Task Duration(us)`、设备、进程、频率、Block Dim；完整 MIX 耗时不由 AIC/AIV 流水时间相加得到 |
| `PipeUtilization.csv` | 各核流水耗时、占比；按核标识匹配 |
| `Memory*.csv`、`L2Cache.csv` | 数据方向、带宽、缓存命中；单位以实际表头为准 |
| `ArithmeticUtilization.csv`、`ResourceConflictRatio.csv` | 计算与冲突指标；缺字段、`NA` 保留为未知 |
| `trace.json`、`visualize_data.bin` | 对应工具版本的时间线或可视化原件 |

`inspect` 同时接受采集目录或一个 CSV，输出逐记录数据和文件 SHA。只有采集了相应指标才要求其产物；BasicInfo 计时不要求所有 CSV 齐全。多个记录的聚合方式由调用方确定。

当前官方文档的 `--set` 三档逐步增加分析内容，具体集合随平台和工具版本变化。不要手工把档位展开为指标并集：例如源码中的 950 `full` 使用 InstrTimeline，不能再机械加入与之互斥的 PipeTimeline。范围重放 `range` 与 `--set` 也互斥。

`--replay-mode=kernel` 的采集路径会尝试通过 scratch 数据搬运驱逐 L2；warmup 本身不逐次清 L2。清理失败或型号表缺失可能只告警后继续，因此应记录相关日志，不能仅凭参数宣称已验证全设备冷缓存。需要保留算子间缓存上下文时，由调用方选择 application/range 并单独记录口径。

依据：[官方用户指南](https://gitcode.com/Ascend/msopprof/blob/44c5b5b733d712aeef537669d9bf4231782a1755/docs/zh/user_guide/msopprof_user_guide.md)、[采集实现](https://gitcode.com/Ascend/msopcom/blob/002ae2823b417d50b9786f10b2fb104677626e24/csrc/runtime/inject_helpers/ProfDataCollect.cpp)。msopprof 二进制默认 warmup 为5；脚本与适配器显式传入 `--warm-up=3` 和默认的 `--replay-mode=kernel`。warmup 不适用于 application；PCSampling 等路径还有内部预热，不能把参数次数当成所有 replay 总数。

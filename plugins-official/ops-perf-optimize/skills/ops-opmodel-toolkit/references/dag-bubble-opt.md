# 空泡分析与优化

输入为一次运行的 `result.json`、完整 `trace.json`、统计表和对应用户模型。
目标是解释可观察的空闲时段，并用新的模型实验验证优化假设。

## 取得并核对输入

完整 case 的调用见[Python API](python-api.md)，使用 `export_trace=True`。
物理命令通过 `--trace` 请求时间线。以 `result.json:artifacts` 找到本次真实文件，
核对 case、硬件、成本、参数、核/阶段和时间范围。
trace 使用 cycle，普通 case 的 trace 可能只对应关键核，不能直接套完整 case 的总周期。

## 解读公开产物

在支持 trace-event JSON 的查看器中打开 trace，保留 pid/tid 或 engine 身份。
按用户要求记录目标管线、时间窗口、可见空闲区间和对应输入/输出事件，
对照模型的依赖、任务边界和容量声明提出待验证原因。
统计字段与范围见[结果分析](analysis.md)和[trace 接口](framework/runtime-and-trace.md)。

工具集不提供自行计算或归因的分析脚本。查看器未提供的指标标为未取得，
不将 CSV 的指令周期总和当作墙钟忙碌时间。等待轨不属于计算管线的服务量。

## 实验调用与交付

在模型副本中改变一项合法参数或用户声明的方案，以相同 case、硬件和成本运行新目录。
参数搜索调用见[优化指南](optimization.md)，结构方案实验见[DAG 寻优](agent-dag-opt.md)。
交付输入与 trace 身份、观察范围、证据位置、待确认原因、实验结果及未解释部分。

## 使用限制

时间戳相同、其他管线繁忙或 overlap 较低都不足以证明根因或双缓冲是否有效。
保留真实数学工作量、依赖、版本与容量要求，不能通过删约束缩短周期。
局部利用率提升不表示完整 case 更快；模型改善不自动表示设备收益。
详细报告口径见[空泡分析参考](dag-bubble-opt/pipe-gap-analysis.md)。

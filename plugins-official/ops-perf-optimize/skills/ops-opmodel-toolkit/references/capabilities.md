# OpModel 能力与限制

本表说明 OpModel 的调用入口与使用范围，具体模型、后端和字段组合以已安装包的接口为准。
软件合成示例不代表设备预测精度。

| 能力 | 安装后的入口 | 功能说明 |
| --- | --- | --- |
| 用户自定义 YAML 模型 | `opmodel <模型目录>`、`run_native_case` | Cube/Vector 模型、CLI 和 Python 入口、硬件及成本注入 |
| 原生模型 / Python hooks | 导出的 `operators/dag/matmul`，用户工作目录 | 分核与 DAG 搜索使用可编辑模型及 hooks |
| 公式生成 | `python -m accel_model.kernel.dag.gen` | 需要公式与 Cube 声明文件，输入要求见 [CLI 参考](cli.md) |
| buffer 复用分析 | `python -m accel_model.optimize.dag.reuse` | 入口保留；当前矩阵乘示例存在兼容问题，见下文 |
| 编译 / 校验 | `model.physical.compile_case`、声明式 gates | 容量、分配、区域、数量、运行时及错误拒绝 |
| 仿真 / 报告 | SimPy、Replay、原生/物理入口 | trace、周期、指令统计、Case/Pipe/Instruction CSV |
| 已注册模型 API | `accel_model.app.api` | CSA/HCA 查询、输入契约、结果 scope、显式产物 |
| 分核搜索 | `python -m accel_model.app.cli.split_run` | 多核候选排名及 SimPy 复核 |
| DAG 参数搜索 | `python -m accel_model.app.cli.dag_run` | 多候选、Replay、最优模型与 trace |
| 图搜索 | `python -m accel_model.app.cli.graph_search` | 动作发现、候选生成、图 checkpoint 与恢复 |
| 搜索会话 | `python -m accel_model.app.cli.agent_search` | 基线/候选评分、预算、排名、关闭及报告 |
| 数值校验 | 语义/执行校验接口 | 模型语义、数值执行和图搜索候选检查，具体支持域见模型说明 |
| 硬件 / 搬运分析 | 硬件 YAML、`gm_read` 等入口 | 资源导出、硬件 profile 与搬运参数分析 |

当前版本不提供可独立使用的完整 L2 地址级对拍。
上板测量、VF 真实性能证据和设备工具链也不由 wheel 直接提供。

如果 buffer 复用分析报 `AttributeError: 'tuple' object has no attribute 'name'`，
记录实际版本与输入，改用本例的公开运行产物分析。
完整 case 仿真、分核搜索和 DAG 参数搜索可按教程使用；结果分析采用周期统计和 trace。

用户资料包含[模型配置参考](model-reference.md)、[Python API](python-api.md)、
[CLI](cli.md)和[可编辑模型](../assets/examples/matmul/README.md)。
文档和示例随本 skill 统一交付，阅读顺序见[使用指南](index.md)。
安装后可以在用户目录中开发模型，通过发行包提供的接口运行仿真、分析和寻优。
仿真内核、模型执行和优化算法以二进制扩展交付。

按任务选择分核搜索、DAG 参数搜索、图搜索或搜索会话；具体参数见 [CLI](cli.md)
和[工具路由](joint-optimization/tool-routing.md)。调用前核对包版本和对应入口，
缺少入口或遇到不支持的配置时保留报错与最小输入，按[故障排查](troubleshooting.md)处理。

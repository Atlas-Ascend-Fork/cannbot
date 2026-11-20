---
name: ops-profiling-report
description: 编排一个或多个 profiling 子工具，统一测量方法、核对证据与口径，综合性能分析并提出算子设计和优化建议。
---

# 性能分析与报告

接收程序或已有报告，按 `profilers.json` 选择子工具。已有原件可直接用 [msprof CLI](tools/tool-msprof/scripts/msprof_tools.py) 或 [msopprof CLI](tools/tool-msopprof/scripts/msopprof_tools.py) 离线执行 `inspect`、`report`。

## 工具接入

选卡与资源分配由调用方负责。准备前继承其指定的可见设备环境和应用设备号，采集器、工具和应用沿用同一环境；不要求使用 `npu-smi`。

```bash
python "$REPORT_SKILL_DIR/scripts/report_contract.py" --prepare --application-device "$APPLICATION_DEVICE" --out "$PREPARATION_JSON"
```

读取返回的 `report_context.tool_skill`；多个工具返回 `bindings`，分别加载所选子工具。配置可接入一个或多个子工具，未配置的工具不加载。子工具可只提供指导，也可提供自动采样适配器，见[调用契约](references/caller-contract.md)。

`--application-device` 是应用可见编号；返回的设备字段由运行时解析，整组放入计划，不手填物理卡号。不带该参数只检查工具能力，不能作为正式采集计划。设备绑定、单进程启动与恢复规则见[设备契约](references/device-context.md)。

## 测量能力与建议

程序组成未知时可先用 msprof 最小采集。所接工具的 `inspect --brief` 或 `report --brief` 返回原名、次数、设备耗时和首条原件位置。已知 runner 只执行一次目标调用时，msprof 可从这份采集直接交付全部目标 launch。按耗时和依赖选择精采对象。

正式耗时是一次目标调用中各 kernel 设备耗时之和；保留重复 launch，排除 host 和间隙。单 kernel 测量尽可能预热并清 L2，多 kernel 默认无额外预热、自然缓存。工具默认配置和比较一致性见[采集口径](../ops-perf-acceptance-criteria/references/performance-collection.md)。专项诊断可另选工具，不将不同口径拼成一个正式值。

采集时核对输入、构建/加载身份及设备；占用信息可来自调用方或可用的查询手段，普通占用检查不能保证独占。二进制身份/段提取可用 `scripts/device_identity.py`。独立进程样本与 replay 分开计数。

采集进程退出且必要导出完成后再解析结果；已写出的日志可用于观察进度。

工具报错、参数不兼容或输出异常时，先看本机 help 和日志，必要时查该工具官方 GitCode 文档目录，修正用法后小范围验证；入口见各工具指导。

## 分析与统合

两种工具都已有报告时，可按同一构建、case 和调用范围对齐 kernel。优先看首采名册中的运行时名称，结合 runner 或原日志辨认实体。同一范围已核实，可用 `--analysis` 中的 `kernel_alignment` 展开已观察到的精确对应。其余由 agent 给出原名和依据，母报告核对原件并出表。相同范围可复用这份输入，示例见[报告契约](references/collection.md)。

从子工具取得带原件引用的专项报告，检查范围和缺口。按需补充板上或仿真流水、指令时序；流水优先看单核/单 MIX 组，不足再扩展多核。不同计时口径分别展示。

分析 CANNBot-DSL 算子时，若采集工具受阻或现有报告难以解释瓶颈，可参考 [Ascend 950 DSL 仿真留档](references/ascend950-dsl-simulation.md)辅助分析。

结合算子工作量和实际指标解释关键路径、核间负载、计算/访存及头开销，区分观测、推断和待验证项。给出适用 case、依据和验证重点明确的设计或优化建议；未知峰值、缺失计数和 `NA` 保持未知。

多 kernel 可结合数据传递和调度开销评估融合机会；是否合并由证据、实现代价及验证结果决定，时间相邻本身不足以说明应融合。

```bash
python "$REPORT_SKILL_DIR/scripts/profile_report.py" \
  --report "$CHILD_REPORT_JSON" --analysis "$ANALYSIS_JSON" --out "$REPORT_DIR"
```

`$CHILD_REPORT_JSON` 直接取子工具 `report` 命令返回 JSON 中的 `report` 路径。`--report` 可重复；`--analysis` 放母技能综合判断的 `findings` 与 `recommendations`。脚本核对原件和标准测量项，保留各工具口径，输出 JSON 与 Markdown 报告。优化轮次、候选选择和最终验收由调用方管理。

---
name: tool-msopprof
description: 仅由 ops-profiling-report 委派的 msopprof 工具技能：环境与 CLI 能力检查、命令生成、采集指导、结果检查和报告提取。
---

# msopprof

由母技能提供程序、argv/cwd、设备、采集范围和输出位置，以及 `report_context.tool_script`（下例的 `TOOL_SCRIPT`）。

```bash
python "$TOOL_SCRIPT" env
python "$TOOL_SCRIPT" command --output ./capture --warm-up=3 --replay-mode=kernel --kernel-name 'A|B' -- ./app arg
python "$TOOL_SCRIPT" inspect ./capture --brief
python "$TOOL_SCRIPT" report ./capture --case-id case1 --brief --out ./specialist-report
```

- `msopprof …` 与 `msprof op …` 是同一工具的入口。`env` 查询当前环境的工具路径、版本、选项与指标。
- 命令由调用方确定。可在一个进程采集多个 kernel；`--launch-count` 是采集的 kernel launch 数，不是独立启动或统计重复次数。
- 若本机支持 `--set`，可用 `--list-sets` 查看预设，也可用 `--aic-metrics` 直接选择指标。
- 单 kernel 最小计时默认 `--aic-metrics=BasicInfo --warm-up=3 --replay-mode=kernel --launch-count=1`；精采可选择其他指标/范围。kernel replay 在预热后尝试清 L2，失败可能告警后继续，记录日志中的实际条件。
- `inspect` 保留每个 kernel 的来源、原始字段及微秒耗时。重复同名记录可用 `--basic-info`、`--op-name`、`--device` 定位。
- `inspect --device` 筛选的是原始报告编号。正式采集和比较使用母技能的[设备绑定](../../references/device-context.md)，禁止把应用编号直接用于 CSV 筛选。用 `report --plan ... --attempt ...` 生成带绑定的报告。
- `protocol.kernel_filter` 是采集 CLI 的运行时符号/模式。正式计划的 `report_op_name`（旧字段 `kernel_name`）及诊断用的 `--op-name` 精确匹配 CSV 的 `Op Name`。
- 已经确认只发起一个目标 launch 的 runner，可在正式 identity 用 `{"kernels":"all"}`，从实际采集的唯一记录确定报告名。多目标诊断可在采集后用 `report --op-name` 选择实现，用 `--basic-info <CSV> --line N` 精确选取其中一条记录。只采第一条本身不能证明 runner 只有一个 kernel。
- 旧计划的编译符号可由同次采集的日志分析块恢复。适配器核对报告名、物理卡、PID、Block Dim、耗时及 launch 次数，并将日志收据写入 `kernel_name_binding`。
- 需要指标原始行时加 `--include-data`，或直接读已定位的 CSV；默认只给文件索引和 kernel 计时。
- 其它参数可按当前 help 直接调用，或用 `--option=--name=value`；自动适配器 context 对应 `extra_options`。范围重放还需匹配的 MSTX 配置，不只设置 replay-mode。
- 披露所用版本的流水范围、能力与采集/生成开销，结合原始字段给出专项观察及缺口；交付 `profile-report.json` 与专项 Markdown，供母技能统合。`report` 保留公共 `measurements/evidence/identity/protocol`。

需要字段含义、版本差异或清缓存边界时读母技能返回的 `report_context.tool_reference`。原始 CSV、trace、日志保留在调用方输出目录；HTML 可视化交回母技能。

参数或使用异常时可查[官方文档目录](https://gitcode.com/Ascend/msopprof/tree/master/docs/zh)，与本机 help 和版本核对后修正用法。

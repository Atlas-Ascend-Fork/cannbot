# 调用契约

调用方提供程序、argv/cwd、case/输入、源码/构建/加载身份、设备、环境、精度依据与输出目录。

正式采集先按[设备契约](device-context.md)用应用可见编号准备运行时绑定，将返回字段整组放入计划；物理卡号由解析器生成。采集、发布、screening 和恢复均检查同一绑定与目标 PID。没有绑定的原始报告仅用于诊断。

`report_contract.py --prepare` 返回单个工具绑定或 `bindings`，不是完整采样 plan。多个工具的 context 可用 `per_tool` 区分；未接入项不读取指导、不导入适配器。自动独立采样由调用方按已有[采集 plan schema](../../ops-perf-acceptance-criteria/references/profile-evidence.md#plan-schema-1)补齐身份、输入、设备/频率与采样安排。仅命令或 trace 诊断按子工具指导执行，不要求正式统计计划。

context 的 `tools` 选择已注册工具，例如 `{"tools":["msprof"],"application_device":0}`；省略则准备全部注册项。每版目标信息由工具解释：msopprof 使用 `report_op_name`（旧计划兼容 `kernel_name`）/ 可选 `occurrence`，msprof 使用 `kernels` 列表，见各自工具指导。

自动测量适配器是可选接口：

| 接口 | 责任 |
|---|---|
| `prepare(context)` | 检查能力，返回工具收据、协议与私有指导路径 |
| `validate_measurement(plan)` | 核对该工具的冻结测量协议 |
| `collect_attempt/recover_attempt` | 采集或恢复原有证据 |
| `check_command/validate_failure/validate_publication` | 核对实际命令、失败与原件；传入 plan |
| `raw_sample` | 提取一次目标调用的 kernel 设备耗时总和与进程标识 |
| `validate_screening/validate_report` | 复核专项报告与原始数据 |
| `check_report_output(report, out)` | 可选，由子工具检查输出目录是否落在受保护的采集原件范围内 |

工作流仍管理独立进程样本、重试、比较和最终验收；每个计划固定一个工具绑定。

母报告脚本接受一个或多个 `--report`，只消费公共报告字段；各原始格式由所选子工具复核。

子报告可提供经复核的 `invocation={duration_us,statistic,records}`，对应一个明确选中的调用；母报告分工具/协议展示调用总值和逐 launch 明细，不跨报告求和。直接采集成功的 attempt 用 `tool_elapsed_seconds` 记录启动工具到解析校验完成的实际用时；失败后恢复的完整成本未知时省略此字段。

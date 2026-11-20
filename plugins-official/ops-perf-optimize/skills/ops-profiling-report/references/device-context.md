# 采集设备契约

适用于已接入工具的单进程、单目标设备采集。应用使用自己的可见设备号；CANN 的 user、runtime logical、physical 编号分开记录。映射不能由 CSV 反推，也不能把可见列表元素直接当作物理卡号。msopprof 的 application replay 会重新启动应用，正式单进程绑定提前拒绝；kernel 与同进程 range replay 保留原工具参数约束。

## 准备与启动

在采集入口一次性设置环境，并保持到采集结束：

```bash
export ASCEND_RT_VISIBLE_DEVICES=4
python "$REPORT_SKILL_DIR/scripts/report_contract.py" \
  --prepare --application-device 0 --out "$PREPARATION_JSON"
```

通过 context 的 `tools` 选择工具；省略则返回所有注册工具的 bindings。将所选绑定的 `tool`、`protocol`、`report_context`、`device_binding`、`environment`、`physical_device`、`logical_device` 整组放入正式计划，再补充原有输入、身份与采样安排。`logical_device` 是保留的应用编号字段，不是 CANN 内部逻辑编号。两项编号均为绑定的只读投影，改变设备须重新准备和注册计划。

不带 `--application-device` 的 prepare 仅查询工具能力，返回 `device_binding_status=required_for_measurement`。上下文 JSON 也可传 `application_device`；多个工具使用各自的 `per_tool` context。

设备解析在独立进程中加载当前 `ASCEND_HOME_PATH/lib64/libascendcl.so`，调用 `aclrtGetDeviceCount`、`aclrtGetLogicDevIdByUserDevId`、`aclrtGetPhyDevIdByUserDevId`，不执行 kernel。绑定保留设备选择环境的设置/未设置状态、实际映射、可见设备数、主机启动标识及运行库/解析脚本/启动解释器的文件收据。空可见列表、重复编号、非法编号或查询失败直接拒绝；未设置可见列表则依据运行时查询结果。

采集开始前核对环境及映射。每个子进程显式传入独立的 `env` 字典，不修改采集器全局环境。工具使用同一环境启动目标包装器；包装器核对继承环境，记录 PID、进程启动标识、绑定散列和 capture ID，然后用 `exec` 替换为冻结的 runner。

runner 必须是绝对路径。shell runner 必须 `exec` 最终应用；多进程启动器、后台子进程、改变 PID namespace 的 runner 不在此契约支持范围，PID 不一致时保留现场并拒绝正式样本。包装器记录的是 exec 前环境，不能观测任意目标程序后续的环境修改；最终设备由独立 runtime 预检查与实际 kernel CSV 交叉核对，不把包装器记录冒充目标内部探针。运行库映射、可见列表或目标 PID 无法对应时不降级猜测。

## 报告读取

msopprof 将 CSV 的 `Device Id` 和 `Pid` 与运行时绑定的物理设备和目标进程核对。msprof 还核对 `op_summary.Device_id` 与原件目录 `device_N`，PID 取同一 PROF 的 `host/info.json.pid`。

`inspect_collection` 和 msopprof CLI `inspect --device` 保留原始编号语义；它们不自行解释环境。正式流程通过 `read_bound_records` 统一读取并校验设备。选择、发布、原件复核与恢复调用同一入口，不能另写逻辑/物理比较。

原始 `record.device_id` 和 CSV 不变。带绑定的诊断报告额外输出 `application_device`、`physical_device`、`device_namespace`，业务代码可使用明确的应用编号。`npu-smi` 等管理命令使用绑定中的物理编号和已核对的管理拓扑，不能假定它们遵循可见设备环境变量。

生成有设备证据的诊断报告：

```bash
python "$TOOL_SCRIPT" report "$CAPTURE_OUTPUT" \
  --plan "$PLAN" --attempt "$ATTEMPT" --out "$SPECIALIST_REPORT"
```

`--plan` 和 `--attempt` 必须成对；case、kernel、设备与协议由冻结计划提供，不能再传覆盖参数。正式计划必须在采集前填入非空 `effect_case_id`，attempt 和报告核对同一 case。原始诊断报告仍可直接生成，但没有设备绑定时不能用于 screening 比较。母报告会复核绑定、目标进程和原件；诊断报告本身仍是 `performance_eligible=false`。

## 失败与恢复

- 报告设备错误：`DEVICE_ID_MISMATCH`，包含应用编号、预期物理编号、报告命名空间和实际编号。
- 报告 PID 不属于被启动目标：`TARGET_PID_MISMATCH`，不能忽略设备或 PID 过滤后选第一条。
- 绑定、原件或目标进程收据被改动：拒绝发布与复用。
- 已有原件的失败保留 `needs_review`，不因设备解析失败而重新上板覆盖现场。
- 恢复仅使用冻结的 plan、设备绑定、目标进程收据及原始 CSV，不查询当前运行时或当前环境；新增结果落在独立 recovery 目录。

正式计划必须包含 `runtime_device_v1` 绑定。不兼容旧计划的正式恢复，不推测缺失身份；旧 CSV 可用原始 inspect/report 离线诊断，也可作为回归输入。已有模型、计时、预热、kernel/occurrence 选择规则不因设备修复而放宽。

## 验证范围

离线回归覆盖非零卡、可见列表重排、容器式逻辑到物理映射、环境变化、错误设备/PID、收据修改和恢复。真实 runtime/采集验证以实际运行的版本和设备为准；模拟容器映射测试不代表已验证任意虚拟化平台。新增平台或报告格式必须先验证编号语义，禁止遇到未知情况默认使用 0。

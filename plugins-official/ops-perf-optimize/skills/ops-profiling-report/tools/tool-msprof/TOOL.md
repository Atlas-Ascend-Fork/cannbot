---
name: tool-msprof
description: ops-profiling-report 的网络级 msprof 工具：基础 kernel 观测、逐 launch 设备耗时和完整调用取样。
---

# msprof

网络级 `msprof` 与 `msprof op` / `msopprof` 是不同工具。下例 `TOOL_SCRIPT` 来自准备结果。

```bash
python "$TOOL_SCRIPT" env
python "$TOOL_SCRIPT" command --output ./capture -- /absolute/app arg
python "$TOOL_SCRIPT" inspect ./capture --brief
python "$TOOL_SCRIPT" report ./capture --case-id case1 --brief --out ./specialist-report
```

`command` 只生成 argv。默认 `--task-time=l0 --ai-core=off --ascendcl=off --sys-lp=off`，采集和自动导出后读取 `op_summary*.csv` 与同一 PROF 的 `host/info.json`。不额外预热或清 L2，不要求程序计时/标记。原件中的其他任务不自动算作目标调用。

l0 采集保留名称、设备、stream/task、开始时间和 duration；OP Type、Task Type、shape 等可能为 N/A。`on` 等价 l1，可按需要增加信息。`--l2` 采计数，`--task-time=l2` 提高详细度，都不是清缓存。`--option=--name=value`（prepare context 的 `options`）替换整组默认参数。

## 目标与正式取样

准备 context 显式选择工具，例如 `{"tools":["msprof"],"application_device":0}`；设备编号继承母技能的[设备契约](../../references/device-context.md)。`Device_id` 是物理编号，真实 OS PID 取自 `host/info.json.pid`，trace JSON 的 pid 可能只是展示编号。

每版 identity 的 `kernels` 描述一次目标调用的组成，名称使用 `inspect` 返回的 **op_summary 精确名称**，与 task_time 或 msopprof 的具体 kernel 符号可能不同：

```json
{"kernels":[
  {"name":"aclnnAdd_AddAiCore_Add","occurrence":0},
  {"name":"aclnnMul_MulAiCore_Mul"},
  {"name":"aclnnAdd_AddAiCore_Add","occurrence":1}
]}
```

若 runner 已把一次目标调用隔离出来，其全部设备任务均属于目标，可在采集前填 `{"kernels":"all"}`，单、多 kernel 都使用本次原件。范围尚未确定时先读名册，再用 `report --identity` 在原件上选取。简表的 `runtime_names` 来自同份导出的 `task_time`，按设备、stream、task 和开始时间精确关联。`launches` 为该名实际关联到的次数。

`occurrence` 是同名记录按设备开始时间排列后的零基索引；名称唯一时省略。同名重复 launch 分别列出，每条只选一次。由 runner/源码和原件确认哪些记录属于一次调用；脚本不推测调用归属。双方组成可不同。

`raw_sample` 返回目标记录的 duration 之和及真实 PID。`frequency_policy=record_only`：此 CSV 没有 Current/Rated Freq，不能据此证明额定频率；可用于现有 median 采样路径。正式样本仍绑定实际 argv、同一可见环境、设备、进程和原件，恢复只解析已有数据。

```bash
python "$TOOL_SCRIPT" report "$CAPTURE_OUTPUT" \
  --plan "$PLAN" --attempt "$ATTEMPT" --out "$SPECIALIST_REPORT"
```

带绑定报告从计划选取目标，输出 `invocation` 总耗时和全部逐 launch 明细。直接诊断可以传 `--identity` JSON 选择调用；未选目标时只展示逐行耗时，不将全进程相加。`--conditions` 可记录实际缓存、输入和独占情况。报告供母技能统合；正式统计复用现有采样器。

## 用法核对

参数或输出异常时核对本机 help、日志和对应版本文档。本机 `msprof --version` 不提供版本；CANN 包的 `share/info/msprof/version.info` 可查工具版本，`host/info.json` 的 `cannVersion` 是 CANN 版本。

- [官方 msprof 文档目录](https://gitcode.com/Ascend/msprof/tree/master/docs/zh)
- [AI 任务采集参数](https://gitcode.com/cann/oam-tools/blob/master/docs/zh/user_guide/profiling/msprof_cmd/ai_runtime_profile_data.md)
- [输出数据格式](https://gitcode.com/Ascend/msprof/blob/master/docs/zh/user_guide/profile_data_file_references.md)

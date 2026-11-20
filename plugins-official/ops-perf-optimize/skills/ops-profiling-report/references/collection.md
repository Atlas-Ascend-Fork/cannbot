# 子工具与报告流

`profilers.json` 的 `tools` 是当前接入列表，每项包含 `id`、私有指导文档 `guide`，以及可选的 Python `adapter`。

准备器 context 可用 `tools` 选择子集，用 `per_tool` 分别传入各工具参数；单工具也可直接传其 context。单个绑定可冻结进测量计划，多个绑定分别使用，不能混为同一统计样本。

Markdown 和 JSON 分别发布，以最后出现的 `profile-report.json` 为完成标志。中断若只留下 Markdown，可用原采集在新目录重新生成两份文件。

报告的公共字段为：

| 字段 | 内容 |
|---|---|
| `provider/case_id/status` | 已接入工具 ID、目标、专项报告状态 |
| `identity/protocol/conditions` | 版本及输入身份、计时口径、warmup/清 L2/NPU 占用证据；未知如实保留 |
| `measurements` | 逐 kernel/launch 的 `kernel/device/pid/duration_us/evidence/line`；耗时统一微秒 |
| `evidence` | 原件的 `{path,sha256}` 列表 |
| `observations/limitations` | 专项发现、缺失项及适用边界 |

`--analysis` 可附同一 case 的 kernel 对照，每个工具使用自己报告中的精确原名。

```json
{"kernel_alignment":[{"case_id":"single","names":{"msprof":"aclnnAdd_AddAiCore_Add","msopprof":"Add_FLOAT32_high_performance_8"},"basis":"同一 single runner 只执行一次 Add，两份采集各有一个目标 launch。"}]}
```

同一 runner 和用例已经由 agent 核实时，可直接让脚本展开观察到的精确对应。母报告按首采的设备、stream、task、开始时间查到运行时名称，再核对另一份报告。唯一名称覆盖该实体的全部首采 launch 且精采中确有该名时才展开。报告表格链接两侧首行及中间任务原件。

```json
{"kernel_alignment":{"case_id":"repeat","runtime":"msprof","detail":"msopprof","basis":"已核对两次使用相同 runner、输入和构建。"}}
```

未精采或待区分的一侧填 `null`，在 `basis` 说明。对照记录每个实体在各份报告中的次数与首条原件位置，跨进程比较实现时，PID、task ID 和发生序号仅在各自的采集内有效。

工具不支持某项要求时说明缺口，按分析目标决定补证方式。

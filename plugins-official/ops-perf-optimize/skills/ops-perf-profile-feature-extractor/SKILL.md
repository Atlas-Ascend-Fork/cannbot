---
name: ops-perf-profile-feature-extractor
description: 复杂算子性能特征提取。当简单 profile 信息（聚合指标、torch profiler Duration 等）不足以支撑瓶颈分析时，使用各类工具提取诊断级性能特征（pipe 流水图、逐指令时序、依赖与气泡等），供后续分析使用。不用于稳态耗时验收。触发：仅由 ops-perf-optimize 工作流按阶段派发时使用。
---

# 性能特征提取（流水图）

本 Skill 面向**复杂算子**：简单 profile 的聚合指标无法回答"哪条 pipe 在空、谁堵了谁"时，用各类工具提取诊断级性能特征，产出供后续分析使用；稳态计时与性能验收仍走 `ops-profiling`。先核验目标 SocVersion、`msprof op --help` 与当前调用方式，再选路：

| 平台 | 流水图来源 | 适用问题 |
|---|---|---|
| Ascend 950 | 板上 `PipeTimeline` 看各 pipe，`instrTimeLine` 看逐指令实际时序；无卡时可用 `npusim record`（旧名 `cannsim`） | 真实重叠/气泡优先板上；仿真用于指令推演 |
| Atlas A2/A3 | `TimelineDetail` 上板取得输入与核上下文，再由仿真器生成指令图；无板卡或调用路径不支持时用 `msprof op simulator` | 诊断单核指令依赖与流水关系 |

A2/A3 的 `Task Duration` 和 `PipeUtilization` 是板上数据，`TimelineDetail` 的**指令图是仿真结果**；当前能力不能把 `PipeTimeline` 当作 A2/A3 的板上流水入口。`-g` 只补充源码/调用栈映射，不改变时间线来源。具体支持范围以[官方 msOpProf 指南](https://www.hiascend.com/document/detail/en/mindstudio/2610/optools/Operatordevelopmenttools/docs/en/user_guide/msopprof_user_guide.md)及已安装工具为准。

`PipeUtilization` 只有聚合指标，不是流水图。仿真周期、仿真墙钟和裁剪 case 的板上耗时均不得替代完整 case 的稳态计时。

详细坑与看图见 [references/collection.md](references/collection.md)。

## 诊断负载

A2/A3 的长序列、多核或大量循环可能让仿真耗时远超算子板上耗时。全尺寸预计或实测超出分钟量级预算时，按 [采集参考](references/collection.md#诊断负载裁剪)构造保留目标计算路径的隔离探针；记录裁剪前后 shape、属性、tiling 分支、有效核数和索引分布。要分析核间同步或负载不均时，保留相应多核条件，不能用单核裁剪图推断原 case 的跨核行为。

## 公共前置

1. 只 source 用户指定的 CANN `setenv.bash` / `set_env.sh`，不要混两套 toolkit。
2. 程序只调用一次目标算子；造数、JIT 编译及辅助 launch 放在目标调用前并 `synchronize`，程序里不叠加性能计时循环。
3. 必须带 `--kernel-name=<前缀>`（板上和 A2/A3 仿真都要）。默认采第一个 AICore launch，通常是 Cast/ZerosLike。
4. 同一张卡不和正在跑的 msprof / simulator 并发。
5. 先确认可执行程序单独跑得通，再套 profiler。

## Ascend 950：板上流水

伪代码：

1. 删除并重新创建输出目录 `<out>`。
2. 调用 `msprof op`，输出目录设为 `<out>`。
3. 按诊断粒度将采集指标设为 `PipeTimeline` 或 `instrTimeLine`，命中次数设为 1；两者分别采集。
4. 设置 `kernel-name` 为目标 kernel 前缀。
5. 传入只 launch 一次目标算子的程序。

| 参数 | 原因 |
|---|---|
| `--aic-metrics=PipeTimeline` / `instrTimeLine` | 分别采 pipe 运行状态 / 逐指令板上时间线 |
| `--launch-count=1` | 只采 1 次命中的 kernel |
| `--kernel-name=` | **前缀匹配**。C++ 核用 mangled 名（如 `_Z22fia_noquant_mla_kernel`），注册算子用 OpType（如 `FlashMlaWithKvcache`） |

成功日志应包含设备与目标 kernel、`Task Duration(us)`，以及 `OPPROF_*` 结果目录。

`OPPROF_*/`：

| 文件 | 用途 |
|---|---|
| `trace.json` | Perfetto / Chrome `chrome://tracing` |
| `visualize_data.bin` | MindStudio Insight |
| `OpBasicInfo.csv` | Task Duration、Block Dim、Current/Rated Freq |

核对 `Current Freq == Rated Freq`；未满频的图不能当瓶颈证据。`Task Duration` 与预期不符时，核对命中 kernel 和实际输入。

## 仿真指令流水

### Ascend 950PR / 950DT → npusim

`cannsim` 是旧别名，优先写 `npusim`。仅支持单卡、device 0、AI Core 计算类（无 MC2/HCCL）。

伪代码：

1. 调用 `npusim record`，输入用户程序，指定芯片为 `Ascend950`，生成报告并写入 `<out>`。
2. 默认只生成 core 0 的流水；需要其它核时，对已有 record 目录调用 `npusim report`，指定核编号和 `<report_out>`。

`<user_app>` 可以是 `./test_aclnn_xxx` 或 `python3 run_once.py`。同样要求程序只 launch 一次目标核。

产物：

产物路径模式为：`<out>/npusim_*/npusim.log`，以及
`<out>/npusim_*/report/results/kernel_*/core_*/trace_core*.json`。

`kernel_0` 经常是 `zeros`/`Cast`，目标算子通常是后面的 `kernel_*`。按 `blkDim`、kernel 名、耗时对一下再读。

`trace_core*.json` 拖到 `chrome://tracing` 或 https://ui.perfetto.dev。HTML 报告若依赖 plotly 且环境没装，JSON 才是结果，不要打开空 HTML 当失败。

约束：无驱动也能跑；建议 ≥16 核 CPU / 32GB；当前文档写明不支持 ARM 仿真。

### Atlas A2 / A3 → 仿真指令流水

有板卡且当前调用路径受支持时，使用 `msprof op --aic-metrics=TimelineDetail,Default --kernel-name=<目标> --launch-count=1 --output=<out> <app>`；`Default` 用于同时保留板上指标。不支持该调用路径或无板卡时，核验并使用 `msprof op simulator`。两条路径都需确认命中目标 kernel，并检查 `OPPROF_*/simulator/trace.json` 或 `visualize_data.bin` 实际生成；进程退出码不能单独证明流水采集成功。调用限制、环境与排障见 [采集参考](references/collection.md)。

`--core-id` 只指定**解析**哪个核的仿真数据，不减少内核执行量。若单核流水足以回答问题，应从算子分核规则出发裁剪输入，使有效工作集中在少量核；仿真超预算时继续缩小诊断负载，不靠增加超时阈值解决。

## 看图口径

- 横轴时间，纵轴核（`coreN` 下还有 cubecore / veccore）。
- 同名 pipe 上的空隙 = 空转或等依赖（QKᵀ → softmax → PV 串行最常见）。
- 950 板上时间线是硬件时序；A2/A3 `TimelineDetail` 是仿真指令时序。可用仿真图定位依赖和气泡，不按仿真周期推算板上收益。
- 仿真开头大段 SCALAR 常是核上启动，不是 HBM 搬运；头开销 = 全局起点 → 第一条 MTE2。
- 分析脚本（若环境有）：对 cannsim/npusim 的 Chrome trace 用 `pipeline_bound_analyze.py`；字段对不上时按最后一个 `_` 分段（如 `AIC_52_MTE2` → `MTE2`）。

## 禁止

1. 将大负载直接交给仿真器长期运行，或把改变 tiling 分支的裁剪图当作原 case 的流水证据。
2. 省略 `--kernel-name`。
3. 把 `PipeUtilization`、TTK `op_perf_us`、torch profiler Duration 当成流水图。
4. 程序里 10 组 warmup+target 再交给 `msprof op`（它自己会 replay）。
5. 混用两套 CANN 的 `LD_LIBRARY_PATH` / profiler 库。
6. 在 A2/A3 上把 `TimelineDetail` 图或 `--core-id` 解释成板上逐指令实测或单核执行开关。

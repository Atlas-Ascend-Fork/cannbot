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

设备身份、concrete 重放入口、先保存真值及异常退出的八阶段门禁见[身份与重放证据](references/identity-and-replay-evidence.md)；使用只读工具，输出 FAIL 的图标明诊断用途。

板上与 A2/A3 的排障、看图见 [references/collection.md](references/collection.md)。Ascend 950 的仿真、DSL 输入重放或“成功却不出图”问题，先读 [完整仿真经验](references/ascend950-dsl-simulation.md)：含可执行命令、NZ/别名/tiling 恢复、报告修复和四个已验证用例。

路径由当前任务提供：本技能资源相对实际加载的 `SKILL.md` 定位，CANN 环境脚本、Python 环境、runner、输入快照和输出目录来自用户或当前项目。不得依赖开发者机器的用户名、conda 环境名、CANN 安装目录或历史采集文件；本次生成的 archive、DB 和 trace 按实际产物核对。

## 诊断负载

长序列、多核或大量循环可能让仿真耗时远超板上耗时。50/70 µs 等上板耗时只能作为用户指定的筛选条件，不能自行设为仿真准入门槛；分钟量级也是成本估计，不是自动中止条件。用户要求完整 case 时继续采集并报告进度，不因慢就裁剪。存在用户给定的预算或只需隔离诊断时，按 [采集参考](references/collection.md#诊断负载裁剪)构造保留目标路径的探针，记录原始/裁剪后的 shape、属性、tiling、核数和索引分布。跨核同步或负载不均必须保留相应多核条件。

## 公共前置

1. 只 source 用户指定的 CANN `setenv.bash` / `set_env.sh`，不要混两套 toolkit。
2. 程序只调用一次目标算子；尽量在重放前完成造数、布局转换和辅助 launch，调用前后 `synchronize`。首次 JIT 可发生在仿真进程，但要和计算记录区分，不叠加性能计时循环。
3. `msprof op` 路径带 `--kernel-name=<前缀>`，避免默认采到 Cast/ZerosLike。本次 CANN 9.2 的 `npusim record` 没有此参数：通过单次重放和明确选择目标 DB 定位 kernel，不能传入不存在的选项。
4. 设备共享与调度按用户授权执行。共享卡采集时记录占用、频率与样本波动；CPU 仿真也会消耗大量主机资源。仿真中逻辑 device 必须为 0，不能沿用上板的物理卡可见性设置。
5. 先确认可执行程序单独跑得通，再套 profiler。

## Ascend 950：板上流水

伪代码：

1. 为本次尝试创建新的输出目录 `<out>`，保留此前成功、失败和中止记录。
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

推荐将 record、校验和 report 分开，报告失败时可直接重试解析已有 DB，不必重跑仿真：

```bash
npusim record "$trace_app" -s Ascend950 -n all -o "$trace_run/record"
# 先核验 npusim.log 中用户程序成功，以及程序自身的输出校验。
# 按下文核对目标 DB，放入 trace_selected_record 后再解析。
npusim report -e "$trace_selected_record" -n 0 -o "$trace_run/report"
```

`trace_app`、`trace_run`、`trace_selected_record` 由当前任务显式设置；应用可以是 runner 命令或可执行文件。命令的安全构造与其它路径参数见 [环境与配置](references/ascend950-dsl-simulation.md#1-环境与采集身份)。本次验证的 CANN 9.2 中，record 的 `-n` 控制哪些核**记录日志**，report 的 `-n` 选择已有记录的解析核；均不替代 kernel 的 `block_num`。需要多核证据时 record 用 `-n all` 或所需核范围，再选择报告核。只记录 core 0 后不能凭 report 补出未记录核的指令。

当前产物通常为 `<out>/npusim_*/record/NNNN_*kernel*.db`、`npusim.log`，报告为 `<report_out>/results/NNNN_*_reports/core_*/trace_core*.json`；不同版本名称有差异，按实际文件发现。准备核经常排在目标前面，不能默认选序号 0000 或所有 `*acl_kernel*.db`。

用 [scripts/select_simulator_db.py](scripts/select_simulator_db.py) 查看 DB 指令数量，核对目标身份后将明确指定的 DB 放入独立报告目录；空 DB 引发除零、索引页找错层级等修复见 [完整经验](references/ascend950-dsl-simulation.md#报告失败与目标-db-选择)。

原始 JSON 可在 Perfetto / Chrome 查看。用 [scripts/render_pipeline_trace.py](scripts/render_pipeline_trace.py) 生成 PNG/SVG、离线交互 HTML 和合并重叠区间后的统计；显式填写 Board/Simulation/unknown 来源、工具/SoC/模型、case/kernel、recorded/reported 核、full/cropped/unknown 范围与输出状态；旧调用默认 Simulation，板上必须明确 Board。至少检查图片可读、链接可访问，以及 trace 有目标流水的非零时长指令。不能仅以退出码或聚合 HTML 判定成功。主机架构支持按本机工具核验，本次验证环境为 x86_64。

### Atlas A2 / A3 → 仿真指令流水

有板卡且当前调用路径受支持时，使用 `msprof op --aic-metrics=TimelineDetail,Default --kernel-name=<目标> --launch-count=1 --output=<out> <app>`；`Default` 用于同时保留板上指标。不支持该调用路径或无板卡时，核验并使用 `msprof op simulator`。两条路径都需确认命中目标 kernel，并检查 `OPPROF_*/simulator/trace.json` 或 `visualize_data.bin` 实际生成；进程退出码不能单独证明流水采集成功。调用限制、环境与排障见 [采集参考](references/collection.md)。

`--core-id` 只指定**解析**哪个核的仿真数据，不减少内核执行量。若单核流水足以回答问题，应从算子分核规则出发裁剪输入，使有效工作集中在少量核；仿真超预算时继续缩小诊断负载，不靠增加超时阈值解决。

## 看图口径

- 横轴时间，纵轴核（`coreN` 下还有 cubecore / veccore）。
- 同名 pipe 上未记录指令的空隙可能是等待、空闲或缺记录；不能据此证明硬件空闲。明确记录完整时再结合依赖解释气泡（QKᵀ → softmax → PV 串行最常见）。
- 950 板上时间线是硬件时序；A2/A3 `TimelineDetail` 是仿真指令时序。可用仿真图定位依赖和气泡，不按仿真周期推算板上收益。
- 仿真开头大段 SCALAR 常是核上启动，不是 HBM 搬运；头开销 = 全局起点 → 第一条 MTE2。
- 本次 CANN 9.2 trace 的 `ts/dur` 已是 µs；`displayTimeUnit: ns` 是查看器显示设置，不能据此再次转换。其它版本先核验单位，仿真器墙钟另列。
- 流水身份来自 `process_name` 元数据，保留 AIC/AIV 与核身份；`SCALAR_LDST` 是完整流水名，不能一律取最后一个 `_` 字段。旧 `pipeline_bound_analyze.py` 的标签适配另存 normalized JSON；原始 trace 不改写。脚本若写成 cycles 而输入是 µs，须修正报告单位。

## 禁止

1. 自行用固定上板耗时或墙钟阈值排除用户要求的 case，或把改变 tiling/核数的裁剪图当作原 case 的证据。
2. `msprof op` 正式采集省略目标 kernel 过滤，或 `npusim` 未核对目标 DB 就报告第一个/所有 kernel。
3. 把 `PipeUtilization`、TTK `op_perf_us`、torch profiler Duration 当成流水图。
4. 程序里 10 组 warmup+target 再交给 `msprof op`（它自己会 replay）。
5. 混用两套 CANN 的 `LD_LIBRARY_PATH` / profiler 库。
6. 在 A2/A3 上把 `TimelineDetail` 图或 `--core-id` 解释成板上逐指令实测或单核执行开关。
7. 将准备、仿真执行、输出校验、报告和可视化的失败混为一谈；失败/中止尝试也要列出原因、修复和最终产物。

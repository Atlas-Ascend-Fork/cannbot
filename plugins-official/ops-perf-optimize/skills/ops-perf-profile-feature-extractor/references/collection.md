# 流水图采集：排障与看图

## 失败对照

| 现象 | 处理 |
|---|---|
| 日志连续 `Kernel xxx skipped`，没有 `Start profiling ... <目标>` | `--kernel-name` 前缀不对，或程序没 launch 到 AICore |
| `Task Duration` 与预期 kernel/shape 不符 | 核对命中名称、输入和 tiling；不要仅凭时长判断是否采错 |
| 图里只有 SCALAR / 没有 MTE2 | 看错了 `kernel_*`，或 launch 的不是计算核 |
| 仿真超出诊断预算 | 停止后按下文裁剪负载，核对目标分支，再采一次 |
| import 自定义包失败 / profiler 报 driver 不兼容 | 确认只 source 了一套 CANN；conda `site-packages` 不要被 toolkit 自带包盖住 |
| npusim 报只能 0 卡 | 程序里写死 `npu:0`，不要设 `ASCEND_VISIBLE_DEVICES` 到别的卡 |
| `trace.json` 缺失、只有 CSV | 核对目标平台的指标与采集日志；`TimelineDetail` 还需确认上下文保存和仿真是否成功 |
| HTML 报告空白 | 缺 plotly；读 `trace_core*.json` |

## 怎么拿到 `--kernel-name`

1. 先**不加** `--kernel-name` 跑一次 `msprof op`（或看 `npusim.log`），抄日志里的 kernel 字符串。
2. C++ 直调：`nm -D` 目标 `.so`，找 `T` 符号里带 `kernel` 的 mangled 名，填能唯一前缀匹配的一段。
3. 注册算子 / torch.ops：用 OpType，如 `FlashMlaWithKvcache`。不要带 `Metadata` 伴生核。

## 单 launch 程序骨架

伪代码：先完成造数、JIT、LUT、`empty`/`zeros` 等准备工作；同步设备；只调用一次目标算子；再次同步设备。

`msprof op` 默认还会自己 warmup 若干次 replay，所以程序侧不要再循环。

## Ascend 950 板上 trace.json 怎么读

- 事件名：`CUBE` / `VECTOR` / `MTE1` / `MTE2` / `MTE3` / `SCALAR` / `FIXP`。
- AIC 核下 cubecore + 两个 veccore（CV_RATIO=2）。
- 关注：同 pipe 空隙、CV 是否重叠、Fixpipe 是否把后半拍堵住、尾部 SyncAll / FlashDecode。
- `OpBasicInfo.csv` 的 Block Dim 必须对得上预期核数；和稳态采集不一致时先查是否采到了别的 kernel。

## 仿真流水怎么读

Chrome trace 常见字段为 `ts` / `dur` / `name`。先确认产物属于目标 kernel，再按工具单位解释时间轴；仿真时间不等于板上耗时。

建议先切窗口：

| 窗口 | 含义 |
|---|---|
| 全局 span | max(end) − min(start)，含核上启动 |
| 头开销 | 起点 → 第一条 MTE2 |
| 有效计算窗 | 第一条 MTE2 → 结束；用于定位内部依赖与气泡 |

只看核 0 无法判断负载不均或跨核同步；需要这类结论时保留多核负载并补充相应核的证据。

`npusim report -n all` 会放大 `instr.bin`，长 kernel 先核 0 定性，再按需加核。

## A2/A3 仿真采集

上板 `TimelineDetail` 是**板上捕获、仿真出图**。先核验当前 msOpProf 对芯片和调用路径的支持；[官方指南](https://www.hiascend.com/document/detail/en/mindstudio/2610/optools/Operatordevelopmenttools/docs/en/user_guide/msopprof_user_guide.md)所述路径为 PyTorch 单算子 API 调用。仅需流水图时选 `TimelineDetail`，同时要板上 CSV 时选 `TimelineDetail,Default`；诊断采集可设 `--launch-count=1 --warm-up=0`，正式计时另走稳态协议。无板卡或调用路径不支持时，核验 `msprof op simulator --help` 后使用对应 SoC 的独立仿真入口。

两条路径均以目标 kernel 名称、仿真启动/完成日志和 `OPPROF_*/simulator/trace.json` 或 `visualize_data.bin` 为成功条件；上板 Task Duration 与仿真图分别标注来源。`--core-id` 只减少解析范围，不能替代负载裁剪。

## 诊断负载裁剪

1. 先确定要看的阶段或依赖，冻结影响路径的 dtype、布局、属性、可选输入状态及关键维度；从 Tiling 和 kernel 分工确认分支、有效核数、内层 tile/循环和索引范围。
2. 对单核依赖，优先缩小外层并行维度到少量有效工作核，再缩短序列或选中块数；只保留能体现目标稳态、尾块或稀疏访问的最小规模。若诊断多核同步/负载，必须保留足以触发该机制的核数。索引分布与边界条件也按诊断问题保留。
3. 在隔离探针上先独立运行，再采一次流水并量完整命令墙钟；超过分钟量级预算就停止，继续裁剪主导执行量的维度。`--core-id`、只减少输出核数、单纯延长 timeout 都不能证明仿真工作量下降。
4. 比较原 case 与探针的 TilingKey/模板、有效核数、目标循环和输入语义；这些条件不对应时，不能将该图归因给原路径。报告列明裁剪范围与失去的行为覆盖；正式性能仍用完整 case 上板采集。

## 和稳态计时的关系

| 需求 | 工具 |
|---|---|
| 可比较的 kernel 耗时 / MFU | `ops-profiling`（`PipeUtilization` 或 `msprof application`） |
| 看哪条 pipe 在空、谁堵了谁 | 本 Skill（流水图） |
| TTK 批量 `op_perf_us` | TTK 标准 skill（`ttk-how-run-test`），不是流水图 |

流水图伴随的 `Task Duration` 是单次采集结果，不能当前后优化的正式 delta；仿真周期、仿真器墙钟和裁剪探针的 Task Duration 更不能外推完整 case 时延。

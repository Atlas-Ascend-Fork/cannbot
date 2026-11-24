# GE 运行时与图优化（强相关细节）

> 供 `model-recommend-ascend-env-baseline` / `baseline-run` / `ge-graph-optimization` / `analysis` / `precision-comparison` 引用。skill 侧只写通用方法，GE 具体命令与选项以本文件为准。

## 1. 执行框架 GE_SESSION_DEMO（仅 onnx 路径）

- 入口：`prepare.sh <id>` → `compile.sh` → `run.sh <id>`；精度 `run.sh <id> --verify`；采集 `run.sh <id> --prof ge|msprof`；图 `run.sh <id> --dump_graph`；数据 `run.sh <id> --dump_data`。
- 禁止绕过脚本直接执行二进制（工作目录与缓存治理依赖脚本）。
- 框架属只读依赖：只能通过 `run.sh`/`test.sh` 参数与环境变量驱动，不得改 `run.sh`/`test.sh`/`src/`/`tools/`。

## 2. GE Session v2

- `GEInitializeV2` / `GeSession` / `RunGraphAsync`；单设备一个 Session；单 Graph 同 `graph_id` 重复 `AddGraph`。
- onnx 经 `aclgrphParseONNX` 解析；输入以 `gert::kOnHost` 放置，H2D 由 GE 内部完成；warmup 一次触发编译（不计时）。
- 支持 dtype：fp32 / fp16 / bf16 / int32 / int64 / bool（fp16/bf16 位模式无损传递）。

## 3. shape 策略（`prepare.sh --mode`）

| mode | parser_shape 规则 | 适用 |
| --- | --- | --- |
| `all_static`（默认） | 按实际 shape；batch 维按 `batch_size` 静态化 | 形状固定，kernel/融合最优 |
| `all_dynamic` | 维持 `[-1,...]` | 形状多变，免重编译，workspace 偏大 |
| `custom` | `overrides[name].dynamic` 指定维动态 | 动静混合 |

- `all_static` 的 batch 语义：`batch_size` 权威，数据沿第 0 维自动扩展/裁剪。
- 输出动态维无需手填：`io_config.outputs[].shape` 保留 `-1`，以运行时 `output_shapes.json` 为准。
- 换策略后必须重跑 `prepare_input.py`（parser_shape 烘焙进 `io_config.json`）。

## 4. GE 编译选项（逐项单变量）

| 选项 | 入口 | 说明 |
| --- | --- | --- |
| `CORE_NUM`（`ge.aicoreNum`，"AIC\|AIV"） | `run.sh --cores` | 限核 |
| `FORCE_16` / `ENABLE_HF32` | `test.sh` 环境变量 | 精度模式；默认关闭，须用户确认 + 精度门禁 |
| `ge.exec.precision_mode` / `op_precision_mode` | GE 选项 | 全局/算子级精度路由 |
| `ge.fusionSwitchFile` | GE 选项 | 融合开关（归因/回退） |
| `GRAPH_MAX_PARALLEL` | `run.sh --graph-max-parallel` | 图实例并行上限 |

- HF32 属 `runtime_config`（非精度模式），由 `model-recommend-core-limit-stress` 的 Stage 1 前置执行。

## 5. 图验证与缓存

- `--dump_graph` → `models/M<id>/.cache/dump_graph`（保留 3 份）；`fusion_result.json` 在 `.cache/run`。
- `kernel_meta` / `fusion_result.json` 同配置复用；切换 Pass/CORE/dtype/shape 后清理缓存再复测。
- `fusion_op_*.csv` / `op_summary_*.csv` / `api_statistic_*.csv` 等来自 `--prof msprof` 的 `mindstudio_profiler_output/`。

## 6. 精度与测量口径

- 精度：整型/bool 精确相等；浮点 `allclose` 默认 `rtol=atol=1e-3`（`verify.py --gate` 可按输出覆盖）。
- golden 优先级：用户 `reference/` → CPU onnxruntime → 报错；bf16 与自定义算子模型必须用户提供标杆。
- 统计：3 次取中位数、稳态窗口 2/4–3/4、首迭代不计入、噪声带 ±2%～±5%。
- 并发（`THREAD_NUM>1`）仅压测，不做 dump/精度验证/输出落盘。

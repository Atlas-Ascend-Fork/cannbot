# Optimize-State Contracts

`triton-npu-optimize-state` 的状态文件字段契约由两个 machine-readable JSON
文件定义，脚本（`scripts/baseline/contract.py`、`scripts/round/contract.py`）
直接加载它们作为唯一事实来源：

- [baseline-contract.json](baseline-contract.json)：`baseline/state.json` 的字段说明与状态枚举。
- [round-contract.json](round-contract.json)：`opt-round-N/round-state.json` 的必填/可选字段与状态枚举。

## 要点

### `baseline/state.json`

- 全部字段均为相对 `baseline/` 目录的路径或解析后的模式/状态值。
- `correctness_status` / `benchmark_status` 取值：`passed` / `failed` / `not_run`，
  仅在对应验证成功后才能写 `passed`。
- `bench_mode` 历史值（`standalone`、`msprof`）加载时会归一化为 `torch-npu-profiler`。
- 可选字段：`preparation_notes`、`baseline_repairs_summary`。

### `opt-round-N/round-state.json`

- 必填：`round`、`parent_round`、`hypothesis`、`correctness_status`、
  `benchmark_status`、`summary_path`、`opt_note_updated`。
- `benchmark_status=passed` 时还必须提供：`perf_artifact`、`comparison_target_path`、
  `effective_metric_source`（`kernel` / `total-op` / `mixed`）。
- 可选：`analysis_skipped_reason`、`profile_dir`、`ir_dir`、`perf_analysis_path`。
- 旧字段名 `comparison_target` 仅作 legacy 兼容读取，写入统一使用
  `comparison_target_path`。

字段的权威描述以 JSON 文件为准；修改字段语义时同步更新对应 JSON 与脚本。

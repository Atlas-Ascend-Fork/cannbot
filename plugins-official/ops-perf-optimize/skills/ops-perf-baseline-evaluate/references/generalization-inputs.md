# 泛化输入与冻结集合

泛化用例必须性能/功能合一：每条 case 同时包含性能采集所需的 shape/dtype/attrs 和可信 golden、比较器、阈值。用户提供时直接冻结；未提供时由 baseline 角色的通用 subagent 执行生成参考，默认生成 1000 条 L0，并调用：

```bash
python3 "$PLUGIN_ROOT/scripts/prepare_case_sets.py" attach-generalization \
  --manifest "$OUTPUT_DIR/run-manifest.json" \
  --cases "$GENERATED_GENERALIZATION_CASES"
python3 "$PLUGIN_ROOT/scripts/workflow_state.py" sync-manifest \
  --state "$OUTPUT_DIR/workflow-state.json" \
  --message "generalization cases attached"
```

竞品性能由文件提供：已有竞品文件在 freeze 时规范化为 `competitor-performance.csv` 并校验覆盖；创建时未提供时，可在泛化用例接入后用 `attach-competitor` 接入外部采集结果，将 `case_id,gpu_total_us`（或 `testcase_name,gpu_time_us`）规范化：

```bash
python3 "$PLUGIN_ROOT/scripts/prepare_case_sets.py" attach-competitor \
  --manifest "$OUTPUT_DIR/run-manifest.json" \
  --competitor-perf "$XPU_RESULT"
python3 "$PLUGIN_ROOT/scripts/workflow_state.py" sync-manifest \
  --state "$OUTPUT_DIR/workflow-state.json" \
  --message "competitor performance attached"
```

两次 attach 都是原子 manifest 更新。竞品缺 case、多 case、重复 ID、非正耗时或无法数值化时拒绝接入。

| 集合键 | 文件 | 规则 |
|---|---|---|
| `generalization_full` | `generalization-full-cases.csv` | 默认 1000 条或用户完整库存；最终性能与功能全集 |
| `competitor_performance` | `competitor-performance.csv` | 与泛化全集 ID 精确一一对应 |
| `baseline_performance` | `baseline-performance-full.csv` | 相同硬件与协议下的 NPU 全集基线 |
| `generalization_tuning` | `roundN/generalization-tuning-cases.csv` | 当前 `ratio < 1.0` 中最多 30 条 |
| `functional_acceptance` | `functional-acceptance-cases.csv` | 泛化全集中最多 40 条 L0 |
| `optimized_involved` | `optimized-involved-cases.csv` | 所有轮次实际调优 case 的去重并集 |

泛化全集同时登记为 `functional_full`，不得复制出语义不同的第二份功能全集。用例准备与竞品准备都为 `complete` 后才能采集 NPU 基线。

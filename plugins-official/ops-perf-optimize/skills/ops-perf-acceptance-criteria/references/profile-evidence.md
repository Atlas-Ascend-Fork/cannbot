# 报告采集与性能证据

工作流管理身份、采样与验收，测量通过 `ops-profiling-report` 的 [调用契约](../../ops-profiling-report/references/caller-contract.md) 执行。先取得测量绑定，再冻结计划。

## 策略

- 默认 `median_v1` 使用 `kind=profile_median_v1`：事前确定正整数 N、2N 个 slot 和双方身份。`frequency_policy=record_only` 记录频率，`rated` 则核对额定频率。完成后两份 CSV 直接按 manifest 汇总。
- 显式 `confidence_effect_v1` 使用 `kind=profile10_independent_v1`：最终候选稳定后注册每侧 10 次独立进程采集，顺序事前冻结；相同输入、设备、环境和测量协议，活动频率等于额定频率，两侧各满足 `(max-min)/median <= 10%`。工具 replay 与独立样本分开计数。
- confidence 的统计方法为 `python_mt19937_independent_medians_v1`，`difference_of_medians`、confidence=0.95、quantile=linear，预先固定 seed/draws。
- confidence 探索使用 `screened + provisional:true` 时，逐 case 提供双方 `screening_evidence` 报告收据；报告身份含 `execution_identity`、`input_snapshot`。复核每个 case 内双方输入，以及身份、headline、频率和协议。

## plan schema 1

文件收据为绝对路径 `{path,sha256}`，可附 `kind:file`。

| 字段 | 内容 |
|---|---|
| `kind/manifest/collection/effect_case_id/soc` | 策略 kind、manifest 收据、性能集合键、唯一 case、SoC |
| `baseline_variant/candidate_variant/identities` | 双方名称与身份 |
| `physical_device/logical_device/frequency_policy/rated_frequency_mhz` | 设备映射及频率策略；confidence 使用缺省 `rated`，该模式要求额定频率 |
| `device_binding` | 所选工具的运行时设备绑定，由 `report_contract.py --prepare --application-device` 返回；编号与 environment 整组使用，见[设备契约](../../ops-profiling-report/references/device-context.md) |
| `tool/protocol/report_context` | 报告入口提供的工具收据、协议及可选上下文 |
| `environment/snapshot/precision_policy` | 环境（含绝对 ASCEND_HOME_PATH）、逐输入文件 SHA 的 JSON 收据、原比较器策略收据 |
| `samples_per_variant/order` | N 与 2N 个 `{slot,variant,sample_index}`；slot 连续，每侧索引覆盖 0..N-1 |
| `statistical_method/retry_policy` | confidence 的统计方法；重试策略固定 `failed_without_published_report_only` |
| `reuse` | median 可选：`{版本名:{collection:{path,sha256},variant:原版本名}}` |

每版身份含 `execution_identity`、生成文件收据 `generated`、绝对 `runner` argv、`cwd`、`precision` 和报告入口所需的目标信息。解释器或包装启动器另附 `launcher` 文件收据，被测产物仍由构建/加载链验证。

精度收据含 status、case_id、source、input_snapshot、execution_identity、policy、returncode、comparison_log、actual_output。同版本同输入复用精度，后续采集使用纯性能 runner。

原版源码可用 `source_archive={manifest,original_source,original_snapshot}` 收据绑定字节等价的归档，或用相同 commit 与 `git-tree-v1` 树身份绑定 worktree。

## 采集、复用与恢复

```bash
python "$WORKFLOW_SCRIPTS/profile_evidence.py" --plan "$PLAN" --register "$REGISTRATION"
nohup python "$WORKFLOW_SCRIPTS/collect_profile.py" \
  --plan "$PLAN" --registration "$REGISTRATION" --out "$CAPTURES" \
  > "$DRIVER_LOG" 2>&1 < /dev/null &
```

注册收据独占创建并登记到 workflow-state。采集目录绑定 plan 与 registration；同计划恢复时复用成功 slot。每 attempt 保留命令、环境、起止时间、退出码及原件，逐 slot 落盘。

`reuse` 引用旧 median collection 的完整单侧样本，数量、该侧身份、输入、设备、环境、工具、频率策略和协议须一致；保留原 attempt 收据及 `reused_from` 来源，仅采缺少的一侧。新计划的注册冻结复用引用；新采样发生在注册之后。

已有原件的 `needs_review` 先恢复解析，原 attempt 和失败日志保存在 `recovery-*` 中；必要字段通过后继续采集。完整诊断报告按需生成。仅无已发布报告且无 export 原件的失败允许新 attempt。

正式样本还保存 `device_binding_file` 与 `target_process` 收据，发布和 proof 绑定这些证据。没有 `runtime_device_v1` 设备绑定的旧计划只允许原始诊断，不进入正式恢复或比较。

完成输出 `collection.json/baseline.csv/candidate.csv`。confidence 再构建 proof，复核原件、身份、独立进程、覆盖、时间顺序及中位数：

```bash
python "$WORKFLOW_SCRIPTS/performance_effect_evidence.py" \
  --plan "$PLAN" --registration "$REGISTRATION" --collection "$CAPTURES/collection.json" \
  --baseline "$CAPTURES/baseline.csv" --candidate "$CAPTURES/candidate.csv" \
  --case-id "$CASE_ID" --baseline-variant baseline --candidate-variant candidate --out "$PROOF"
python "$WORKFLOW_SCRIPTS/summarize_performance_effects.py" \
  --manifest "$RUN_MANIFEST" --baseline "$CAPTURES/baseline.csv" --candidate "$CAPTURES/candidate.csv" \
  --evidence "$PROOF" --out-json "$EFFECT_JSON" --out-csv "$EFFECT_CSV"
```

median 汇总省略 `--evidence`。同身份同协议完整证明可复用，集成身份变化后重新验证。多 kernel 取样由所选适配器按目标组成求和；MC²/多 rank 等无法确认完整覆盖的范围返回 unsupported/pending。历史证据按原协议恢复。

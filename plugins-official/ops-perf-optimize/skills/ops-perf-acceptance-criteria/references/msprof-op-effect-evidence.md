# msprof op 独立十样本确认

仅在最终候选稳定后使用。本适配器不占设备、不调用 profiler；探索阶段的合法单次 `Task Duration` 可继续作诊断，但不能冒充统计终选。冻结的 `confidence_effect_v1`、原 baseline 和旧 application collector 均保持不变。

完整确认是 **baseline 十次 + candidate 十次独立 msprof op 采集**，每次 `PipeTimeline`、`launch-count=1`、工具实际 warmup5、原两次 target call 和两次同步。数据来自 `OpBasicInfo.csv` 的唯一完整 mix 目标行；不伪造 application warmup 行，不相加 AIC/AIV pipe 时间。

## 使用顺序与 CLI

长采集执行纪律（20 slot 确认、全集 before/after 等）：由驱动脚本以 `setsid`/`nohup` 脱离会话进程组后台执行，逐 slot 写进度日志与独立 attempt 目录；驱动脚本必须跳过已存在 attempt 目录，中断恢复只补缺失 slot，不重做已完成 slot、不替换成功样本。禁止把整段采集放在代理前台单命令内执行。

1. 稳定候选，准备原始输入快照、原 BF16 输出裸字节参考、两个 variant 的真实 source/generated/build/load 身份。所有路径必须为绝对路径；引用严格为 `{ "path": "...", "sha256": "..." }`。
2. 写 `op-confirmation-plan.json`。固定下述 20 个 slot 和全部统计参数；不能在看结果后改顺序或选择样本。
3. 在实际采样前运行（`SCRIPTS` 为插件 scripts 的绝对路径）：

```bash
timeout 60s python3 "$SCRIPTS/msprof_op_effect_adapter.py" \
  --plan "$ROUND/op-confirmation-plan.json" \
  --register "$ROUND/op-confirmation-registration.json"
```

`--register` 拒绝覆盖已有收据。省略该选项只校验计划，不登记。将 plan 和 registration SHA 纳入现有 round 的工作流 artifact，不另建状态机。

4. 实施代理按 `order` 逐 slot 采集，每次用独立目录与真实 wrapper 起止时间、退出码、原件 SHA。必须先完成上一 attempt 才能开始下一次；不得同时占同一张卡。沿现场已验证的超时预算执行，所有 Python 外层加 timeout。失败的 nonzero-returncode attempt 可以保留在该 slot 的成功 attempt 前；成功样本不能因慢而替换。returncode=0 但缺行/缺频率/非法耗时的记录直接拒绝，不得改写为成功或悄悄删除。
5. 写下述 collection；用全部原始样本分别计算 median10，写两个只有 `case_id,total_us` 的 CSV。旧阶段的单次 baseline CSV 不改、不充当新 median10。
6. 构造 proof：

```bash
timeout 120s python3 "$SCRIPTS/performance_effect_evidence.py" \
  --plan "$ROUND/op-confirmation-plan.json" \
  --registration "$ROUND/op-confirmation-registration.json" \
  --collection "$ROUND/op-confirmation-collection.json" \
  --baseline "$ROUND/baseline-confirmation.csv" \
  --candidate "$ROUND/candidate-confirmation.csv" \
  --case-id sfa_full640 --out "$ROUND/op-confirmation-proof.json"

timeout 120s python3 "$SCRIPTS/summarize_performance_effects.py" \
  --manifest "$MANIFEST" \
  --baseline "$ROUND/baseline-confirmation.csv" \
  --candidate "$ROUND/candidate-confirmation.csv" \
  --evidence "$ROUND/op-confirmation-proof.json" \
  --out-json "$ROUND/effect-summary.json" --out-csv "$ROUND/effect-summary.csv"
```

多个逻辑 case 各有自己的 plan/proof；本版单份 op headline CSV 只承载该 plan 的一个 case。接入更大的全集前需要明确的按 case 汇集，不能悄悄放宽证明归属。

## 集成层复用规则

本适配器服务 demo 侧最终确认；回集成（integration）层默认不重跑 20-slot 全量确认，两全集 before/after 的效果证据由 `canonical10_independent` proof 承担（口径见 performance-jitter-policy 与 DSL 集成阶段文档）。

1. **复用条件**：回写字节一致性证明成立（集成后源码与 demo 验收实现逐字节一致，built 与 loaded 同 SHA）且源/编译/加载身份链闭合时，集成层效果结论 = demo 侧本适配器正式确认结论 + 集成层 canonical10 proof，不重复采样；绑定关系写入 effect summary 的 evidence_paths。
2. **边界**：回路由、编译分支或输入分布变化即新身份，字节等价不再成立，集成层必须重新确认；不得把 `msprof_op10_independent_v1` 改名或降级口径冒充集成层证据，也不得为凑集成层证据改写已登记 plan。
3. **登记时序不变**：集成层 canonical10 proof 仍走 `performance_effect_evidence.py` 事前 registration（早于全部 candidate 采集）；baseline 绑定既有冻结收据时在 plan 中显式声明其 manifest 路径与 SHA，不重采。
4. 逐 case 分类仍按冻结 `performance_effect_policy` 执行：小变化不因集成层复用而豁免配对确认，`inconclusive` 照常阻断最终 PASS。

## plan schema 1

```json
{
  "schema_version": 1,
  "kind": "msprof_op10_independent_v1",
  "manifest": {"path": "/absolute/run-manifest.json", "sha256": "SHA"},
  "collection": "performance_full",
  "effect_case_id": "sfa_full640",
  "soc": "Ascend950PR_957b",
  "physical_device": 3,
  "logical_device": 0,
  "rated_frequency_mhz": 1650,
  "protocol": {
    "profiler": "msprof op", "aic_metrics": "PipeTimeline", "launch_count": 1,
    "warmup": 5, "metric": "Task Duration(us)", "target_calls": 2,
    "synchronizations": 2, "warmup_time_included": false
  },
  "snapshot": {"path": "/absolute/immutable-input-snapshot", "sha256": "SHA"},
  "samples_per_variant": 10,
  "precision": {"status": "strict_pass", "rtol": 0, "atol": 0, "comparison": "raw_bf16_bytes_equal"},
  "output_contract": {
    "dtype": "bfloat16", "shape": [1, 4096, 64, 512],
    "reference": {"path": "/absolute/original-seed1-output.bf16.bin", "sha256": "SHA"}
  },
  "baseline_variant": "baseline",
  "candidate_variant": "candidate",
  "identities": {
    "baseline": {
      "kernel_name": "EXACT_OpBasicInfo_Op_Name",
      "block_dim": 28, "mix_block_dim": 56,
      "generated": [{"path": "/absolute/baseline-generated.cpp", "sha256": "SHA"}],
      "execution_identity": {"path": "/absolute/baseline-execution-identity.json", "sha256": "SHA"}
    },
    "candidate": {
      "kernel_name": "EXACT_OpBasicInfo_Op_Name",
      "block_dim": 28, "mix_block_dim": 56,
      "generated": [{"path": "/absolute/candidate-generated.cpp", "sha256": "SHA"}],
      "execution_identity": {"path": "/absolute/candidate-execution-identity.json", "sha256": "SHA"}
    }
  },
  "order": [],
  "retry_policy": "record_failed_attempts_then_first_success_no_valid_sample_replacement",
  "statistical_method": {
    "id": "python_mt19937_independent_medians_v1", "confidence": 0.95,
    "statistic": "difference_of_medians", "quantile": "linear", "seed": 2026, "draws": 100000
  }
}
```

`order` 必须填满 20 项。推荐对 `pair=0..9`，偶数 pair 按 baseline,candidate，奇数 pair 按 candidate,baseline；各项为 `{slot:0..19, variant:"baseline|candidate", sample_index:pair}`。每对各一 variant、每侧 index0..9、AB/BA各五对。顺序只用于控制位置偏差，统计仍为独立 bootstrap，不伪称 paired。

本适配器用于相对原始冻结实现的最终确认，不允许替换为某个上一轮候选。baseline execution_identity.source 默认必须精确等于 manifest.inputs.code。

如果集成会改动原 source root，应在注册 plan 之前使用字节相同的独立源码归档，并在 baseline identity 增加 `source_archive: {path,sha256}`，引用 preparation 的 extraction-manifest.json。该文件必须含 `schema_version:1`、`manifest`（与 plan 相同）、`original_source`（等于 manifest.inputs.code）和 `original_snapshot`（等于执行 identity.source）。归档 identity 除 path 外所有字段都必须与原冻结 identity 相同；source-tree-v1 的 SHA 覆盖相对文件路径及内容，因此不是只认一个自报名称。所有基线执行、build/load/precision 收据从开始就绑定归档。恢复验证会重算归档内容，而不要求已集成的原目录仍保持旧字节。不能事后重写已经注册的 plan；不要用软链接或硬链接代替独立归档。此映射只覆盖 source-tree-v1 选中的源码，生成代码、构建二进制及 loaded artifact 仍各自核验。

`rated_frequency_mhz` 必须在 plan 中冻结为实际额定频率，20 份原始 CSV 的 Current Freq 和 Rated Freq 都须等于该值。原始 CSV、run.log 和 runtime evidence 的 PID 必须一致；20 个成功样本 PID 必须全部不同，以拒绝复制同一 capture 冒充独立采样。本版保守拒绝真实操作系统 PID 重用，应记录失败原因后重新安排整组确认，不能改写 PID。

`execution_identity` 复用现有 schema1；每份只含当前 SoC。source 必须是实时 source snapshot；build.log 应包含 source/generated/built 的 SHA 归属，并保留真实编译来源；runtime.loaded_artifacts 必须与 build 匹配。不能用合成日志补生产证明。

## attempt schema 1

每个 `sample-XX/attempt-NN/attempt.json`：

```json
{
  "schema_version": 1,
  "slot": 0, "variant": "baseline", "sample_index": 0,
  "started_at": "ACTUAL_UTC_ISO_WITH_TIMEZONE", "ended_at": "ACTUAL_UTC_ISO_WITH_TIMEZONE",
  "protocol": {"COPY": "exact complete plan.protocol object; this placeholder is invalid"},
  "physical_device": 3, "logical_device": 0,
  "command": ["/absolute/msprof", "op", "--aic-metrics=PipeTimeline", "--launch-count=1", "ACTUAL_REMAINING_ARGS"],
  "returncode": 0, "status": "valid",
  "run_log": {"path": "/absolute/sample-00/attempt-00/run.log", "sha256": "SHA"},
  "op_basic_info": {"path": "/absolute/sample-00/attempt-00/OPPROF.../OpBasicInfo.csv", "sha256": "SHA"},
  "execution_identity": {"path": "/absolute/sample-00/attempt-00/execution-identity.json", "sha256": "SHA"},
  "precision": {"path": "/absolute/sample-00/attempt-00/precision.json", "sha256": "SHA"}
}
```

失败 attempt：真实非零 `returncode`、`status:"failed"`、真实起止时间/command/protocol/device/run_log 必填；产生了 OpBasicInfo 则保留引用。成功 attempt 必须是该 slot 最后一条且只有一次；不能把有效成功改写成失败。

成功 attempt 的 execution identity 必须对应本次实际加载。其 `targets[0].runtime.source_artifacts` 包含同一次 `run.log`、`OpBasicInfo.csv` 和保留输出裸字节的引用；runtime.evidence 指向的原始 JSON 除现有 method/source_artifacts/loaded_artifacts 外还需要：

```json
{
  "target_soc": "Ascend950PR_957b", "physical_device": 3, "logical_device": 0, "pid": 12345,
  "input_snapshot": {"path": "/absolute/immutable-input-snapshot", "sha256": "SHA"},
  "target_calls": 2, "synchronizations": 2
}
```

`pid` 必须是加载该代码并产生输出的被测进程实际 PID，并与 OpBasicInfo、run.log 中的 Pid 精确一致。非零退出若已经有完整有效 CSV 和 All task success 日志，也不能宣称失败后丢弃重采。

失败 attempt 可用 `raw_captures: [{path,sha256}, ...]` 保留所有已生成的原始 CSV；未生成文件时可为空数组。旧 `op_basic_info` 单文件字段继续兼容。适配器将所有失败原件纳入 SHA 依赖，任何一份含完整成功计时且日志显示成功都禁止丢弃重采。成功 attempt 仍只允许唯一完整目标 CSV；此字段不放宽成功多目标歧义。

这些字段必须来自实际观测。旧 runner 丢弃返回，不能凭已有功能验收填本次输出。可在计时外观测同一次返回并与原 BF16 位比较；不得增加/减少原两个目标调用或把拷贝/校验纳入被测 Task Duration。观测方法、输出归属和任何额外操作必须随 runtime 源证据保留审查。

`precision.json`：

```json
{
  "contract": {"status":"strict_pass","rtol":0,"atol":0,"comparison":"raw_bf16_bytes_equal"},
  "case_id": "sfa_full640",
  "input_snapshot": {"path":"/absolute/immutable-input-snapshot","sha256":"SHA"},
  "execution_identity": {"path":"/absolute/sample-00/attempt-00/execution-identity.json","sha256":"SHA"},
  "dtype":"bfloat16", "shape":[1,4096,64,512],
  "actual_output":{"path":"/absolute/sample-00/attempt-00/output.bf16.bin","sha256":"SHA"}
}
```

适配器实际读两个裸字节文件逐字节比对，不仅接受 `PASS`；参考文件大小须等于 shape 元素数×2。

## collection schema 1

```json
{
  "schema_version": 1, "kind": "msprof_op10_independent_v1",
  "plan": {"path":"/absolute/op-confirmation-plan.json","sha256":"SHA"},
  "samples": [
    {"slot":0,"variant":"baseline","sample_index":0,
     "attempts":[{"path":"/absolute/sample-00/attempt-00/attempt.json","sha256":"SHA"}]}
  ]
}
```

`samples` 必须按完整 plan.order 填满20项；attempt 和 raw capture 路径不得跨 slot 重用。实际时间必须严格晚于 registration，顺序无重叠。每侧 spread/median 不超过10%，headline 必须等于原始 median10。所有引用在 proof 恢复时重新校验。

当前只实现独立十样本大变化确认。原小变化规则、CI跨零、最终inconclusive门禁保持生效；小变化仍需已支持的真正paired证据，不能把本kind改名来冒充。930us绝对目标与相对baseline统计改善分别报告。

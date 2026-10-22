# 基线评估

本阶段由 baseline 角色的通用 subagent 执行，原工程只读。输入来自已确认 request，先运行预检，再 freeze/start；freeze 前的预检开始/结束时间来自原报告，不能事后伪造阶段耗时。状态初始化后登记预检、集合和目标证据。

## 环境与用例

调用 `preflight_dependencies.py --request <request>`，按 `ascendc-env-check` 核对必要依赖、NPU 型号/数量/设备初始化、CANN、Python、编译与性能工具。TTK 由预检统一接入：未找到 ops-test-kit 时自动 `git clone --depth=1` 上游最新到 `/tmp/ops-test-kit` 并校验可导入，随后把 TTK 仓自带 4 个标准 skill（`$TTK/.claude/skills/` 下的 `ttk-how-run-test`/`ttk-how-write-case`/`ttk-how-write-plugin`/`ttk-how-diagnose`）软链到当前部署客户端的 skills 目录（opencode→`.opencode/skills`，claude→`.claude/skills`，codex→`.agents/skills`，codearts→`.codeartsdoer/skills`，项目级与全局级均已存在的全部链接）；后续所有 TTK 操作直接加载这 4 个 skill。每个 `TARGET_SOCS` 必须有对应可用设备和环境证据，多机分别运行预检并汇总；不能用当前一张 950 卡证明 910b 可用。正式评估不得使用 `--skip-device` 或 `--skip-build`。无 fail 后 freeze；warn 的处理理由写入报告。

产出 `环境检查报告.md`：请求 SHA、真实设备与 SoC 映射、依赖版本/路径、检查状态、warn 理由、失败修复证据及 `preflight-report.json` 引用。不把“脚本存在”当作设备可用。

按 [input-freezing.md](input-freezing.md) 调用 `prepare_case_sets.py` 冻结集合；`existing/reuse_performance` 只用确定性脚本。需要生成时读取 [`case-generation.md`](case-generation.md) 与 `$PLUGIN_ROOT/workflows/prompts/generation.md`，加载 `ascendc-st-design`、`ops-precision-standard`，保留 standard L0/L1/L2 完整库存、generalization 默认 1000 条合一用例和最多 40 条 L0 验收子集；生成完成执行 attach 与 sync-manifest。基线评估完成前库存必须就绪。

## 被测实现身份

`performance_reference.kind=baseline` 时，从冻结源码通过工程现有构建入口生成独立产物，并证明运行时加载的是该次构建的产物。不得把已安装包、缓存扩展、系统 OPP 或历史工作区默认为当前源码实现；文件时间戳、包名、kernel 名和彼此无关联的 SHA 不能证明构建血缘。

每个 `TARGET_SOCS` 准备一个运行时加载证据 JSON，包含非空 `method`、可选 `target_soc`、原始 loader/process 证据，以及实际加载的目标实现文件：

```json
{
  "method": "process map or loader trace",
  "target_soc": "<TARGET_SOC>",
  "source_artifacts": [
    {"path": "/abs/path/to/raw-loader-evidence", "sha256": "<sha256>"}
  ],
  "loaded_artifacts": [
    {"path": "/abs/path/to/loaded/library-or-kernel", "sha256": "<sha256>"}
  ]
}
```

用统一脚本记录构建命令、完整构建日志、构建产物和加载证据；多个 SoC 对同一输出文件重复执行 `record`，最后执行 `validate`：

```bash
python3 "$PLUGIN_ROOT/scripts/validate_execution_identity.py" record \
  --manifest "$OUTPUT_DIR/run-manifest.json" --target-soc <TARGET_SOC> \
  --build-command '<exact build command>' --build-log <build.log> \
  --built-artifact <target-runtime-artifact> \
  --runtime-evidence <runtime-evidence.json> \
  --out "$OUTPUT_DIR/baseline/execution-identity.json"

python3 "$PLUGIN_ROOT/scripts/validate_execution_identity.py" validate \
  --manifest "$OUTPUT_DIR/run-manifest.json" \
  --identity "$OUTPUT_DIR/baseline/execution-identity.json"
```

脚本要求冻结源码未变、目标 SoC 覆盖完整、构建日志和产物可追溯，原始运行证据能定位加载路径或内容 SHA，并要求每个实际加载文件的内容 SHA 出现在本次构建产物中。若加载路径只能在首次调用时确定，可执行一次专用身份探针；该探针只生成加载证据，不作为功能、精度或性能结论。门禁通过后才运行正式 smoke test 和性能采集；身份不一致时修正构建或加载路由，不分析该实现的功能与性能。

同一源码、构建产物、加载证据、环境、runner 和用例身份均未变化时复用门禁及已有采集，不重新构建或测量。若身份已通过但原实现运行失败，本阶段只保留足以确认可重复失败及其最小对照的证据，随后返回明确 blocker；根因二分、阈值搜索和方案实验交由后续诊断或实施阶段。

## 对标选择与逐 case 目标

`performance_reference` 与 `optimization_objective` 分开：前者定义每例目标，后者定义停止轮数或达标指标。通过 `create-request --performance-reference <json>` 冻结，例如：

```json
{"kind": "theoretical", "target_ratio": 0.8}
```

`kind=xpu|theoretical|unfused|baseline`；`target_ratio=reference_us/target_us`，必须有限且大于 0。所有性能 case × 所有目标 SoC 都有独立记录，不只覆盖调优子集。多个来源用于不同目标时分开创建明确请求，不混合口径。

| 来源 | 执行与证据 | 目标 |
|---|---|---|
| `xpu` 其他算力卡 | 用户提供覆盖泛化全集的竞品性能文件（`case_id,gpu_total_us`，或 `testcase_name,gpu_time_us` 由脚本规范化）；记录实际 kernel/端到端计时边界、同步、输入与实现 SHA；不能假设单一采集协议适用于所有卡 | 对标卡耗时 / 目标比率；例如 ratio=1 表示不慢于对标卡 |
| `theoretical` 理论上限 | 加载 `ops-theoretical-performance-estimation`，逐 case 建模计算流、dtype、流量、指令/overlap/tiling 与硬件常量来源，保存模型 JSON 和原报告；当前技能仅支持 Ascend950 纯 Vector，其他芯片、Cube 或混合算子必须报告 unsupported，取得可信扩展模型或由用户选择其他对标后再继续 | 理论时延下界 / 效率，0 < 效率 ≤ 1；理论上限是吞吐上限，不是时延上限 |
| `unfused` 小算子 | 在独立目录编写 `unfused_reference.py`，保持原始运算序列/中间张量/精度/广播语义，禁用会把序列重新融合的编译路径；先用冻结 golden 验证，再加载 `ops-profiling` 实测整个未融合链及各小算子。记录启动次数、同步、临时分配和设备身份，按同一计时边界比较融合实现 | 融合前整链实测耗时 / 期望加速比（≥1）；不能把各步骤独立中位数相加冒充整链中位数 |
| `baseline` 原始实现 | 在原工程只读快照上按“被测实现身份”门禁构建并加载，再用现有入口采原实现全集；已有同一 execution identity 的性能证据直接复用，不提前做剥离或优化 | 原始耗时 / 目标加速比；旧请求默认比率 1，不凭空承诺收益 |

standard 的 xpu 来源与访问参数写入 `performance_reference` JSON（例如 `source_configuration`），不使用仅属于 generalization 的 `--competitor-*` 参数。泛化模式保留已有 `generalization.competitor` 与 ratio 1.0/0.6 合同；`performance_reference` 必须为 xpu，目标比例不能静默改变泛化退出门限。单纯 xpu 对比无需切换为泛化模式。

来源缺失、NaN、非正耗时、目标 case 不全时不能完成阶段。理论模型的误差/可达性与实测波动分别报告，不为“达标”调常量或改目标。小算子脚本是本次运行产物，不能写入被测原工程。失败分类延用工作流精度规则，缺少有效计时的既有失败仍显式列为未决，不伪造性能。

## 产物与门禁

先写 `target-evidence.json`，source_artifacts 是真实原始结果、模型/脚本、设备与协议清单的绝对路径：

```json
{"cases": [{"case_id": "case-001", "target_soc": "Ascend950", "kind": "theoretical", "reference_us": 10.0, "method": "已核验计算流和 roofline 模型", "source_artifacts": ["/abs/run/baseline/roofline_report.json"]}]}
```

```bash
python3 "$PLUGIN_ROOT/scripts/build_performance_targets.py" \
  --manifest "$OUTPUT_DIR/run-manifest.json" --evidence "$OUTPUT_DIR/baseline/target-evidence.json" \
  --out "$OUTPUT_DIR/baseline/performance-targets.json" --out-md "$OUTPUT_DIR/baseline/性能目标.md"
```

脚本拒绝遗漏/重复/多余 case 或 SoC、错误来源、无效比率与非正耗时；保存来源 SHA。主 Agent 审核来源确实适用，并将目标与其原始证据登记为 `phase.baseline` artifacts；原实现实测还必须登记 `execution-identity.json`，状态门禁会重新验证其全部依赖。目标在分析/实施/后处理一直只读，变化必须新建请求/run；后处理回路由后的实际结果仍对原目标判定，可为 NOT_FULLY_ACHIEVED。

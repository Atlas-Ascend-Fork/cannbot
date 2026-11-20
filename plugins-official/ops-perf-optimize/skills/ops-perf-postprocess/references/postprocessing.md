# 后处理与退化回路由

后处理是独立的通用 subagent 实例，读取文件交接：冻结目标/集合、workspace-manifest（仓库/基线 commit/worktree 身份）、兼容矩阵、最终保留 commit（final 标签）与 source-isolation gate、完整精度/性能证据。AscendC 输入按 [merge-protocol.md](merge-protocol.md) 合并交付，DSL 输入按本 Skill 的 DSL 步骤与 [dsl-integration.md](dsl-integration.md) 执行合并交付（final 标签合并回原工程，fast-forward 等价/并发变更分路与 AscendC 同构）；两种输入均保持原入口，已有独立 demo 也按同样方式合入原目录。

## 集成与芯片族保护

按 [merge-protocol.md](merge-protocol.md) 的合并交付流程，主 Agent 冻结 scope 后实施；共享 helper/tiling/kernel 在最终 commit 中以新增副本文件落地再接线，合并时逐文件 blob 一致性机器校验（合并结果与验收 commit 逐 blob 相等），替代人工逐行移植纪律。原始工程发生并发变化时走条件②全量复验路径，报告具体 diff 并重新审核映射，不能覆盖用户改动。

在合并和长构建前，对照最终候选实际 diff 与原工程路由检查隔离前提；信封中的门控描述只作为待核事实。范围或隔离不成立时先修复/返回裁决，不能凭“已验收”推迟到全集跑完才处理。原工程构建复用基线记录的工作目录与单算子命令，worktree/harness 的构建命令不能直接替代原工程入口。

芯片族归类统一查询 `npu-arch` skill，同一 NpuArch 为一族；实际 SocVersion、宏和构建路由从原工程/SDK 取证。在现有目标设备上完成全集验证并记录实际型号；审阅代码对同族资源差异的适配，不得新增具体型号或 SKU 白名单门禁，也不得将未测型号记为已验证。

硬件参数写死检查：回写范围内扫描核数、UB/L2/L0 容量、频率等硬件参数字面量（含 tiling 中的魔数与注释中的"当前平台取值"断言）。同一 NpuArch 内这些参数随子型号不同而变化，取值范围以 `npu-arch` 的硬件参数表（platform_config ini 口径）核对；写死即 finding，须改为运行时接口（PlatformAscendC / GetCoreNumAiv / GetCoreMemSize 等）获取或按实际能力/资源条件分派。判定细则可加载 `ascendc-performance-review` 的 PRC-ARCH-002。

未涉及芯片族的专属源码、构建选项、模板及传递依赖须零修改；共用 legacy 函数体/常量/布局原样保留，只在共享入口增加最小、可审阅的目标守卫。宏展开、include、实例化和链接也须隔离，不能只证明运行时 if 不命中。保存逐文件 SHA、范围 gate、原 fallback 可达性与编译链证据；没有非目标设备时标明静态保持与动态缺口，不谎称上板 PASS。

## 两套全集、两侧原工程身份

两套全集的检查范围按合并条件分路（判定与证据见 [merge-protocol.md](merge-protocol.md)）：条件①（fast-forward 等价，树哈希一致 + 重建产物 SHA 一致 + 按冻结回归验收子集的回归验证全 PASS）时原工程身份 == 验收身份，两套全集性能**免重测**，以 `merge-equivalence.json` 与证据复用清单登记（引用 final 标签 commit 的最终验收证据）；条件②（并发变更）时按下文全量执行。

1. 条件②下：以合并前目标分支 HEAD 构建原工程基线，合并后的原工程构建另一份产物；沿原调用入口运行，核验真实加载的二进制。两侧保持同一 SoC、设备/频率、CANN、用例、seed、golden、计时边界及缓存/采集协议。
2. 功能全集和性能全集都检查精度，并分别采集每个**可运行且会启动目标 kernel**的 case 的性能。目录形式功能库存按已冻结 manifest 枚举；保留所有原 ID 与输入映射，不替换或删 case。冻结库存中 `is_enabled=false` 且有 `expected_error` 的行必须在集成前后分别验证指定错误子串，记录 `PASS`、实际错误摘录与原始身份；这类行不产生目标 kernel 耗时，不得填入伪造的正 `total_us`。若诊断表明目标 kernel 实际启动，须调查该行而非直接豁免。两集合有相同 ID 时仅在完整输入/seed/语义也相同时复用同一结果；同名不同输入分别验证。
3. 精度沿冻结的原比较器或适用 TTK 入口；通过后使用 `--dry-run` 或等价 runner，由 `ops-profiling-report` 采集性能，MC² 的边界按 `ascendc-mc2-best-practice` 核对。一份相同源码/二进制/入口/集合/环境/协议证据只采一次；demo 与原工程身份不同必须实测，不能援引“不重复采集”跳过集成检查。
4. 每个目标 SoC 都用 `$WORKFLOW_SCRIPTS/validate_postprocess_performance.py` 检查两个集合的完整覆盖与逐 case 回退（条件②全量路径；条件①下本步骤由身份等价与 smoke 替代）；功能全集中的可运行行以旧/新耗时和源 CSV SHA 检查数值退化，预期报错行以集成前后错误结果文件检查冻结子串与 ID 覆盖。含预期报错行时必须传入下方两个 `--*-functional-errors` 参数；不得为了让数值门禁通过而删行、改冻结库存或伪造耗时。median 默认按两个集合各自的完整几何平均判定，单例退化作为明细；旧策略沿用其冻结回退规则。性能数值门禁不替代采集身份、源码安全和真实路由审阅。

```bash
python3 "$WORKFLOW_SCRIPTS/validate_postprocess_performance.py" \
  --manifest "$OUTPUT_DIR/run-manifest.json" --target-soc "$SOC" \
  --baseline-functional "$BEFORE/functional-performance.csv" \
  --candidate-functional "$AFTER/functional-performance.csv" \
  --baseline-functional-errors "$BEFORE/functional-expected-errors.json" \
  --candidate-functional-errors "$AFTER/functional-expected-errors.json" \
  --baseline-performance "$BEFORE/performance.csv" \
  --candidate-performance "$AFTER/performance.csv" \
  --out "$OUTPUT_DIR/integration/postprocess-performance-$SOC.json"
```

仅当冻结功能全集含预期报错行时传入两个错误结果参数；结果文件格式为 `{"results":[{"case_id":"...","status":"PASS","expected_substring":"...","error_excerpt":"..."}]}`，并精确覆盖这些行。没有预期报错行时省略两参数，原数值门禁口径不变。脚本输出在功能集合中分别记录可计时行的数值摘要和预期报错行的前后语义证据；后者不参与加速比或抖动统计。

功能/性能计时 CSV 的列约定为 `case_id,total_us`（泛化模式功能/性能合一）；非计时行不伪造正 `total_us`，host_only 行另见 `dsl-integration.md`。`validate_postprocess_performance.py` 的完整参数集：必选 `--manifest/--target-soc/--baseline-functional/--candidate-functional/--baseline-performance/--candidate-performance/--out`；可选 `--baseline-functional-errors/--candidate-functional-errors`（预期报错行的前后错误结果）、`--baseline-functional-host-checks/--candidate-functional-host-checks`（host_only 行语义证据）、`--baseline-functional-baseline-failures/--candidate-functional-baseline-failures`（原实现无法执行行的已知基线失败语义证据，注意参数名为双段 `functional-baseline-failures`，不存在 `--baseline-functional-failures` 这一形式）、schema2 gate 的 `--functional-effect-evidence/--performance-effect-evidence`（逐 case proof）与 `--functional-same-implementation/--performance-same-implementation`（同源码/构建/加载 no-op）。

## 需要回路由时

`route_required` 表示冻结策略要求修复整体或单例退化，结果始终保留逐例变化。以运行时可计算的 dtype/shape/attrs/format/模板条件求安全分区，形成 `regression-routing.md`：退化证据 → 条件 → 原 host/tiling/kernel/依赖入口 → 源码位置 → 边界验证。原代码指本次修改前原始实现，不是任意上一轮候选。按实际算法适用条件选择实现，不得将已测输入列表用作运行时白名单；禁止按 case ID/CSV 序号、测试标志或缓存的测量值分派。

无法精确表达单例条件时保守扩大 legacy 范围，必要时保留整个分支或全部原代码。不能把优化实现叫作 fallback，也不能仅修改对比 CSV。无论收益多少，新增路由都是新源码身份：冻结新的回路由 scope（记录旧 scope 和变更原因），重新做公开契约/源码隔离、真实构建、TTK 完整功能门禁与变更相关序列测试，然后复测两套全集。边界用例覆盖守卫两侧、别名/in-place、尾块和未涉及模板；附加边界不替代冻结集合。对同一最终身份仍有退化则继续收窄优化范围。

两个全集在每个目标 SoC 按冻结效果策略通过，且无新增/恶化精度失败，后处理才可完成。median 各全集几何平均 ≥1 即可，单例退化不自动要求回路由；legacy/confidence 沿用原规则。精度失败先定位真实问题，已知原始失败按 strict/conditional 保留。

## 交付与恢复

`VERIFY_REPORT.md` 汇总：两侧代码/二进制/入口身份、冻结范围与兼容矩阵、每个目标 SoC 两套全集的精度/性能 gate、逐 case 结果、回路由前后证据、守卫边界与原路径验证、非目标族未变证据、目标达成状态。新路由有独立版本目录，旧测量和 gate 不覆写。

回路由后的 ratio 从最终集成实测重新计算，内外层计数和未达标结论延续原规则。

最终原工程性能还须刷新持续报告：每个 SoC 使用其原工程集成前/后的性能全集 CSV 生成 effect 摘要，用 `$WORKFLOW_SCRIPTS/workflow_state.py mark --stage integration.performance.<soc> --status complete --selected-candidate <最终原工程身份> --performance-summary <摘要> --cumulative-performance-summary <同一摘要> --performance-scope full` 登记。显式注明 SoC 与原工程入口，不把最后的 demo `final.performance` 留作最终集成性能。功能全集的独立性能结果引用各 SoC gate，不与性能全集混算；多 SoC 的完整结果保留在各自证据与 VERIFY_REPORT 中，报告当前表只代表最近登记的那个 SoC。

未接纳优化时后处理交付 no-op 说明，仍检查原始身份覆盖两套全集的精度与性能；同身份证据可复用。CANN-Bench 只在用户要求时执行。归档保留最终保留 commit（两个后端统一为 final 标签）与最终原工程源码/路由差异；明确两者身份不同，交付结论以最终原工程为准。

## confidence全集门禁

`validate_postprocess_performance.py` 自动读取manifest策略。schema2 gate接收可重复的 `--functional-effect-evidence/--performance-effect-evidence`（每case一个proof）；同源码、同构建、同加载的真实no-op使用 `--functional-same-implementation/--performance-same-implementation`。规格与proof schema见 `ops-perf-acceptance-criteria/references/performance-jitter-policy.md`。两类全集分别按相同版本重算，proof必须绑定此次原工程before/after收据及当前SoC，demo或候选间proof不能直接挪用。header-only非计时行仍按原语义门禁检查。

稳定小回退为 `route_required`，需要真实谓词回原代码并完整复验；无有效回退但有 `inconclusive` 为 `confirmation_required`，不能写PASS。最终两个全集全部已确认或有同身份byte-identical依据才为 `pass`。旧gate schema1按legacy原算法重放；新gate、报告与state登记proof全部依赖SHA，任一改变失效。原精度、泛化ratio、非目标芯片族保护和路由审阅不变。

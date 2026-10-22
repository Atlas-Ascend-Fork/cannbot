# 后处理与退化回路由

后处理与前处理分别是独立的通用 subagent 实例，读取文件交接：冻结目标/集合、原源码快照、剥离映射、兼容矩阵、最终 demo 与 source-isolation gate、完整精度/性能证据。两种输入均回集成，原入口保持注册或直调；已有独立 demo 也按同样方式合入原目录。

## 集成与芯片族保护

按 [writeback.md](writeback.md) 的机械移植流程，主 Agent 冻结 scope 后实施；共享 helper/tiling/kernel 先复制再接线。原始工程发生并发变化时报告具体 diff 并重新审核映射，不能覆盖用户改动。

在回写和长构建前，对照最终候选实际 diff 与原工程路由检查隔离前提；信封中的门控描述只作为待核事实。范围或隔离不成立时先修复/返回裁决，不能凭“已验收”推迟到全集跑完才处理。原工程构建复用基线记录的工作目录与单算子命令，剥离 demo 的构建命令不能直接替代原工程入口。

芯片族归类（哪些 SocVersion 同属一族）统一查询 `npu-arch` skill，按其 NpuArch 代际划分归族（同一 NpuArch 为一族）；实际 SocVersion、宏和构建路由必须从原工程/SDK 取证。族别用于检查影响范围，不能替代精确 `TARGET_SOCS`：只验证族内某一型号时，不能自动启用同族其他型号的优化。

硬件参数写死检查：回写范围内扫描核数、UB/L2/L0 容量、频率等硬件参数字面量（含 tiling 中的魔数与注释中的"当前平台取值"断言）。同一 NpuArch 内这些参数随子型号不同而变化，取值范围以 `npu-arch` 的硬件参数表（platform_config ini 口径）核对；写死即 finding，须改为运行时接口（PlatformAscendC / GetCoreNumAiv / GetCoreMemSize 等）获取或纳入目标守卫隔离。判定细则可加载 `ascendc-performance-review` 的 PRC-ARCH-002。

未涉及芯片族的专属源码、构建选项、模板及传递依赖须零修改；共用 legacy 函数体/常量/布局原样保留，只在共享入口增加最小、可审阅的目标守卫。宏展开、include、实例化和链接也须隔离，不能只证明运行时 if 不命中。保存逐文件 SHA、范围 gate、原 fallback 可达性与编译链证据；没有非目标设备时标明静态保持与动态缺口，不谎称上板 PASS。

## 两套全集、两侧原工程身份

1. 以集成前原源码快照构建原工程基线，集成后的原工程构建另一份产物；沿原调用入口运行，核验真实加载的二进制。两侧保持同一 SoC、设备/频率、CANN、用例、seed、golden、计时边界及 warmup 协议。
2. 功能全集和性能全集都检查精度，并分别采集每个**可运行且会启动目标 kernel**的 case 的性能。目录形式功能库存按已冻结 manifest 枚举；保留所有原 ID 与输入映射，不替换或删 case。冻结库存中 `is_enabled=false` 且有 `expected_error` 的行必须在集成前后分别验证指定错误子串，记录 `PASS`、实际错误摘录与原始身份；这类行不产生目标 kernel 耗时，不得填入伪造的正 `total_us`。若诊断表明目标 kernel 实际启动，须调查该行而非直接豁免。两集合有相同 ID 时仅在完整输入/seed/语义也相同时复用同一结果；同名不同输入分别验证。
3. TTK 负责精度；性能按 `ops-profiling`，MC² 沿 `ascendc-mc2-best-practice`。一份相同源码/二进制/入口/集合/环境/协议证据只采一次；demo 与原工程身份不同必须实测，不能援引“不重复采集”跳过集成检查。
4. 每个目标 SoC 都用 `validate_postprocess_performance.py` 检查两个集合的完整覆盖与逐 case 回退；功能全集中的可运行行以旧/新耗时和源 CSV SHA 检查数值退化，预期报错行以集成前后错误结果文件检查冻结子串与 ID 覆盖。含预期报错行时必须传入下方两个 `--*-functional-errors` 参数；不得为了让数值门禁通过而删行、改冻结库存或伪造耗时。平均收益或达标 case 占比不能覆盖任何有效退化。性能数值门禁不替代采集身份、源码安全和真实路由审阅。

```bash
python3 "$PLUGIN_ROOT/scripts/validate_postprocess_performance.py" \
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

## 性能退化必须回原代码

`route_required` 返回全部有效退化 case。以运行时可计算的 dtype/shape/attrs/format/模板条件求安全分区，形成 `regression-routing.md`：退化证据 → 条件 → 原 host/tiling/kernel/依赖入口 → 源码位置 → 边界验证。原代码指本次修改前原始实现，不是任意上一轮候选。默认路径是 legacy，新路径仅对白名单中已验证条件启用；禁止按 case ID/CSV 序号、测试标志或缓存的测量值分派。

无法精确表达单例条件时保守扩大 legacy 范围，必要时保留整个分支或全部原代码。不能把优化实现叫作 fallback，也不能仅修改对比 CSV。无论收益多少，新增路由都是新源码身份：冻结新的回路由 scope（记录旧 scope 和变更原因），重新做公开契约/源码隔离、真实构建、TTK 完整功能门禁与序列压测，然后复测两套全集。边界用例覆盖守卫两侧、别名/in-place、尾块和未涉及模板；附加边界不替代冻结集合。对同一最终身份仍有退化则继续收窄优化范围。

直至两个全集在每个目标 SoC 都无有效性能回退，且无新增/恶化精度失败，后处理才可完成。抖动阈值仍用既有统一策略；不通过重采择优消除回退。精度失败先正向定位集成/候选问题，不以未经验证的 fallback 隐瞒；已知原始失败按 strict/conditional 保留。

## 交付与恢复

`VERIFY_REPORT.md` 汇总：两侧代码/二进制/入口身份、冻结范围与兼容矩阵、每个目标 SoC 两套全集的精度/性能 gate、逐 case 结果、回路由前后证据、守卫边界与原路径验证、非目标族未变证据、目标达成状态。新路由有独立版本目录，旧测量和 gate 不覆写。

generalization 保留涉及/不涉及用例的映射与抽检扩样（5% → 20% → 全量）作为附加路由检查；最终功能及性能全集已经覆盖全体，抽检不能替代。回路由后的 ratio 从最终集成实测重新计算，内外层计数和未达标结论延续原规则。

最终原工程性能还须刷新持续报告：每个 SoC 使用其原工程集成前/后的性能全集 CSV 生成 effect 摘要，用 `workflow_state.py mark --stage integration.performance.<soc> --status complete --selected-candidate <最终原工程身份> --performance-summary <摘要> --cumulative-performance-summary <同一摘要> --performance-scope full` 登记。显式注明 SoC 与原工程入口，不把最后的 demo `final.performance` 留作最终集成性能。功能全集的独立性能结果引用各 SoC gate，不与性能全集混算；多 SoC 的完整结果保留在各自证据与 VERIFY_REPORT 中，报告当前表只代表最近登记的那个 SoC。

未接纳优化时后处理交付 no-op 说明，仍检查原始身份覆盖两套全集的精度与性能；同身份证据可复用。CANN-Bench 只在用户要求时执行。归档同时保留经过验收的 demo、最终原工程源码与路由差异；明确两者身份不同，交付结论以最终原工程为准。

## 泛化涉及与不涉及路由核验

最终功能回归覆盖整个泛化全集。注册与直调输入回集成后，都先满足`ops-perf-postprocess` 的后处理规则两个全集功能和性能检查。以下分组与抽检保留为附加路由核验，不能替代全集检查：

- `optimized-involved-cases.csv` 去重后的所有 case 通过原调用入口全量回归；
- 对不涉及用例做代码 diff → TilingKey/执行路径映射，再按稳定 case ID 确定性抽检 5%，至少 10 条、不足 10 条时全选；
- 抽检失败扩大到 20%，仍失败则回归全部不涉及用例；
- 产出 `uninvolved-cases-verification.md`，记录映射、抽检 ID、结果和升级动作。

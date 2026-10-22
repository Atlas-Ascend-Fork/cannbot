# 最终优化回写

仅在独立后处理专家收到 `ROLE=integration` 时读取。注册与直调输入均沿原入口回集成；未接纳最终优化时回集成为有证据的 no-op。以下步骤不授予其他阶段修改原工程的权限。

## 输入与前置条件

1. `OPT_DIR`：Stage 3 归档的 `final_optimized/`，含 `ARCHIVE_MANIFEST.md`。
2. `REG_DIR`：原始输入工程（保留 REG_DIR 变量名兼容现有归档），就地集成。
3. `FUNCTIONAL_ACCEPTANCE_CASES`：冻结的最多 40 条 L0 功能验收子集。
4. `FINAL_FUNCTIONAL_REPORT`、`FINAL_PERFORMANCE_REPORT`：证明 OPT_DIR 已完成全量验收。
5. `RUN_MANIFEST`、`SOURCE_COMPATIBILITY`、`PRE_INTEGRATION_SNAPSHOT`：分别锁定 `TARGET_SOCS`、原工程支持 SoC/隔离风格，以及未修改的注册源码身份。
6. `VALIDATE_INTEGRATION_SAFETY`：插件的 `validate_integration_safety.py` 绝对路径。
7. `EXTRACTION_MANIFEST`：前处理的源码、依赖和注册入口映射；以及最终候选的 source-isolation scope/gate。

缺任一前置证据或 SHA 不匹配时停止并报告，不重新生成用例、不替代 Stage 3。

## 职责边界

本阶段只做：解析已接纳方案 → 冻结兼容性合同 → 忠实且代际隔离地移植 → 代码安全门禁 → 用原工程工具链构建/部署 → 当前模式规定的原入口功能回归与两类全集性能检查 → 报告。

不做：

- 再次运行工作工程功能全集；
- 把 demo 性能当作原工程回集成性能；身份完全相同的已有证据直接复用；
- 生成/修改功能用例，或在工作流规定范围外重新抽样；
- 重新选择性能算法方案；性能退化时按工作流生成可验证的原始代码回路由。

所有 TTK 环境校验、CSV 转换和原入口运行统一加载 TTK 标准 skill（`ttk-how-run-test`/`ttk-how-write-case`/`ttk-how-write-plugin`）。API 查询用 `ascendc-docs-search`；集成新增功能失败时用 `ascendc-precision-debug` 正向定位。

注册回集成沿用自定义注册工程的注册语义，直调保持原 launch ABI 和 runner，不默认做直调转注册。下面注册专用的 vendor/OpType/模板接线步骤仅适用于注册输入；直调按映射使用原构建/launch 规则，公用安全、精度与性能门禁不减。先读 `$PLUGIN_ROOT/workflows/references/source-isolation.md`，通过剥离映射定位原文件及工程接线；不能把 optimized 副本覆盖回公共 legacy 文件。

## 第一纪律：忠实移植

严格区分两类修改：

- 桶 A（已验证算法）：优化 kernel、公共库、tiling/选型逻辑及全部守卫/分支边界。逐行移植，只允许必要的 type/接口适配；不得重新推导算法。
- 桶 B（注册接线）：`DTYPE_X`、`GET_TILING_DATA_WITH_STRUCT`、`ASCENDC_TPL` 轴、TilingKey、`SetTilingKey`、op_def、host/launch ABI。只做机械、有界适配。

若发现自己在重写桶 A，立即停下并与 OPT_DIR 对照。选择性方案必须原样保留已验收运行时谓词、字段来源、路由优先级和历史最佳 fallback；禁止按 case ID/CSV 行号路由。后处理若发现有效退化，按工作流 postprocessing 参考另冻回路由范围，只将相应真实输入谓词切回原代码；新身份完整复验，不能混入未经验证的算法。

## 第二纪律：验证范围不是支持范围

先做集合比较：`TARGET_SOCS` 是本次真正完成构建、功能、性能验证的集合；`SUPPORTED_SOCS` 必须从目标工程 build config、`SocVersion` 路由、架构目录和入口分派取证。不得用当前设备或 A5 工作基线推断工程只支持 A5。

共享代码被多个 SoC 或模板分支使用时，必须先复制再单独路由；本次用例不涉及的模板也必须保持不变。若 `SUPPORTED_SOCS - TARGET_SOCS` 非空，按目标工程已有风格做代际隔离：

- kernel 优先放入工程既有 target 架构目录/编译宏分支，新入口只在 target 编译或分派；legacy kernel 保持不变且对非目标 SoC 可达；
- host tiling 先按工程既有 `SocVersion`、TilingKey 或 build config 选 target 路由；A5 专用 UB/核数/VF 模型不得覆盖共享 legacy 计算；
- 共享入口文件只允许增加 target guard + legacy fallback 接线；不得把已验证 A5 函数体直接替换原共享 tiling/kernel。

不能从源码证明 target guard 和 non-target fallback 时停止；没有非目标硬件不是放弃隔离的理由。

## Stage A：计划

完整读取 `ARCHIVE_MANIFEST.md`、最终功能/性能报告和两侧代码，产出 `REG_DIR/docs/perf-integrate/INTEGRATION_PLAN.md`，至少包含：

- 接纳方案、OPT_DIR/代码/二进制 SHA；
- 桶 A 文件与逻辑清单；
- 桶 B 接线点：模板轴、TilingKey、TilingData、host 路由、kernel 入口、workspace；
- 路由谓词、字段来源、fallback 和优先级；
- 构建/部署入口；
- 功能验收子集路径、数量和 SHA。
- `REG_DIR/docs/perf-integrate/SOC_COMPATIBILITY_MATRIX.md`：每个工程支持 SoC 的源码证据、是否属于 `TARGET_SOCS`、验证证据和最终 tiling/kernel 路由；
- 公开契约面清单及 pre-integration SHA；
- 目标工程代际隔离风格证据、所有将修改的共享 host/kernel 文件、逐文件 target guard 与 non-target fallback 计划。

兼容矩阵中未上板的 SoC 标记 `not_verified_preserved_by_isolation`，不得写 PASS；每代的 host/kernel 路由与 fallback 分别留证。

同时写 `integration-safety-scope.json`，严格使用 `validate_integration_safety.py` 的 schema：`target_socs` 与 `verified_socs` 必须等于 manifest 的 `TARGET_SOCS`；`supported_socs` 每项带源码证据，并与脚本从未注释 `AICore().AddConfig(...)` 自动发现的集合精确一致；存在未验证 SoC 时填写项目隔离风格、path markers、route tokens 和每个共享变更文件的双路由证据。非 `AddConfig` 工程仍须人工交叉检查 build config、`SocVersion`、架构目录和入口，不能因自动发现为空就把支持集合报成只有 target。计划阶段不得预填尚不存在的集成后行号，集成完成后再补齐并运行门禁。

另按完整原算子树的独立快照生成 `source-isolation-integration.json`，由主 Agent 审阅并冻结 SHA 后实施；记录源码/构建输入、最小接线范围、新增副本及未涉及模板保护。范围基于原工程重新映射，不能直接复用工作工程行号，也不能在集成后扩大范围。

详细机械规则见 [`integration-mechanics.md`](integration-mechanics.md)。

## Stage B：集成与构建

1. 新增目标实现副本并修改最小路由；仅有明确使用者证据的目标专属、涉及用例实现才允许原地修改。共享实现和未涉及模板不因归档结果通过而获得替换权限。
2. 桶 A 逐行移植；桶 B 适配 register 接口。新 TilingData 的 host/kernel 字段顺序、类型和对齐必须一致。
3. `ASCENDC_TPL_ARGS_DECL` 与 `ASCENDC_TPL_SEL` 取值一一对应；kernel 分派、host `SetTilingKey` 和 TilingData 类型一致。
4. 用 tiling 阶段真实可计算量表达谓词；保留非目标场景旧路径。
5. 公开契约零修改：禁止改变 `op_api/`、op def/proto、infer shape、API 签名、原有 shape/attr 检查、支持 dtype/format；优化 kernel 支持更多类型也不能扩大声明。
6. 用同一份完整算子注册树的集成前后独立副本运行 `validate_integration_safety.py --manifest "$RUN_MANIFEST" --baseline ... --candidate ... --scope ... --isolation-scope <source-isolation-integration.json> --out ...`。脚本核对冻结目标、支持集合、双路由证据和冻结文件/行范围；主 Agent 复核 scope SHA 及调用链/编译隔离，`decision != pass` 时禁止构建、部署或进入 Stage C。
7. 用注册工程自带工具链构建和部署 vendor 包。先只读发现 `build.sh --help`、README/CI 与单算子 target；不得自造 CMake/staging/部署脚本或静默全仓构建。
8. 不修改共享 CANN SDK。清理仅限本算子受管 build 产物与已确认的旧 vendor 部署，目标不明时停止。

内置同名算子导致 vendor 路径无法验证时，按 `integration-mechanics.md` 的命名四位一致规则创建独立同级 `<op>_custom/` 验证副本；交付目录保留原 OpType，验证结束删除临时副本。

门禁：`integration-safety-gate.json` 为 pass、编译成功、vendor 包部署成功、移植 diff 与计划逐项对应。测试只覆盖 target SoC 时，不能用测试结果替代非目标路由的静态隔离证据。

## Stage C：原入口功能回归与性能检查

1. 加载 TTK 标准 skill（`ttk-how-run-test`）校验环境，注册输入把冻结用例转换为 aclnn 模式，直调输入沿原 runner/TTK 模式；不改变 case/golden/阈值。解析 `result.csv` 的功能/精度状态；性能另由统一 `ops-profiling` 协议采集，不能把 TTK perf 列替代规范性能证据。
2. 先通过原入口执行 `FUNCTIONAL_ACCEPTANCE_CASES` 全部 case，再完成工作流规定的功能全集与性能全集精度检查。允许分批，但实际并集必须等于各冻结集合。
   泛化模式还须按主工作流执行全部 `optimized-involved-cases.csv`，并对未涉及用例完成 diff-to-route 映射及固定种子 5% 抽样（至少 10 条，不足则全量）；失败扩大到 20%，仍失败再全量。不能把 standard 子集误当作泛化回集成的全部验收范围。
3. FAIL 按顺序定位：
   - 先比对注册路由、守卫和 TilingData 与 OPT_DIR；
   - 再区分构建/部署/内置同名派发问题；
   - 最后才用 `ascendc-precision-debug` 定位真正的集成新增 kernel 问题。
   `OPTILING_FAILURE`、kernel-not-found 属于构建/接线排查；`NO_OUTPUT`、`VEC_ERROR` 或 vendor kernel 未加载时优先核验内置同名派发，不直接认定为数值问题。
4. 修复只能针对集成差异；不得放大阈值、删除 case 或重写算法。有效性能退化范围必须回原代码，交主 Agent 重新冻结范围并验证；代码变化后重编、重跑完整功能门禁与序列压测、两个全集精度和性能。

门禁：当前模式规定的注册回归范围 100% 覆盖，按共享验证 strict/conditional 策略判定，无集成新增或恶化失败。已有基线失败须引用同身份复现证据，不误报为新增失败，也不隐藏新增失败。demo 全量报告只作为前置证据；原工程的新身份必须完成两类全集逐 case 性能比较与精度验收，完整覆盖和性能检查由后处理调用方执行，本技能返回原工程构建/接线证据。

## 输出

产出 `REG_DIR/docs/perf-integrate/VERIFY_REPORT.md`：

- 集成计划与实际修改文件；
- SoC 兼容矩阵、项目隔离风格、target 路由和 non-target fallback；
- 公开契约 diff 和 `integration-safety-gate.json` 结论；
- 桶 A 保真对照、桶 B 接线对照；
- 构建/部署命令和结果；
- 功能验收子集期望数、实际数、逐 case PASS/FAIL、代码/二进制/用例 SHA；
- 泛化模式涉及用例全量回归和未涉及用例静态映射、抽检及扩样证据；
- 修复过的集成差异和遗留问题；
- 对 Stage 3 最终功能/性能报告的引用，注明 demo 与最终原工程身份、两套全集性能 gate 和退化回原代码后的复验证据。

安全门禁、构建/部署、两类全集精度/性能或必要回路由复验未完成时不得声称集成成功。非目标 SoC 未上板只能报告静态隔离保持 legacy；conditional 结论须显式列出已有基线失败。

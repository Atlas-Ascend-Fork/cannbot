# CANNBot-DSL 共享验证与领域边界

仅 `configuration.backend=cannbot_dsl` 适用。三部分按场合查阅：功能入口与编译门禁始终遵循「共享验证契约」；编译取证、缓存/调试与性能取证时查「编译与执行边界」；核验 API、编程模型或样例事实时查「文档与样例检索」。

先记录实际安装包版本/来源、CANN/毕昇、精确 SoC、原 Python 入口与 JIT/AOT 模式；使用派发的 `DSL_REPO_ROOT` 定位同版本文档、samples 和 test；仓库只作参考，候选运行不得通过其 PYTHONPATH 偷用原实现。当前事实不自动跨版本成立。

DSL 代码与文档不限单一来源；官方站点 [编程模型](https://cannbot-dsl.gitcode.com/programming-model/)、[API](https://cannbot-dsl.gitcode.com/api/) 仅是可能的参考。判定标准是附带材料说明了如何编译、运行与跑 case：本地优先检索 `DSL_REPO_ROOT` 与安装包实际携带的文档、samples 和原测试（目录名先实际定位，不假定固定布局）；外部页面不可读或与安装包不一致时记录限制，查安装包实现，不编造 API。

## 领域边界

- 普通 Python 对外调用 `@host`；Kernel 启动遵循实际安装包的调用约定。区分构图期 Python 值、专门化配置和设备运行期值；源码短不代表设备指令少。
- Channel 选槽不等于等待或调度。依据 Tensor 访问、槽位生命周期和生成同步检查依赖；不能仅统计 produce/consume 次数判断正确性。
- 资源按物理布局、capacity、depth、scratch 与并发存活期计算；容量取自目标平台，不硬编码文档中的示例数字。
- API 与数值约束从当前文档/安装包/样例核验。AscendC 代码可解释机制，不能替代 DSL 能力或编译证据。
- `ascendc-perf-optimize` 提供公共诊断方法；`ascendc-performance-best-practices` 按语言、架构和计算模式查询实践。领域事实只在本文引用，性能经验维护在族级知识库。

## 共享验证契约

保持原冻结集合、精度阈值、源码隔离、抖动规则及五阶段状态协议。原 pytest/checker/golden 是功能真源；原测试使用 TTK 时保留 TTK。纯 Python/JIT 不要求改造成 OPP 注册工程；原工程包含 Native/AOT、C++ 扩展或注册入口时，沿实际入口保留对应构建与集成检查。

### 编译证据

在确认的 Python/CANN 环境运行 `$WORKFLOW_SCRIPTS/dsl_evidence.py environment --out <path>`。环境文件保存真实包源文件和编译器二进制身份；preflight 保存其身份，后续正常候选使用同一工具链。升级环境必须记录决策、失效受影响证据，不能静默复用。

前处理、最终实施和后处理交接必须含 `dsl-compile-evidence.json`，由 `dsl_evidence.py validate --manifest <path> --evidence <path> --stage <role>` 验证；状态脚本在阶段 complete 时执行同一检查，并登记依赖。运行期间归档临时 `.so` 和原始加载记录，不能等待进程退出才取证。

文件身份为 `{path:绝对路径, sha256:文件SHA}`。证据 schema 1：

```json
{
  "schema_version": 1,
  "backend": "cannbot_dsl",
  "stage": "implementation",
  "manifest": {"path": "/run/run-manifest.json", "sha256": "manifest SHA"},
  "dsl": {"repo_root": "/reference/repo", "entrypoint": "flash_attn.flash_attn:flash_attn", "execution_mode": "jit", "workload_scope": "network_cases"},
  "source": {"path": "/run/candidate", "kind": "directory", "sha256": "code_identity 输出", "file_count": 1},
  "environment": {"path": "/run/dsl-environment.json", "sha256": "environment SHA"},
  "collection": "performance_full",
  "variants": [{
    "id": "selected-variant",
    "target_soc": "Ascend950PR",
    "case_ids": ["network-case-1"],
    "compile_config": {"path": "/run/evidence/config.json", "sha256": "config SHA"},
    "generated_sources": [{"path": "/run/evidence/kernel.asc", "sha256": "generated SHA"}],
    "build_log": {"path": "/run/evidence/build.log", "sha256": "log SHA"},
    "built_artifacts": [{"path": "/run/evidence/program.so", "sha256": "binary SHA"}],
    "runtime_evidence": {"path": "/run/evidence/runtime.json", "sha256": "runtime SHA"}
  }]
}
```

`source` 使用 `prepare_case_sets.code_identity` 的完整输出，不手写字段。`compile_config` 至少有 `source`、`environment` 两个相同身份，`entrypoint`、`execution_mode`、`target_soc`、`target_arch` 和 `parameters` 对象；parameters 记录参数规格/shape/stride、tiling、分支与数值模式。构建日志须包含对应源码树、config、生成代码和产物 SHA，以及真实构建命令/结果；这些绑定收据应由 harness 在编译期间生成，不由 Agent事后编造。

`runtime_evidence` 采用 `validate_execution_identity.py` 的 `method/source_artifacts/loaded_artifacts` 格式，另有精确 `target_soc` 与相同 `compile_config` 身份。原始运行记录必须识别实际加载路径/符号/SHA；归档路径与加载路径不同时记录两者及相同 SHA。只有 built 与 loaded SHA 一致才放行。JIT 必须有生成代码；AOT 没有生成代码时仍需要包构建/导出和实际二进制证据。

variants 的 case×SoC 并集必须恰好覆盖冻结 collection 中需要设备执行的行。库存可显式声明 `execution_kind=device|expected_error|host_only`，缺省为 device，有 expected_error 时默认 expected_error。expected_error 行冻结错误子串；host_only 行冻结 host_assertion 或 pytest_nodeid。这些正常通过的非设备检查不要求伪造编译/加载变体。

有非设备行时追加 `non_device_evidence` 文件身份，其 results 精确覆盖非设备 case×SoC：每条记录 case_id、target_soc、execution_kind、status=PASS、raw_evidence 文件身份；expected_error 另含匹配的 expected_substring/error_excerpt，host_only 另含匹配的 assertion。编译 gate 只证明该检查的独立证据，不把其标为设备执行。性能库存只使用实际设备 case；原测试中的非设备检查保留功能覆盖和原预期报错验证，不要求 NPU 耗时。

前处理使用 functional_acceptance；最终实施与后处理使用 performance_full，功能全集另有完整运行证据。每轮候选分别记录覆盖调优库存的证据，不能借终选产物冒充被淘汰候选的执行结果。

### 功能与稳定性

原测试 nodeid、seed、输入分布、golden/比较器/容差冻结，并映射到库存 case_id。pytest 的 skip/xfail、测试收集成功、进程 exit 0 不等于覆盖通过；报告实际执行及输出比较结果。测试命令只在运行副本上 import 候选。以 functional-acceptance.md 和 acceptance-run-manifest.json 交接，至少含命令、case/nodeid 映射、源码/编译/加载/工具链身份、逐例判定与原日志路径。

strict 基线要求原 PASS case 仍 PASS；原已知失败经同 case/seed/环境证实且不恶化才能 conditional。新增失败只修复/淘汰该候选。依赖变更或新代码重新验证；不换 golden、不放宽容差。数值诊断优先 DSL 调试/编译/布局/同步依据；AscendC 排障只在后端生成代码问题被确认时按需使用。

至少检查本次变更相关的单 tile、尾块、槽位 wraparound、重复调用/shape 交替、原支持的动态 shape/stride、metadata 重用/更新条件；不凭程序短删除覆盖，也不生成未请求的泛化全集。

### 正式性能

加载 [统一性能采集](performance-collection.md) 和 [抖动规则](performance-jitter-policy.md)。DSL 按同一 sample 全部相关 target launches 聚合，正式终选使用共享中位数口径，不混用样例 README 的 min。Cube/Mix 不用单独 aiv_time 代替完整 Task Duration。

JIT 编译/加载在正式样本前完成。优先用 `cbd.compile` 准备程序；若必须执行目标初始化或 prime，使用 ops-profiling 的可声明非计时 launch 路径，登记角色与预期拓扑。不得偷偷发射未映射的目标 kernel，或在解析时按顺序/名称删除它。正式调用中意外出现重新编译、debug 回读或未声明 launch 时采集无效。

设备计时、必要的接口端到端计时、编译耗时分开记录；metadata/workspace 的范围按冻结的原入口确定。同 shape 的真实稀疏/量化数据与调度配置不能替换为更容易的分布。诊断探针只用于证明对应假设，不参加候选排名。

### 公开接口与隔离

Python 签名、返回结构、shape/dtype/layout、输入检查、默认参数、stream、metadata ABI 和支持范围属于公开契约，即使与 Kernel 同文件也要逐项审阅。公共文件按真实影响确定 scope；目标源码可以整体改造，不强迫构造虚假 C++ 模板。非目标路由/接口仍保持原行为，路由只能依赖合法输入元信息，不能依赖测试 id、随机种子或 golden。

## 编译与执行边界

当前文档与安装包可观察的路径是 Python → CANNIR/MLIR → 生成 AscendC → 毕昇产物 → 加载执行。工具选项与内部对象可能随版本变化，适配器先查当前包，不将内部字段当作长期公开 API。

### 可核验的身份

记录完整 Python 依赖闭包、host/Kernel 编译期配置、TensorSpec/Dim/stride、目标架构、包版本与文件身份、CANN/毕昇、影响编译的环境、生成代码、构建日志、实际加载产物。每个 case 映射到实际编译变体和全部相关 launch。

当前安装包有进程内及可选磁盘缓存。磁盘缓存文件不必是实际 dlopen 路径；进程私有副本或临时产物会被清理。运行中取证实际加载路径、符号与 SHA，并在释放程序对象或进程退出前归档产物和日志。不要只哈希目录中任意 `.so`。

### 诊断与正式测量

当前安装包提供 `CANNBOTDSL_DUMP_MLIR`、`CANNBOTDSL_DUMP_ASCENDC` 和 `CANNBOTDSL_DUMP_DIR`。相关 dump/print/reuse 开关可能旁路缓存。诊断产物须记录独立配置；正式候选关闭诊断开关，以正常编译/加载身份重新验证。只有源配置与生成结果建立对应后，诊断证据才能解释正式版本。

`CANNBOTDSL_REUSE_ASCENDC` 可帮助验证后端假设，但手改 `.asc` 不是最终 DSL 交付。最终必须将优化落实到 DSL 或其明确授权的编译配置，并证明重新编译仍成立。

Channel 路径依赖自动同步；不能通过关闭 `CANNBOTDSL_AUTO_BUFFER_SYNC` 获得看似更快的候选。调试屏障、`cbd.print`、dump_tensor/dump_reg 和设备周期插桩会改变行为，不能混入正式性能样本。数值开关、FTZ、HF32、累加/舍入位置沿原契约保持。

先编译/加载再开始稳态测量。分别保存首次编译成本、设备 Task Duration，以及原目标需要时的端到端耗时；不得相互替代。运行模式、缓存状态、预热与所有相关 kernel 的范围在比较前固定。

### 修改后的证明

| 假设 | 编译/运行核验 |
|---|---|
| 常量外提减少设备标量计算 | 生成代码确实减少对应指令/表达式；Python 局部化本身不证明收益 |
| Channel 加深提高重叠 | 预取/消费/排空顺序、物理资源和同步成立；profiling/trace 显示目标空档缩短 |
| VF 融合减少 UB 中转 | 生成代码中间读写减少，原数值及跨 VF 依赖成立 |
| 减少专门化 | 编译变体数减少，动态 shape/stride 和路由边界仍通过 |

生成代码只能证明实现发生变化，性能仍以上板同协议证据判定。

## 文档与样例检索

以派发的 DSL 仓库为根，先读取 README 配套说明、CHANGELOG 与目标样例 README。DSL 代码与文档不限单一官方仓库；判定依据是附带材料说明了如何编译、运行与跑 case，而不是代码来自哪里。记录 revision 和实际阅读文件 SHA；文档描述的版本不能替代安装包版本。若文档与包实现矛盾，标记差异并用同环境最小编译/运行核验。

| 当前问题 | 本地编程模型 | API / 实现与样例 |
|---|---|---|
| 入口、Kernel 启动、辅助函数 | `introduction.md`、`code-generation.md` | `docs/api/decorators.md`（先定位实际文件）、目标入口和 host 方法 |
| 静态/动态参数、shape/stride 专门化 | `jit-arguments.md`、`control-flow.md` | host/data-description、control-flow；`flash_kda` 的参数规格 |
| 布局、物理存储、尾块搬运 | `data-and-layout.md`、`type-system.md` | types-and-views、memory movement；核验完整容量及 stride |
| Buffer、Channel、流水与生命周期 | `onchip-memory.md`、`synchronization.md` | types-and-views/channel、buffer、resource-management；`flash_attn` 的数据交接 |
| Cube、Vector、Mix、SIMT | `compute.md`、`vector-registers.md`、`cube-and-mix.md` | cube_compute、reg_compute、目标 sample 的实际选路 |
| metadata / AI CPU 调度 | `aicpu.md` | 原主算子及配套 metadata 的私有 ABI、同 stream 顺序、复用条件 |
| 编译、缓存、生成代码、调试 | `compiler-options.md`、`debugging.md`、`limitations.md` | 安装包 compiler、env、channel、runtime；见 [编译与执行边界](#编译与执行边界) |

API 文件名随来源与版本变化：先 `rg --files docs/api` 定位，不把上述目录名当作稳定接口。引用到报告时说明是文档事实、包实现事实、源码设计、已编译验证还是已上板验证。

### 按阶段交付知识上下文

基线交付环境与原入口；分析引用实际选路、资源与同步事实；实施逐个核验所用 API 和预期编译变化；后处理核验原入口、metadata、缓存与回归范围。各阶段消费原始文件路径，不依赖上一代理的会话记忆。

网络 case 必须包含决定工作量的值与分布：稀疏长度/块索引、页表、有效序列长度、mask、量化 scale、metadata 配置等。相同 shape 不保证相同路径或负载。

# DSL 实施验证

先读本轮 analysis（含 `ascendc-performance-review` 的方案净收益评估 `references/dsl-benefit-assessment.md`）、exact/forbidden 契约、冻结 scope、原/当前基线与映射；共享验证与领域边界见 [cannbot-dsl.md](../../ops-perf-acceptance-criteria/references/cannbot-dsl.md)。核对 scheme_id 与评估条目、冻结 case/SoC、计时范围一致且为 ready_for_implementation；缺少评估或安全/同步关键未知未完成诊断时返回 analysis，不自行把 probe/deferred 方向作为正式候选实施。每方案独立物理副本与证据，不修改原工程、测试真源或 SDK。

## 候选门禁

1. 核验 backend、case/SoC、入口及 required_features。启用 schedule_policy 时先消费 [调度契约](../../ops-perf-acceptance-criteria/references/async-schedule-contract.md) 的候选身份、scope、模型与检查报告；核对 A1 独立程序、A2 约束与 A3 假设，不以 MODEL_FEASIBLE 代替实施就绪。普通局部修改只在相同身份/覆盖且有已验收依据时复用契约。先从真实 DSL sample/已核验实现查相同机制；AscendC 范例只解释算法与硬件，DSL API 由当前版本取证。
2. 按方案修改 Python/tiling/流水。记录 Buffer/Channel 物理布局、capacity×depth、scratch、生存期和资源预算；检查尾块、预取/排空、CrossCore、VF 内依赖和数值顺序。静态容量包含未命中分支仍被编译分配的 buffer；初始化/排空包含未激活通道的 token，不能只审活动任务。不关闭 Channel 自动同步，不用调试 barrier 掩盖错误。
3. 编译诊断副本，核验常量、循环、发射顺序、同步和中间读写是否符合 expected changes。逐 task/edge/buffer/event 映射到真实生成代码：确认每个程序提交顺序、wait/set 的 pipe 与 generation、最后读者、分支计数、启动/排空以及 alias 复用。编译器插入或移动同步时更新事实并重新核验，不能只凭 DSL API 名称判 pass。正常配置构建正式候选并取证实际加载产物；源码或配置变化即新候选。手改 .asc 的实验不能直接交付。
4. 执行源码隔离、schema 3 conformance 与 dead-code 审阅；Python public wrapper 与 Kernel 同文件时审阅签名、检查、输出和原支持范围。pass feature 引用真实 .py:line 与编译/运行证据。UNKNOWN 不等于通过。
5. 用原 pytest/checker/golden 运行冻结 functional_acceptance，记录逐例 strict/conditional。执行变更相关序列压测：重复/交替 shape、槽位 wraparound、不同进程与缓存命中、metadata 更新/复用。新增失败先用可信原基线对照，再修复或淘汰候选。调度改变时按冻结支持范围补满/单 tile、短长 query 交替、空 query、尾块、sink/LSE、两个 AIV 不均衡和槽位回绕；不支持的路径须有真实接口依据，不能以未测代替不适用。
6. 调度报告分别记录 model/lowering/runtime 证据；源码、参数、SDK/编译配置或输入分支变化使相关证据失效，重新绑定 SHA。只有符合性、资源/编译/加载、精度与序列门禁通过才 eligible。正式采集按 shared protocol 排他运行，编译/调试 launch 不计入样本且不得未声明。本轮构建使用隔离目录，同设备验证串行。

生成代码核对还须区分地址、所有权和真实搬运：RingBuffer 捕获句柄不证明跨控制流区间持有 lease；逻辑等价 guard 也可能被 lowering 拆成多个事务，须核对实际同代 slot、guard 与发布/消费绑定。whole-view 模型的保守包络不证明 DMA 布局正确；分片或 reinterpret 后核对源/目标 stride、偏移、搬运长度及写集合，精度结果由原 checker/golden 独立验收。取证方法见 `ascendc-performance-review` 的后端层模板 `references/async-schedule-templates.md`（后端层当前 DSL 的真实表达与核对）。

## 选择与最终验收

保留 `selection-and-final.md` 中 baseline 参与唯一终选、effect 摘要和全集交付规则。DSL 的功能验证、序列压测、编译和实际加载检查按本文件及共享验证契约执行；原测试使用 TTK 或原工程包含 C++ 扩展时，仍检查对应入口。generalization 仅在明确选用时加载其规则。近噪声边界结果依同身份复测确认，不临时改抖动阈值。无有效改善保留 baseline。

在既有候选/每轮报告中逐 case 对照 analysis 中的预期机制、候选耗时/收益区间与实测 effect，记录偏差原因；按假设需要检查生成指令或改后流水，不为对照重复已有有效采集。区分机制未发生、新增成本低估、正确性缺陷与采集无效。预估只用于假设复盘，不参与正式终选，不以预测命中代替精度/性能门禁或以一次预测偏差否定整类方向。

组合代码是新候选，重过全部门禁。每轮交付同名 conformance/safety/function/performance/selection 产物与编译身份；最终对 functional_full、performance_full 验收，输出 final-functional-regression.md、final-performance-comparison.md、final_optimized/、stage=implementation/collection=performance_full 的 dsl-compile-evidence.json。最终证据对应保留实现，不能指向某个曾成功的其他候选。

数值诊断首先查 DSL 参数/布局/tail/Channel/VF/FTZ 与编译结果；仅已确认后端问题时使用 AscendC 排障技能。沿工作流原精度持续诊断政策保存真实进展，不对已淘汰候选伪造 eligible。

# HCCL CCU 通信算法开发 Skill 设计

## 目标与交付范围

新增 `cannbot-skills/communication/hccl-ccu-best-practice/`，支持 HCCL 标准算子的 CCU 算法设计、实现、局部修改与只读检视。参考 AICPU 技能的渐进式知识结构，技术契约以用户提供的 HCCL/HCOMM 当前源码为准。

交付一个可独立调用的能力 Skill、按需参考资料、设计文档模板、源码定位脚本、启动参数契约检查器及回归用例。该 Skill 不拥有多 Agent 状态机；`hccl-op-generator` 通过独立 CCU 工作流绑定本 Skill，并复用已有角色、产物身份和修复机制。

## 关键链路

脚本要求显式传入仓根，输出完整提交、分支、关注文件的 SHA-256 和工作区状态；知识索引记录相对源码路径与关键符号。提交相同也不能代替实际文件核对。

```text
HCCL selector → REGISTER_EXEC_V2 / 属性约束 → executor / TopoMatch
  → CcuAlgTemplateBase 派生 template
    ├─ CalcRes → CcuKernelInfo / channel / die / resGroup
    │             → HCOMM 资源查询与 kernel 注册
    └─ KernelRun / FastLaunch → taskArgs → HcommCcuKernelLaunch
                                 ↓
                CCU kernel 的 LoadArg / ccu 原语 / CCU 控制流
```

首个贯通样本采用 AllGather Mesh1D Mem2Mem：其 template、kernel、executor 注册、selector、两级 CMake 均可在当前源码定位。另按需参考 AllReduce 的归约原语和多 kernel/die 场景。样本不规定新算法必须是 Mesh、固定 rank 或固定线程数。

## 与 AICPU 的关键差异

| 关注点 | CCU 设计要求 |
|---|---|
| 执行模型 | 区分 host 构造 CCU 指令图与 CCU 运行期，动态条件使用当前 CCU DSL |
| 两种参数 | 区分注册期 `CcuKernelArg` 与启动期 `uint64_t taskArgs`；不能混用两处 `argNum` |
| 参数 ABI | host 顺序、kernel `LoadArg` 索引、FastLaunch 缓存和地址更新必须对应 |
| 通信资源 | 核对 kernel 数、channel→peer 顺序、die、resGroup、资源申请与消费 |
| 同步 | 区分本地 Event 和远端 channel Notify；16 位 mask 按协议分配，逐轮处理复用 |
| 地址 | 输入/输出基址、executor 偏移、切片、repeat、尾块和 token 的所有权明确 |
| 构建 | 标准 CCU template 与 kernel 加入各自 CMake 的 `hccl` target；不得照搬 AICPU device 库登记 |
| 跨仓边界 | HCCL 经自身 dlsym 适配层调用 HCOMM，禁止算法直接依赖 HCOMM 私有实现或新写 legacy |
| 验证 | 静态契约检查、编译、功能/选路回归、真机性能分别给出证据；不把 VM 功能通过当性能通过 |

## 技能结构

```text
hccl-ccu-best-practice/
├── SKILL.md
├── references/
│   ├── architecture.md          # 分层、资源与调用生命周期
│   ├── algorithm-design.md      # 数据流、地址、同步与支持矩阵
│   ├── implementation.md        # template/kernel/接线的实施方法
│   ├── api-and-synchronization.md
│   ├── validation.md            # 构建、回归、性能及证据边界
│   └── source-map.json          # 相对路径、关键符号、校验基线
├── assets/
│   ├── design-template.md
│   └── launch-contract.example.json
├── scripts/
│   ├── inspect_sources.py       # 显式仓根，定位源码与版本漂移
│   └── check_launch_contract.py # 检查声明的 host/kernel/cache 参数映射
├── tests/
│   └── test_tools.py
└── evals/
    └── evals.json               # 实际任务与行为验收标准
```

## 使用路径

1. 根据请求选择只读分析、局部修改或新算法/数据流变更；只读和纯日志/CMake 修改不强制完整算法设计。
2. 运行源码定位脚本，确认当前版本及目标算子的可用接口，按来源索引读取必要文件。
3. 新算法先形成数据流、资源、参数 ABI、支持范围及测试设计；局部变更只补受影响契约。
4. 实现 template、kernel 及必要的 executor/selector/CMake 改动。Skill 提供方法和已核验样本入口，不生成可误用为成功算法的空实现。
5. 检查启动参数契约；结合源码逐项检视数据流、同步及资源。脚本只校验声明内部一致性，不声称解析任意 C++ 或证明通信正确。
6. 根据实际环境执行编译与功能验证，记录执行命令、退出码、实际选中算法、源码/构建身份和证据。性能需求另行测量。

可直接向 Agent 提供本 Skill 的 `SKILL.md` 路径和两个源码仓路径。无需为使用单个 Skill 启动 AICPU 插件工作流。

## 验收

- Skill frontmatter、命名、相对资源链接完整，没有未完成脚手架。
- 来源脚本在本次 HCCL/HCOMM 上运行，报告所有关键来源及完整版本；缺文件和漂移有明确结果。
- 参数检查器覆盖正常映射、参数数目/次序错误、重复/越界索引、缓存前缀不一致及 FastLaunch 漏更新等真实错误。
- 输入校验拒绝非法结构，脚本只读取源码，诊断不触发 Git LFS 写入、构建、安装或设备操作。
- 行为评测覆盖新算法、现有算法修改、只读评审、旧接口迁移和环境不足。
- 本次验收针对 Skill 和配套工具；实际生成的通信算法仍须在目标环境单独编译与验证。

## 实施结果

初版交付 [hccl-ccu-best-practice](../vendor/cannbot-skills/communication/hccl-ccu-best-practice/SKILL.md)，共 13 个文件。保留标准 `name`/`description` frontmatter，主入口 64 行，技术细节按需读取；两个 Python 工具仅依赖标准库。

本次验证结果：

- 工具回归：29 项测试通过，覆盖 launch/cache 参数错误、未提交源码漂移、缺失来源、路径越界、输出保护及只读 Git 行为。
- `skill-creator` 快速检查及技能仓 `skill_validator.py` 结构/内容检查通过；17 个技能内相对链接有效。
- 在用户提供的 HCCL/HCOMM 仓执行来源基线检查，25 份关键文件与记录一致；AllGather 索引包含 56 份目标文件。
- AllGather Mesh1D Mem2Mem 的真实参数布局样本通过契约检查：15 个启动槽、17 个缓存槽，FastLaunch 更新地址和 alias 派生字段。
- 8 个行为评测场景通过仓库评测解析器校验；本次未执行模型行为评测。
- 本次没有生成具体通信算法，也未运行 HCCL 构建、VM 或 NPU 功能/性能测试；这些不属于工具回归的通过范围。

调用示例：让 Agent 读取上述 `SKILL.md`，提供 HCCL/HCOMM 仓路径和算子、算法、rank/拓扑、dtype/reduce、数据范围、模式与验收要求。技能文件已在技能仓落盘；插件的安装清单、路由和四个角色已接入 CCU。临时项目用于安装回归，尚未安装进用户级客户端目录。


## hccl-op-generator 接入设计与实现

插件负责流程，技能仓负责 CCU 技术规则与脚本，不把 CCU API 手册复制进角色提示词。

| 层次 | 实现 |
|---|---|
| 安装 | plugin-sources、Claude/Codex manifest、marketplace 加入新 Skill，插件版本 1.3.0；源码安装显式选择本地技能 Git 工作树 |
| 路由 | 明确 CCU 标记进入 ccu-multi-agent-workflow；保留 AICPU 默认路由、引擎冲突检查与 AIV/HostDPU 阻塞 |
| 角色 | 四个已有角色增加 CCU Skill 与职责，分别持有设计、生产实现、独立审查、基线/构建/验证 |
| 状态 | 两引擎统一 ENV_READY → DESIGN_READY → BASELINE_READY → IMPLEMENTED → REVIEW_PASS → TEST_PASS → COMPLETE，替换旧 CCU VERIFIED 顺序 |
| 产物 | CCU 模板保留共享证据协议；增加 Architect 独占的 source-report.json、launch-contract.json，哈希绑定 DESIGN；冻结 CCU 模式及 HCOMM 依赖身份 |
| 门禁 | 复用现有身份/owner/调用/哈希检查，CCU 适配器实际执行 Skill launch 检查器；声明与代码对应关系仍由 Reviewer 核对 |
| 失败 | 评审失败回 Developer→Reviewer；源码测试失败回 Developer→Reviewer→Verifier；环境失败阻塞，最多三轮修复 |
| 验证 | 合成流程/负例、AICPU 回归、临时项目安装验证；不将流程测试表述为实际 CCU 算法通过 |

可执行入口、安装方式与远程发布前的技能版本更新要求见 [quickstart](../plugins-official/hccl-op-generator/quickstart.md)。远程 marketplace 的技能 SHA 仍是原发布版本，需在技能仓正式提交后更新为真实提交；当前完整安装通过本地 `--skills` 实现。

接入验证：81 项插件回归、29 项 CCU 工具测试及 2 项共享安装器定向回归通过；OpenCode/Claude 临时项目安装与独立打包检查通过，9 个 Skill 和 4 个角色完整，61 个本地文档链接校验通过。测试不代表实际 HCCL 构建或硬件运行。


## 2026-10-20 耗时复盘与知识前置

依据用户提供的 CCU `tasks/allgather-ring-ccu-20261019/hcclbot/TIMING-REPORT.md` 与确认的 AICPU `tasks/TASK_TIMELINE_REPORT.md`，原始报告和任务源码只读。CCU 为首次实现/四角色多轮工作流，AICPU 复用了历史 Spec/实现且没有单列独立 Reviewer，两者不能作为控制变量相同的性能比较。

| 同口径项 | CCU | AICPU | 解释 |
|---|---:|---:|---|
| 任务墙钟 | 约16h50m | 1h42m38s | 约9.8倍，但流程/复用/故障条件不同 |
| VM 用例执行 | 约9.5m | 约9m11s | 测试实际执行量不是主要差距 |
| 构建累计 | 约62m | 8m | CCU含运行库重建与失败候选；不能归因于某个编译选项 |
| 首轮接口调研/设计 | 108m（含约85m源码调研） | API核对13m43s+设计7m23s | 知识卡与变化定向核对优先 |
| 首轮实现 | 约106m | 12m07s | 两端都含编码/静态检查，AICPU还复用了历史实现 |
| 首轮独立评审 | 75m | 未单列 | 不可据此声称同等级评审可缩到0 |

CCU另有库代际不匹配、GiB级矩阵导致宿主宕机、零数据工具/入口不可达，以及 Notify 配额错误四类事件。报告中的活动分类、事件分类和理想路径存在交叉；尤其P0的“再省51m根因取证”已包含于其失败闭环，不能重复相加。4h16m闭环中的成功构建、正确设计证明和独立验证在一次通过路径中仍需发生；不将整个区段视为可消除耗时。总体“降至7小时/55%”是反事实估计，本次不当作已实现收益。

### 已实施的优化

1. **有来源边界的先验卡**：新增 development-entry、operator-contracts 和 knowledge-baseline；当前4张卡覆盖公共同步、AllGather Sole、选路和已修复 Ring 样本。对工作区实际字节计算哈希；MATCH且适用直接复用，CHANGED只补查变化方法/依赖，缺来源标UNVERIFIED。不因HEAD变动全量重研，也不把AllGather结论外推所有算子。
2. **减少角色重复认知**：Architect在既有DESIGN保留一份接入记录；Developer消费结论、补查增量，Reviewer独立检查算法关键点并按delta复审，Verifier复用冻结矩阵/命令与仍有效的原始证据。保持角色和证据门禁。
3. **同步资源预检**：新增check_sync_contract与示例，核对HCOMM实际分配4个Notify/4个XN、uint16_t mask、按接收表区分并检查去重/上界。可确定拦住POST=5、同表信号位冲突、XN越界；跨epoch重用要求显式证明，检查器不证明C++对应关系、活性或证明内容正确。
4. **接入插件设计门禁**：新任务ccu_contract_version=2，Architect拥有sync-contract.json并将哈希绑定DESIGN，门禁实际调用Skill脚本。未声明版本的历史任务保留版本1原有门禁，不改写已完成任务。新任务不允许降级绕过检查。
5. **矩阵和环境知识前置**：TEST_PLAN首版记录工具可表达/实际对齐、count=0入口和loop可达性、每rank/全局字节、VM/Checker内存模型与余量、实际库身份及最小模式冒烟计划。64MiB仅是旧任务现场上限，不成为所有机器默认值。冒烟继续由Verifier在已有授权和可信旧包条件下执行。
6. **控制工具输出体积**：inspect_sources新增summary及知识卡结果，后续check_knowledge只输出卡状态与变化项。完整来源报告落文件保留证据，避免每角色把完整inventory重新读入上下文。

一次本机测量（同一HCCL/HCOMM，非端到端/统计性能结论）：完整inspect输出40,653 bytes/0.0906s，summary为3,472 bytes/0.0880s，后续knowledge-summary为1,278 bytes/0.0515s。摘要减少约91.5%/96.9%的输出体积，**主要减少模型阅读/推理，不宣称磁盘查询本身节省数小时**。

### 保持与暂未采用项

保留可信基线、候选全量构建、独立Review和A/B真实Checker。没有新增并行共享构建/测试、自动重编HCOMM或改变安装权限；未因host-only改动或device哈希相同就删--full。构建裁剪、ccache收益、设计/构建重叠均需另有可复现验证和工作流授权，不能从本次两份报告直接推定。

下一轮效果按首次源码/契约核对时间、重复查询文件数量、设计退回次数、基线修订轮次、实际构建/用例时间和最终同身份验收记录度量；区分知识复用、环境已修复和流程差异，避免把一次环境改善全计为Skill收益。


本轮验证：Skill工具44项、插件回归89项通过；临时项目安装/独立打包包含新版模板和同步检查器，88个相对文档链接有效。按skill-creator做了一次独立只读试用：4张卡均MATCH，使用者未因旧来源索引的局部CHANGED转入全仓调研；同步/启动样本通过，slot=5、XN=4、DATA/POST位重叠均被拒绝。试用发现并已修正summary结构一致性、hccl_test来源身份说明和只读脚本缓存写入问题。未进行新算法端到端耗时或VM/NPU功能/性能复测，因而尚无缩短55%等实测结论。

## 2026-10-22 重跑反馈与第三版优化

依据 `tasks/allgather-ring-ccu-20261021/hcclbot/OPTIMIZATION-PROPOSALS.md`、`TIMING-COMPARISON.md` 及候选失败诊断，并回查 HCCL/HCOMM 实现。该任务已 COMPLETE，其代码、报告与哈希链保持只读；历史 DESIGN 的乘法假设在 Skill 中勘误。

### 耗时结论

重跑墙钟约8h45m，相比上轮16h50m减少约48%；设计108→80分钟，实现106→71分钟，首次独立评审75→67分钟。基线52分钟一次通过，环境阻塞、宿主宕机、Notify槽位失败未复发。两轮存在缓存构建、环境预修复和矩阵差异，不能将全部下降归因于知识卡。

剩余返工集中于以下事件：

| 事件 | 本轮记录的时间 | 可前移的判断 |
|---|---:|---|
| Variable乘法编译成功，但目标V1生成器无法翻译MUL | 候选r1约57分钟，后续修复/复审/复测闭环约2小时 | API存在与目标rep表支持分别核对 |
| N=1标准API在Selector前返回，统一expect-algo无法观测 | 设计勘误33分钟、重绑定26分钟 | 逐用例核对断言产物所在路径 |
| 二阶BASELINE哈希依赖遗漏 | 上述26分钟内含额外微调用/门禁回退 | 计算后代闭包，按拓扑序更新 |
| static_failure_count误记过程累计数 | 约9分钟 | 模板明确返回时未解决数 |

这些时间不能直接求和当作可全部消除的收益：候选成功构建、测试和独立验证仍需执行，哈希二阶遗漏已包含在26分钟内。提案的“再省3–4小时”仍是估计，第三版端到端收益待同口径重跑测量。

### 已实施

1. **生成器能力前置**：新增第五张 `generator-arith` 字节锚定卡，覆盖Variable API、C适配、kernel lowering、rep枚举、V1/V2表及运行期选择。新增 `check_arith_ops.py`，从已核对头文件提取实际能力表；未知代际采用交集，V2必须有匹配SHA-256且可辨识版本的初始化日志。新设计在现有 `sync-contract.json.compute_ops` 登记表达式→实际rep；两侧设计模板、Developer与Reviewer职责同步更新。当前V1算术仅ASSIGN/ADD，但支持JUMP_EQ/JUMP_NE，修正提案中“比较均仅V2”的过宽结论。检查器只检声明和证据内容，部署身份、C++对应关系与替代实现正确性仍需独立审查。
2. **断言可观测性预检**：验证参考、AllGather契约卡、测试计划矩阵、Architect和Reviewer要求逐行记录断言文本、真实产生位置和本用例可达性。N=1标准API的SingleRankProc早于Selector；替代API功能断言不能冒充目标kernel覆盖，不可验证项明确LT/UNVERIFIED。
3. **只读重绑定工作单**：两个validator共用 `--rebind-report TASK_SPEC TEST_PLAN --json`，输出后代闭包、owner、字段和拓扑层级，覆盖BASELINE→LOG/REVIEW→TEST_REPORT二阶依赖；`--verify-rebind`列出当前残留过期绑定。各owner核对原始证据后更新，后层读取前层更新后的实际哈希。工具不写报告、不自动恢复PASS；索引、失效记录和目标状态门禁照常执行。
4. **日志计数语义**：共享LOG模板正文说明static_failure_count是本次返回时未解决数，PASS须为0；已修复问题保留正文过程证据，不计入该字段。未添加自定义frontmatter解析器不支持的行内注释。

插件新任务模板采用 `ccu_contract_version=3`，设计门禁实跑launch、sync、arith三个检查器，仍只有原来的三个JSON附件。历史版本1/2维持原门禁，完成任务不自动迁移；升级需Architect重新冻结并处理下游失效。新增2项行为评测场景，覆盖V1乘法和N=1不可观测断言。

### 本轮验证

Skill工具55项、插件101项回归通过，包含历史契约兼容、算术门禁拒绝MUL、来源漂移、缺失工具，以及两引擎重绑定CLI逐字节只读检查。插件集成测试显式使用本地技能仓，OpenCode/Claude临时项目安装通过。独立分发包包含9个Skill、新算术检查器及版本3模板；从包内运行算术检查对照实际HCOMM通过。90个相对文档链接及锚点有效，quickstart继续使用占位路径。

独立只读试用实际拒绝UNKNOWN+MUL、V1+MUL、无初始化证据的V2+MUL，并从源码识别N=1断言不可达；ASSIGN/ADD替代声明通过仅表示rep支持，不表示算法已实现正确。试用发现乘法rep中间层与V2具体翻译实现未纳入新卡，随后定向核查并加入字节范围，算术工具和插件算术门禁定向回归再次通过。另两张AllGather旧卡在重跑源码上CHANGED，维持定向补查，不为通过校验盲目更新旧基线。本次未构建HCCL、启动VM/NPU或进行新的端到端计时。

## 第三轮实测后的 Skill 优化

用户提供 `tasks/allgather-ring-ccu-20261022/hcclbot/TIMING-V3-STAGE-ANALYSIS.md`：墙钟约7h10m，算法零修复轮；两次构建约9分钟，25次运行的results.jsonl累计337秒。此前前移算术/断言检查已避免同类失败，但设计、报告和认知仍有优化空间。报告横切分类相加约458分钟大于墙钟430分钟，设计阶段56/114应约49%而非30%；因此不将“6h50m”视为已证实下限，也不按交叉分类叠加预估收益。

本次按用户确认的六项建议实施：

| 优化 | 实现与边界 |
|---|---|
| 框架方法契约 | 新增all-gather-framework卡与framework-contracts.md，以当前核验源码字节记录带参/默认构造、成本空结果剔除、资源默认行为、建链clear等调用约束。其reviewed_heads单独记录，不刷新旧卡掩盖差异；其他executor不外推 |
| 专用数据流模板 | 新增assets/dataflow-spec-template.md，保留所有权/地址、资源同步、活性、边界与重放证明；规格/文件计划/矩阵及JSON完整映射引用既有产物。插件的dataflow索引、设计和调用模板同步采用；独立完整设计模板保留 |
| 可操作的漂移报告 | check_knowledge新增--cards、--explain、--diff-lines。基线提交blob哈希必须与已核验SHA一致才能给出有界diff/变更区段/符号位置；不可用时明确BASELINE_UNAVAILABLE。CHANGED/UNVERIFIED状态保持，不推定语义无关，不拉取源码或改基线 |
| 短代码范式 | 新增V1 ASSIGN/ADD stride乘host常量helper、多peer请求分别收集合并及launch前缀/cache示意。独立句柄、host立即数、溢出和实际channel映射需按算法证明，生产代码不依赖Skill安装路径 |
| 最短阅读路径 | SKILL入口按设计/实现/独立评审/验证提供必读与按需参考；可选历史样本仅在借鉴时展开。数据流与JSON集中维护，其他产物保留自身核验与引用，不复制完整原表，也不硬截断关键证明 |
| 统一检查入口 | check_contracts.py按原语义运行launch/sync/arith三检查器，汇总退出码、原始输出和契约哈希；一项失败不隐藏其他项，超时/缺工具/文件变化整体失败。原检查器及插件版本1/2/3门禁不变 |

同时修正第三轮暴露的身份约定冲突：CCU工作流、调用参数与角色/LOG/HANDOFF说明将HCCL source_identity与HCOMM hcomm_source_identity分别传递；门禁需要的HCCL头字段不再拼接两仓字符串。此为提示与模板修正，不改历史已完成任务或放宽门禁。

静态材料比较：入口从6234降至4986 bytes（约20%）；新Dataflow模板2040 bytes，相比旧完整设计模板3675 bytes减少约44.5%。这些是输入材料体积变化，不代表端到端时间按比例下降。新增3项行为场景（共16项），效率评测同时记录无关/重复阅读、重复正文、实际工具与读写量、分阶段耗时；正确性和必要独立核验仍需保留。

验证：Skill工具70项、插件101项通过；纯host Variable模型遍历所有uint16_t因子和代表性stride验证ADD链结果及输入句柄不变，并用真实HCOMM头完成helper语法实例化。实际源码的统一检查器三项通过，旧Sole/选路卡的差异可定位到注册/映射区段，新框架卡MATCH。OpenCode/Claude临时安装与独立分发包验证通过（9 Skill/4 Agent），新模板、代码范式和检查器完整；本地相对文档链接及锚点校验通过。未执行新的HCCL构建、VM/NPU运行或第四轮端到端计时。

独立只读试用确认默认构造、成本空结果和建链容器三项草案问题；同时发现需要区分消费者：当前Sole重放按templateAlgRes.threads.size()保存线程，不能只因继承GetThreadNum=0就判该路径必然失败。已收窄方法卡与行为验收条件，避免把通用基类默认值过度推广为当前executor缺陷。

试用手工查阅14个文件，技术交付2311字符、审计2450字符（含空白），并实测缺失基线时保持CHANGED且返回BASELINE_UNAVAILABLE，不编造差异。这不是与上一轮不同请求的计时对照。试用另发现整页接入卡带入未用Ring样本和工具/内存长段，随后将Ring资料独立为按需参考，工具与内存内容移入既有validation，常用接入页从6333降至3723 bytes，技术内容与来源边界保留。

## 第四轮实测后的输入预检与流程自动化

用户提供 `tasks/allgather-ring-ccu-20261023-time-breakdown.md`：请求到答复2h04m42s，较第三轮约7h10m下降约71%；本次直接复用两个历史实现提交，不能把全部降幅归因于Skill，也不代表全新算法固定耗时。设计29m28s、独立检视27m11s，合计56m39s（45.4%）；构建/测试区间与角色窗口重叠，机器/Agent比例为近似活动分类，不当作纯命令/纯推理占比。

报告中118/112/114是通信域编号，实际8/2/4rank。第四轮原始结果在前次分析时核对为基线16/16、定向17/17、回归16/16，通过且算法命中一致；本次实施期间这些原始任务目录已被外部移除，本次没有重建历史证据或重新声称完成49例实跑验证。

本轮实施三个入口，技术模型留Skill，流程工具留插件：

| 入口 | 行为与边界 |
|---|---|
| `preview_allgather_cases.py` | 逐字节核对安装工具的common cc/h、基类count计算和AllGather buffer计算四文件；计算实际rank/count/input/output/基本总I/O、等效输入及给定预算，来源变化不发出猜测预测。二进制哈希单列且源码对应关系仍需可信构建证据；不证明覆盖或功能 |
| `init_ccu_task.py` | 只读Git后创建全新任务/证据目录与索引、环境草稿；不覆盖已有目录、不建分支。环境草稿BLOCKED/valid=false，owner核对PASS后仅绑定实际报告哈希，再跑原门禁。脏仓使用已确认身份与另行可恢复快照，绑定时复核两仓内容指纹，不自动清洁源码 |
| `summarize_ccu_evidence.py` | 显式选取冻结计划的run，复用hvm validate/parse_log/compare，核对原日志/结果、源/包/库身份、角色、用例和目标算法，默认回归逐组配对。输出读取成功的run哈希、包含失败记录的recorded_totals与核对通过的totals，错误非零，不写证据或流程结论 |

可执行矩阵复用已有hvm `plan.py`，由其先建目录、记录批次命令/时间、串行执行及失败停止，不新增另一套runner。Architect可选写`checker-plan.json`，版本3以TEST_PLAN头`checker_plan_sha256`绑定，沿原TEST_PLAN哈希链传播；缺绑定、缺文件、文件变化和路径越界阻断，Verifier无权改计划。无此附件的版本1/2/3历史任务要求不变，三个必需技术JSON附件及原角色/完整构建/A-B验收继续保留。原始需求允许真实DSL花括号，模板元数据中的占位符仍拒绝。

源码复核修正了测试报告中的普遍整数除法假设：工具先按rank或rank×512规整字节，再ceil(A/dtype_bytes)，AllGather再ceil(E/N)。因此8rank/int32请求1048579规整后与1048576等效；请求1规整并两次取整后每rank count=1、输出32，不能代表零数据。阈值16MiB及512字节均来自当前核验源码，其他工具版本/算子不外推。未提供预算时within_budget明确null；多loop只在提供已核对maxCountPerLoop及源码依据时预测，仍需真实路径日志。

独立隔离试用发现两项并已修正：一是旧hvm解析器可能忽略成功汇总前夹带的明确ERROR；新汇总入口拒绝ERROR/FATAL级别（含ANSI/大小写），普通error_count=0不误报，没有修改共享工具的用户已有内容。二是失败run最初不带哈希、统计仅计核对通过记录；现在保留失败run的manifest/results哈希与recorded统计，并和验收统计明确区分。试用复查原始合成证据前后SHA相同，不将隔离日志视为真实Checker运行。

本轮验证：Skill工具78项、插件120项（共198项）通过，包含真实隔离Git初始化/环境绑定、来源漂移、双重取整/16MiB边界/预算、可选计划哈希与owner、原始FAIL伪装PASS、ERROR/FATAL及普通零错误计数、默认选路变化和逐字节只读性。18项行为场景为维护的评测输入，并非18项模型评测均已执行。一次独立现实试用实际使用输入预检、初始化、hvm plan格式检查与三轨合成证据，原始证据SHA保持一致。

111个本地Markdown链接/锚点有效，两仓diff检查和Skill结构检查通过；暂存与独立技能仓35文件逐字节一致。OpenCode/Claude临时安装包含于插件回归；独立分发包包含9Skill/4Agent、三个新入口和来源profile，包内真实源码launch/sync/arith检查及输入模型通过，包内证据汇总对合成成功、Checker失败和ERROR夹带样本分别正确返回0/1/1。未进行HCCL构建、设备测试或第五轮端到端计时；不以工具回归换算节省分钟数。

## 五算子接入卡与输入模型扩展（2026-10-23）

用户要求补充AllReduce、ReduceScatter、Broadcast、Reduce、Scatter。技术知识继续维护在独立技能仓`communication/hccl-ccu-best-practice`，插件只更新按算子加载、预检及证据使用规则。五张新卡各自固定本次核验HCCL HEAD `d749022326eb68a585851707bb0420f552ad12c3`和逐文件哈希；公共HCOMM卡在`d1c2b18c2a8bf97d6d7ffde5f1a44762cbcd2a25`核验MATCH。保留原六张卡全部字段，不刷新AllGather旧卡来掩盖CHANGED或历史Ring样本缺失。

- `references/operator-index.md`按目录名选择自己的卡，同时列DSL/HVM名称映射；默认来源检查只选择目标算子卡及公共sync/arith卡。
- `references/operators/{all_reduce,reduce_scatter,broadcast,reduce,scatter}.md`覆盖实际Sole调用者、构造、字节/元素单位、stride、loop/scratch、资源、launch/cache ABI、root映射、注册限制、API短路与测试边界。主要核对Sched Mesh路径，MS仅列已存在注册，其他模式/多阶段executor仍按实际差异补查。Reduce真实入口为`reduce_sole_executor.{h,cc}`的`ReduceSoleExecutor`，不能根据`ins_v2`文件名推断缺少Sole。Scatter缺少Sole MS Mesh注册，不能外推支持。
- Reduce动态launch为N+12槽，缓存有长度头；Scatter缓存0/1从相对偏移原地更新为绝对地址，连续重放存在需要专门验证的风险；均写入卡中，不以现有样本充当已证明正确的通用模板。Reduce当前单Event的rank mask也必须核对16位容量，注册上限不证明资源可用。
- `scripts/preview_cases.py --op ...`及`references/hccl-test-collectives-profile.json`复用一个实现，按公共三文件和本算子一文件校验CANN 9.2.0工具的输入模型；其他算子来源漂移不会阻止目标算子。原AllGather命令/来源配置兼容。新增基本跨rank I/O预算、root/reduce-op适用性校验和底层工具参数提示；二进制来源绑定仍明确UNVERIFIED，不把源码模型MATCH当成实际部署身份。

测试工具中只有AllGather/ReduceScatter/Scatter设置rank规整，并经ceil(A/w)、ceil(E/N)得到API count；AllReduce/Broadcast/Reduce只有ceil(S/w)。8rank/int32请求1048579：前三种得到count32768且与1048576等效；后三种count262145、有效span1048580。Broadcast只分配一个别名buf/rank，Reduce非root输出和Scatter非root输入虽无相应结果/源数据语义，工具仍实际分配，预算按分配计算。基本I/O总和不含host临时副本、Checker/VM放大、scratch及对齐开销，完整预算仍在TEST_PLAN核对。

当前共享HVM封装固定归约sum、未暴露root透传，原生case key/compare也不含root/reduceType维度。预检可以表达这些底层工具参数，但不把非零root/非sum自动写入原生checker-plan冒充支持。TEST_PLAN单独冻结经验证的定向runner或MPI方式，保存含这两个维度的case-id、命令、库身份与真实Checker/命中证据。插件更新了quickstart、Architect、CCU调用模板、工作流、自动化说明和测试计划模板；状态机及1/2/3版本门禁语义保持原状。

本轮验证：Skill工具93项、插件120项（合计213项）通过；新增15项回归覆盖算子间对齐/count差异、root与归约类型适用性、别名和语义/分配区别、独立预算、来源漂移隔离、零规整、动态loop依据、路径逃逸及只读行为。保留旧AllGather回归。Skill结构验证通过，44个正式技能文件与写回版本逐字节一致。真实`assemblePlugins`生成包保留9个Skill、4个Agent、契约版本3；新八个技术资源完整打入包，包内旧AllGather入口、新五算子模型及launch/sync/arith示例检查均通过。行为评测输入由18增至23条，不代表23条模型评测均执行。

独立现实试用的输入为五算子、8rank/int32、三种请求字节、root0/root7及sum/max组合：12组共36个输入预检通过；可由现有HVM表达的15例计划格式检查通过。非默认组合另存定向计划；未启动VM/NPU、未构建HCCL，也未进行新一轮耗时对照。这些检查不证明设备功能或实际耗时收益。

试用未发现可确证的接入卡/模型错误或必需资源缺失。36例中15例可用当前原生HVM表达，另21例涉及root7或max；默认VM安装目录缺失，未继续环境准备。根据再次核对的既有源码，将ReduceScatter的CCU loop先扣1MiB预留空间、scratch对齐上限及对称内存强制单loop写明，来源仍在原卡固定范围内。最终138个本地Markdown目标检查通过。

## 2026-10-26 三项审查缺陷修复

1. launch契约schema_version=1增加可选`fast_launch.cache_launch_offset`，单位为uint64槽，默认0兼容原AllGather契约。验证完整缓存中的`[offset, offset+launch_count)`与launch_args一致，并检查类型、上下界、容量、启动槽数以及物理缓存updates索引。metadata前后均不发送。新增Reduce 8rank布局样本（N+12=20槽，缓存头1槽），不把样本扩展为缓存失效或运行正确性证明；插件实际调用Skill检查器的门禁也回归该布局。
2. 知识检查先验证op是当前HCCL源码中存在的安全目录名，`allreduce`/拼错目录返回2，不再通过公共卡MATCH掩盖算子卡漏检。输出operator.status、available_cards、checked_cards与目录验证情况；默认无算子卡时返回1，显式`--cards`仍可只检查已知依赖，但清楚报告NO_CARD或NOT_SELECTED，不声称核验了算子接入。内部仅HCOMM的公共卡检查保留op=None行为；inspect_sources摘要一并携带覆盖信息。
3. inspect_sources的`--output`保留仓外输出，仓内仅放行当前算子的`src/ops/<op>/docs/<安全task-id>/source-report.json`，与插件目录规范对齐。父目录由任务初始化创建，文件以排他方式创建；其他算子目录、其他文件名、HCOMM路径或符号链接实际落入生产源码均拒绝。插件调用模板与自动化文档给出直接保存完整报告并打印summary的命令，不覆盖已有证据。

验证：Skill 108项、插件121项，共229项回归通过；其中新增15项Skill回归和1项实际门禁回归，覆盖长度头/偏移范围/物理索引、旧契约、错误目录名/已有未覆盖算子/显式公共卡、报告只创建一次、Git index与生产文件不变及符号链接落点。Skill结构验证和141个本地Markdown链接通过；46个Skill正式文件与写回版本逐字节一致。assemblePlugins安装包保留9个Skill、4个Agent和契约版本3，并验证新Reduce样本与三个修复脚本完整入包、包内Reduce契约通过及错误算子名返回2。源码知识卡/工具模型基线未刷新，真实CHANGED继续要求定向核对；未修改HCCL/HCOMM或共享HVM工具，未运行设备/VM。

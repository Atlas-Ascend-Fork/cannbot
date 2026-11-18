---
schema_version: 1
artifact: TEST_PLAN
engine: CCU
ccu_mode: "{CCU_SCHED|CCU_MS}"
owner: hccl-architect
task_id: "{task_id}"
status: "{FROZEN|DESIGN_ISSUE|BLOCKED}"
source_identity: "{设计输入源码身份}"
artifact_revision: "{修订号}"
semantic_tbd_count: "{非负整数}"
created_at: "{ISO-8601 时间}"
---

# CCU 测试计划

> 本计划必须在观察候选结果前冻结。基线与轨道 B 使用同一矩阵；轨道 A 在对应用例上增加强制算法与命中断言。

六算子先按CCU Skill的`references/test-input-preflight.md`用`preview_cases.py --op <算子目录名>`运行实际输入预检；通信域编号与rank数分列，实际count/bytes及工具分配按本算子模型填写。root/reduceType列明适用性；非零root/非sum须列出经核对的定向runner或直接MPI命令与证据要求，不声称当前HVM计划已支持。采用可选`checker-plan.json`时在本文件frontmatter增加`checker_plan_sha256`真实哈希；参数以JSON批次为准，本文件按case-id引用并记录覆盖/可达性，不复制完整参数矩阵。格式及执行见 [CCU 自动化](../ccu-automation.md)。

## 1. 验收输入

| 字段 | 值 | 依据 |
|---|---|---|
| 算子/算法 | {op_type}/{algo_name} | |
| 改动层级 | | |
| 默认选路模式 | {不变/按批准范围改变} | |
| 批准来源 | {不变时写“不适用”} | |
| 允许变化范围 | | |
| 期望注册全名 | | |
| `HCCL_ALGO` 配置 | {经目标源码核验的值} | |

## 2. 身份与环境要求

| 项 | 必须一致/记录的字段 |
|---|---|
| 源码 | 仓、分支、HEAD、未提交差异或可恢复快照 |
| 构建 | CANN 来源、工具链、命令、日志、退出码、包哈希 |
| Checker | 版本、测试二进制、集群配置、rootinfo、iterations、warmup、runner |
| 用例 | dtype、size、通信域、环境覆盖、期望算法及调用次数 |

## 3. 冻结矩阵

| case-id | 目的 | topology/rank | comm-domain | dtype | size/边界 | 基线期望算法/次数 | 轨道 A 期望算法/次数 | 轨道 B 期望算法/次数 | 特殊覆盖 | 断言产物与可达性依据 |
|---|---|---:|---:|---|---|---|---|---|---|---|
| | | | | | | | | | {零数据/尾块/repeat/地址变化/FastLaunch/多 kernel 或 die 等} | {断言文本、产生位置与该用例路径；不可达时的替代/LT处置} |

### 3.1 白盒路径映射（适用时）

按 `hccl-ccu-best-practice/references/validation.md` 从本次改动的可达源码分支推导；无适用分支时填写 `NOT_REQUIRED` 和源码依据。此表复用上面的 case-id，不增加未经批准的测试目标。

| case-id | 源码位置/分支条件 | 独立预期/反例 | 工具与原始证据 | 未覆盖原因 |
|---|---|---|---|---|
| | | | | |

## 4. 回归范围

| 受影响对象 | 最低回归范围 | 相邻/公共影响 | 依据 |
|---|---|---|---|
| | | | |

## 5. 轨道判据

- 基线：可信旧包、默认路径、不设置 `HCCL_ALGO`，逐用例保存算法名、调用次数、Checker 和原始日志。
- 轨道 A：对真实经过算法选择/执行的用例，用已核验配置与可观测的 `--expect-algo` 证明目标命中；Checker PASS 且失败数为0。API短路等不可观测行单列首版处置，不能统一套批次断言，也不能用替代API功能断言冒充目标kernel覆盖。
- 轨道 B：不设置 `HCCL_ALGO`，与基线同矩阵；默认不变时按已安装测试工具的证据规则比较，批准改变时按冻结矩阵人工核对。
- 按目标实现覆盖切片、repeat、尾块和 FastLaunch 地址变化，用源码与日志证明实际触发；不可达分支写明依据。

### 5.1 功能验证后的性能估算

A/B 全部通过后由 Verifier 按 `hccl-test-tool-hvm/references/estimate.md` 对同一候选包执行独立 estimate，基线阶段不执行。记录冻结 CCU 模式、目标算法/选路配置、HCCL/HCOMM 身份，以及估算通信域（默认112，用户指定时继承需求）、拓扑、dtype 和适用的 root/归约参数；在本次估算日志重新核对命中。目标不支持该组网或环境能力不足时保留具体阻塞原因，不改用其他算法充数。

固定 `-np 1`、`-b 1G -e 1G -w 0 -n 1 -c 0`，不改变上述功能矩阵，不加入 checker-plan.json。真实执行后归档独立 estimate.json 和日志/profiling/trace，写入 TEST_REPORT；估算失败或缺证据阻塞完成，不据耗时阈值判性能收益或触发源码修复。

## 6. 额外测试授权

| 测试 | 授权状态 | 范围 | 结果在何处单列 |
|---|---|---|---|
| HCCL ST/UT | {未授权/已授权} | | `TEST_REPORT.md` |

ST/UT 不替代 A/B 双轨 Checker。

## 7. 原始证据要求

| 证据类型 | 持久路径规则 | 必填身份/哈希 |
|---|---|---|
| 旧包与基线 | 源码仓和构建清理目录之外 | |
| 候选包/源码快照 | 源码仓和构建清理目录之外 | |
| Checker 批次日志 | baseline/regression 独立目录 | |
| estimate.json、估算日志/profiling/trace | 本轮登记外部证据目录，独立于 Checker 结果 | HCCL/HCOMM 身份、CCU 模式、候选包/集群及原始文件哈希 |

## 8. 冻结记录

| 字段 | 值 |
|---|---|
| 冻结时间 | |
| 内容 SHA-256 | |
| Architect 结论 | {PASS/DESIGN_ISSUE/BLOCKED} |

## CCU 执行证据

记录 HCOMM 与 HCCL 联合身份、实际 CCU 模式、template/kernel 和算法命中证据。VM 支持目标模式且能运行 Checker 才可计为功能验证；静态检查不计 PASS，VM 功能不证明真机性能。

## 冻结前可执行性检查

| 检查项 | 本任务取值/结论 | 源码或工具/二进制身份与证据 |
|---|---|---|
| size/count 单位与实际对齐 | | |
| 零数据/非对齐/重放可表达性及算法入口可达性 | | |
| 每个定向断言的产物、产生位置与本用例路径可达性 | | |
| 最大用例 rank、每 rank 输入/输出及全局字节 | | |
| VM/Checker 放大系数、常驻/并发开销、估计峰值 | | |
| 现场可用内存、保留余量与本任务上限 | | |
| 多 loop/FastLaunch 等目标分支是否确实触发 | | |
| 实际加载库/可信构建身份及目标 CCU 模式冒烟计划 | | |

上限按现场模型确定，不能把历史任务的 64MiB 固定移植。工具不可表达、算法不可达、环境受限分别标明依据与未验证范围；不能以静态分析代替运行 PASS。

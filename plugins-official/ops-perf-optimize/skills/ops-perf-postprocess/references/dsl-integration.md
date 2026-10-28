# DSL 后处理

按 [DSL 共享验证与领域边界](../../ops-perf-acceptance-criteria/references/cannbot-dsl.md) 执行本阶段。消费最终 demo、映射、原源码快照、契约/scope、终选与全集证据；使用独立后处理实例，只在主 Agent 冻结的原工程范围回写。

按逐文件映射集成已验收的 Python/tiling/流水实现。保持原函数签名、输出、参数检查、shape/dtype/布局支持、stream、metadata ABI 和 JIT/AOT 部署模式。纯 Python/JIT 不新增 OPP/ACLNN 包装；原 AOT/注册输入保留既有发布与加载方式。检查并发用户改动，不覆盖未知变更。

回到原 Python 调用链执行 functional_full 与 performance_full（功能用例就是性能用例：同一冻结集合服务精度判定与性能对比，不另造额外验证集），逐 case 检查原 PASS/已知失败与有效性能退化。必要路由只依赖真实输入元信息；共享依赖和未涉及路径按影响范围验证，不因没有广泛泛化而忽略已支持接口。新的回路由是新身份并完整复验。

启用 schedule_policy 时按 [回集成调度验收](../../ops-perf-acceptance-criteria/references/async-schedule-contract.md#回集成身份与全集门禁) 绑定当前原工程 root、全部目标 SoC 与冻结全集；逐 case/SoC/branch 保留运行证据。换 root 或回路由后建立新 model/runtime/conformance 身份；实施目录的旧 gate 不能代替实际集成链。

正式运行核验 import 来源、实际编译配置、包/工具链、缓存与加载 `.so`，metadata 生成/复用条件及全部相关 launch。输出 stage=integration、collection=performance_full 的 dsl-compile-evidence.json；无源码变化也需有身份匹配的证据，可复用有效原材料，不为 no-op 重测。

功能库存的 expected_error 沿已有 before/after error 门禁；host_only 行用 `validate_postprocess_performance.py --baseline-functional-host-checks <json> --candidate-functional-host-checks <json>`，results 每行含 case_id、status=PASS、冻结的 assertion 和 raw_evidence 文件身份。设备行仍有原性能检查，host_only 不伪造 NPU 耗时；功能库存全为非设备行时，两侧计时 CSV 只保留 case_id,total_us 表头，逐例语义证据仍必须完整。

保留共享源码隔离/集成安全门禁和每 SoC postprocess-performance-<soc>.json；DSL 没有 C++ AddConfig/TilingKey 时以真实 Python 路由、元信息和编译变体取证，不能伪造 C++ 宏。最终 VERIFY_REPORT.md 写回文件/接口审阅、受影响路径、functional/performance 全集结果、最终加载身份、原目标达成状态与未覆盖项；未测路径不标 PASS。

## 效果确认与耗时控制（DSL）

回集成阶段最容易超时的是证据组装与重复统计确认；按以下口径执行（来自实板 run 复盘）。本节只规定集成层的复用与执行方式，不放宽 `performance-jitter-policy`、`msprof-op-effect-evidence` 与调度契约的任何 proof 门槛：

1. **两全集 before/after 用 canonical10_independent proof，集成层禁止默认重跑 20-slot 全量确认**：baseline 侧绑定既有冻结收据（plan 显式声明其 manifest 路径与 SHA，不重采），candidate 侧只做一次集成后采集。demo 侧已完成的最终 20-slot 确认（`msprof_op10_independent_v1`）不重做、不改名降级为集成层证据。逐 case 分类仍按冻结 `performance_effect_policy` 执行，小变化不因集成层复用而豁免配对确认。
2. **字节等价回写绑定 demo 确认结论**：回写字节一致性证明（writeback byte-equality）成立且源/编译/加载身份链闭合时，集成层效果结论 = demo 侧正式确认结论 + 集成层 canonical10 proof，不重复采样；绑定关系（两侧 proof 的路径/SHA）写入 effect summary 的 evidence_paths。
3. **先登记后采集**：`performance_effect_evidence.py --register` 必须早于全部 candidate 采集（registration 时间由 proof builder 机械核验，事后登记不可证明）。
4. **字节等价的边界**：仅当集成后源码与 demo 验收实现逐字节一致（writeback byte-equality + built 与 loaded 同 SHA）时适用第 2 条复用规则；回路由、编译分支或输入分布变化即新身份，必须重新确认。
5. **长采集脱离会话执行**：多 case 全集 before/after 由驱动脚本 `setsid`/`nohup` 后台执行，逐 case/slot 进度日志、独立证据目录、跳过已完成部分断点续跑；禁止放在代理前台单命令内（纪律详见 `ops-perf-acceptance-criteria` 的长采集执行纪律与 msprof op 确认适配器文档）。
6. **调度集成链换 root 只做重绑**：集成执行镜像与冻结契约模型内容逐字节不变时，仅重绑 candidate_root 生成契约副本并重建 model/runtime/conformance；不重新推导模型。集成阶段 `dsl-compile-evidence.json` 与早期轮同名，以操作者显式登记的产物为准（workflow_state 阶段证据索引已按登记优先解析）。

### 证据卫生（实板踩坑）

1. **同名文件不入 diff**：集成执行镜像中与本次优化无关的同名文件（如原工程的其他变体）不得进入候选 diff；回写映射按文件名逐字节核对，不按目录批量比对。
2. **日志刷盘时序**：采集脚本的证据快照（runtime source_artifacts、SHA receipt）必须在被测进程与 msprof 完全退出、输出落定后再哈希；否则 trace 日志异步刷盘会使 receipt SHA 陈旧（实板 40+ 处返工根源）。发现漂移按 amendment 记录并重绑到最终落盘字节，不删除原始数据。
3. **孤儿产物处理**：外部终止后 msprof 孤儿进程可能继续写入 attempt 目录；该 attempt 按"recorded failed + 目录原样保留"处理，重采使用新 attempt 编号，不得删除或改写既有 attempt 记录。

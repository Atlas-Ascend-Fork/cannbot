# DSL 后处理

按 [DSL 共享验证与领域边界](../../ops-perf-acceptance-criteria/references/cannbot-dsl.md) 执行本阶段，交付与 AscendC 同构：按 [merge-protocol.md](merge-protocol.md) 把工作分支（final 标签）合并回原工程目标分支，fast-forward 等价/并发变更条件分路，不再逐文件移植。消费终选与全集证据、契约/scope、workspace-manifest；使用独立后处理实例。

保持原函数签名、输出、参数检查、shape/dtype/布局支持、stream、metadata ABI 和 JIT/AOT 部署模式。纯 Python/JIT 不新增 OPP/ACLNN 包装；原 AOT/注册输入保留既有发布与加载方式。检查并发用户改动，不覆盖未知变更（用户工作树上的脏改动归用户，git 拒绝合并时提示用户处理，不代为处置）。

回到原 Python 调用链执行 functional_full 与 performance_full（功能用例就是性能用例：同一冻结集合服务精度判定与性能对比，不另造额外验证集），逐 case 检查原 PASS/已知失败与有效性能退化。必要路由只依赖真实输入元信息；共享依赖和未涉及路径按影响范围验证，不因没有广泛泛化而忽略已支持接口。新的回路由是新身份并完整复验。

启用 schedule_policy 时按 [回集成调度验收](../../ops-perf-acceptance-criteria/references/async-schedule-contract.md#回集成身份与全集门禁) 绑定当前原工程 root、全部目标 SoC 与冻结全集；逐 case/SoC/branch 保留运行证据。换 root 或回路由后建立新 model/runtime/conformance 身份；实施目录的旧 gate 不能代替实际集成链。

正式运行核验 import 来源、实际编译配置、包/工具链、缓存与加载 `.so`，metadata 生成/复用条件及全部相关 launch。输出 stage=integration、collection=performance_full 的 dsl-compile-evidence.json；无源码变化也需有身份匹配的证据，可复用有效原材料，不为 no-op 重测。

功能库存的 expected_error 沿已有 before/after error 门禁；host_only 行用 `validate_postprocess_performance.py --baseline-functional-host-checks <json> --candidate-functional-host-checks <json>`，results 每行含 case_id、status=PASS、冻结的 assertion 和 raw_evidence 文件身份。设备行仍有原性能检查，host_only 不伪造 NPU 耗时；功能库存全为非设备行时，两侧计时 CSV 只保留 case_id,total_us 表头，逐例语义证据仍必须完整。

保留共享源码隔离/集成安全门禁和每 SoC postprocess-performance-<soc>.json；DSL 没有 C++ AddConfig/TilingKey 时以真实 Python 路由、元信息和编译变体取证，不能伪造 C++ 宏。最终 VERIFY_REPORT.md 写回文件/接口审阅、受影响路径、functional/performance 全集结果、最终加载身份、原目标达成状态与未覆盖项；未测路径不标 PASS。

性能采集统一使用 `ops-profiling-report`，按冻结策略消费 median 样本或 confidence proof。同身份与同协议的证据按 merge-protocol 复用，实际身份改变则重新采集；多目标边界不能完整覆盖时保持 pending。

### 证据卫生（实板踩坑）

1. **同名文件不入 diff**：集成执行镜像中与本次优化无关的同名文件（如原工程的其他变体）不得进入候选 diff；回写映射按文件名逐字节核对，不按目录批量比对。
2. **日志刷盘时序**：采集脚本的证据快照（runtime source_artifacts、SHA receipt）必须在被测进程与采集工具 完全退出、输出落定后再哈希；否则 trace 日志异步刷盘会使 receipt SHA 陈旧（实板 40+ 处返工根源）。发现漂移按 amendment 记录并重绑到最终落盘字节，不删除原始数据。
3. **孤儿产物处理**：外部终止后 采集工具的孤儿进程可能继续写入 attempt 目录；保留该 attempt 目录并等待原件落定审计；已有 archive 先重解析，仅无已发布报告且无 archive 的失败才允许新 attempt，不删除或替换成功样本。

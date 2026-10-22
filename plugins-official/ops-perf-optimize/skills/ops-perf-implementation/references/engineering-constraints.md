# 实施知识与工程约束

- 先识别真实构建链、单算子 target 和依赖闭包；同一代码 SHA 只编译一次，不猜参数、不静默全仓编译、不修改共享 CANN SDK。
- 性能优化的公开契约是不可变输入：禁止修改 API 签名、输入输出/属性约束、支持 dtype/format、infer shape 和原有错误检查。即使新 kernel 能处理更多 dtype，也不能在性能任务中扩大声明范围；另行功能需求必须退出本工作流处理。
- `TARGET_SOCS` 是已验证范围，不是工程支持范围。从候选实施开始执行 `$PLUGIN_ROOT/workflows/references/source-isolation.md`：共享代码先复制再优化，公共文件仅增加最小接线；非目标 SoC 和同代未涉及模板保持原实现及可达 fallback。已复制工程目录、已有架构宏或其他用例通过，都不能豁免共享函数/依赖保护。
- 算子族、SIMT、Gather/Scatter、Reg/VF 路由按 `ascendc-performance-best-practices`；具体 API 以本机 SDK 和 `ascendc-docs-search` 为准。
- DAV_3510 向量/归约/寄存器重排/Cast/Pack 热点查询 VF catalog 并执行 `vf_preflight.py --strict`。保留 `example_build_contract` 和 readiness；辅助 probe 只作诊断，真实候选构建才是门禁。
- 内嵌 MM 方案必须保留 `mm_route` 和路线证据。DAV_3510 低阶 Cube 路线至少核验 `A2/B2/CO1`、`LoadData2DParamsV2`、`MmadParams`/`Mmad`、`Fixpipe`、`DataCopyCO12DstParams` 及 MTE 事件配对；低阶 Cube 流水重建与 AIV 替换 MM 是不同路线。
- `register-resident-vector-chain` 只适用于已确认的 AIV 向量计算链、UB 驻留且 VEC 耗时主导的目标单元；不能作为内嵌 MM 或 Cube MM 的替换依据。
- DAV_3510 目标的 RoPE/rotary 检查 `paired-segment-rotate`；量化逐 case 记录 `quant_vf_route`（`shared-exponent-pack`、`two-pass-amax-cast` 或有证据的 `no_matching_vf_example`）。
- API 已在 SDK 声明或同环境存在成功反例时，不得把 host/device 可见域或构建契约问题误判为 `api_missing`。
- 队列、buffer、event 或偶现卡死可用 `ascendc-sync-audit`，但结论必须结合语义和动态复验。

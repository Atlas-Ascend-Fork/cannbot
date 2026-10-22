# 前处理

两类输入的原工程在最终交付前都保持不变。按 [extraction.md](extraction.md) 将目标算子和最小依赖闭包从原工程剥离：注册输入生成单算子自定义注册工程，直调输入生成单算子直调工程；已有独立工程也需物理副本与闭包验证。前处理保持调用方式、kernel/tiling 算法和公开语义，不做注册转直调。不得只用全仓的单算子构建开关冒充独立工程。

产出 `extraction-manifest.json`，记录原工程/工作工程映射、逐文件 SHA、依赖闭包、必要工程适配和入口/产物身份。注册工程按当前 SDK 的自定义工程模板构建，并证明实际加载本次自定义产物而非系统同名算子。一般算子补持久 `msprof application` runner；注册 runner 使用注册入口，MC²/多 rank 加载 `ascendc-mc2-best-practice` 并沿用 `msprof op` harness。harness 不得修改 kernel、Tiling、launch ABI 或功能入口。

准备阶段同时产出 `source-compatibility.md`：从原工程的 build config、`SocVersion` 路由、架构目录和 kernel 入口列出“工程支持 SoC / 本次 `TARGET_SOCS` / 证据 / 是否已验证”，定位公开契约面（`op_api/`、op def/proto、infer shape、接口适配头），盘点共享文件/传递依赖、TilingKey/模板分支及使用者。这份盘点只陈述源码事实，不把当前设备或 A5 专用工作基线推断为工程唯一支持代际。两类输入都保存原始算子源码快照（包含既有脏改动），供最终交付 diff 使用。

前处理代理加载 TTK 标准 skill（`ttk-how-run-test`，排障用 `ttk-how-diagnose`），在实际工作基线上运行整个功能验收子集，并用相同原始 case/golden/阈值核对剥离前后语义与加载身份。精度结论严格按`ops-perf-acceptance-criteria` 的精度规则。准备通过后进入 round1；独立静态 review 阶段被取消，检查点只在分析专家阅读源码和 profiling 时按需核对，输出直接并入 `roundN/analysis.md`。

# 单算子工程剥离

输入为原工程、目标算子、`RUN_MANIFEST`、独立输出目录和冻结用例库存。按派发信封的前处理验收要求执行；只写分配目录，原工程和 SDK 只读。基线评估未交付冻结用例时返回调用方补齐，不提前跳过阶段。

## 1. 识别与留证

沿调用入口、构建 target、host tiling、kernel 分派识别实际调用方式，不能只凭目录名判定：

| 原输入 | 工作工程 | 验证入口 |
|---|---|---|
| 注册算子 | 单算子自定义注册工程 | 原有 aclnn / 框架注册入口，加载本次自定义产物 |
| 直调算子 | 单算子直调工程 | 原 launch ABI 和 kernel 入口 |
| 已独立的单算子工程 | 同类型的物理副本 | 复用合规构建/harness |

同时存在两种入口时沿用户用例的实际入口识别；无法确定时上报主 Agent。不得自动执行注册转直调，或因直调输入而跳过工程剥离。

从原仓库真实构建规则盘点最小闭包：目标源码、公共头/模板、host 注册/tiling/infer shape、API 适配、构建模块/代码生成输入、链接依赖与运行时资产。区分 SDK 依赖和仓库私有依赖；不能把执行 `--ops=<op>` 的全仓工作树当成剥离结果。读取相关 README/CI/构建脚本，不推测工具参数。

保存原工程 Git revision、相关文件 SHA 及已有脏改动的内容快照；Git HEAD 不能代表未提交源码。`source-compatibility.md` 列出工程支持 SoC、本次目标 SoC、证据、共享文件/依赖、模板实例化/TilingKey 分支、公开契约面及源文件到工作文件的映射。目标 SoC 的别名须由配置或 SDK 取证映射，不能把 A2/A3/A5 名称直接当作通用构建参数。

## 2. 构造独立工程

复制目标算子和实际依赖，保持可追溯目录关系和许可证。采用普通文件副本，禁止可写软链接、硬链接、引用原仓库的 include/link 路径或借用原 build 产物。SDK 可以作为已声明外部依赖；其他源码依赖应复制进工作目录，或明确记录为无法闭合的依赖。

### 注册输入

参考用户指定的 [CANN 8.1.RC1 自定义算子工程文档](https://www.hiascend.com/document/detail/zh/canncommercial/81RC1/developmentguide/opdevg/Ascendcopdevg/atlas_ascendc_10_0006.html)。实际脚手架和参数必须来自本次 CANN 安装的模板/生成工具或同版本官方样例；旧版文档不能证明新版参数仍兼容。网页只有导航或不可读时记录这一限制，改查已安装模板，不编造命令。

用核实过的自定义工程骨架容纳原 `op_host`、`op_kernel` 和必要的 API/图注册/公共依赖，只构建一个对外目标算子。原 API 内部组合多个算子时保留其真实调用链和必要依赖，不能裁成单 kernel；依赖不能独立携带时明确阻塞。

保持原 OpType、I/O/attr/dtype/format、infer shape、参数检查、TilingData、TilingKey 和所有原分派语义。生成器的 Add 示例或自动生成 API 不能覆盖原算子声明/适配语义。API 注册和 tiling 注册的重复定义应在工程接线层解决，不能删除算法或原有检查来凑编译。

编译、安装到本次工作区的自定义产物目录；使用工具实际支持的本地安装选项和进程环境，不覆盖 SDK/系统 OPP。核对加载库绝对路径、SHA、vendor 搜索路径和实际调用入口；出现内置同名算子歧义时，先解决并取证加载顺序，未证实自定义产物被调用前不能验收。确需别名验证副本时仅在独立副本内按生成工具规则一致改名，记录双向映射，交付仍保留原公开名字。

### 直调输入

保留原 host launch、参数打包、workspace、stream 和 kernel 入口，只剥离多算子构建依赖并补最小可运行入口。不要套注册工程或更换 launch ABI。已有独立 demo 可直接复制并验证闭包。

两类输入都只做工程接线适配。逐项记录必要 include/build/生成器路径差异；不得在前处理调整 tiling、删未命中模板、替换公共实现或引入优化路由。

## 3. 验证与交付

1. 在工作目录以本次 SDK 真实构建目标。检查构建依赖/编译命令和加载记录不含原仓库路径；在不提供原仓库 include/lib/PYTHONPATH 的环境下构建运行。无法解除源码依赖时返回未完成，不能仅以某次编译成功认定已剥离。
2. 一般算子提供持久 `msprof application` runner；MC²/多 rank 沿用 `ascendc-mc2-best-practice` harness。注册 runner 通过注册入口执行，不直接 launch kernel。补 harness 不改变算法和功能入口。
3. 对照原实现与工作工程，记录相同 case 的接口、输出、host tiling、TilingKey/模板分支及加载身份；功能验收子集的完整 strict/conditional 门禁由前处理代理调用 TTK 执行。已有原实现失败按统一精度规则处理。
4. 再核对原源码 SHA 不变，交付未优化工作基线、构建/加载/harness 证据和 `source-compatibility.md`。缺硬件或构建条件时分清已完成静态检查与未完成动态验证。

`extraction-manifest.json` 至少包含：`schema_version=1`、`invocation=registry|direct`、原仓库/算子与工作目录、原源码快照身份、CANN/工具版本、逐文件 `source→working` 路径与两侧 SHA、适配理由、复制/外部依赖清单、原入口/工作入口/产物身份、构建命令/依赖证据、目标 SoC 与验证状态。它是回集成映射和后续分析的输入，不是第二份 run-manifest。

## 评测入口

修改剥离规则后可按 `$PLUGIN_ROOT/workflows/references/validation-cases.md` 选择真实工程验证；后续候选的代际与模板保护遵循`$PLUGIN_ROOT/workflows/references/source-isolation.md`。

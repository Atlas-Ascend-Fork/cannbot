---
name: ops-requirement-analysis
description: >-
  为一个待开发算子产出需求分析文档 REQUIREMENTS.md。按「算子名解析 → 模型研究 / 竞品(TF·PyTorch)研究 /
  CANN 方案研究 → 需求总结」的流水线，把模型场景、竞品实现、CANN 现状与客户需求汇总成一份结构固定的需求文档。当需要生成算子需求文档 / REQUIREMENTS.md / 需求分析时触发。
disable-model-invocation: true
---

# 算子需求分析 Skill

据算子名与客户需求，产出 `REQUIREMENTS.md`。本 skill 是一条流水线的合并版：先解析算子名在各框架的映射，
再从模型场景 / 竞品实现 / CANN 现状三个维度做研究，最后汇总成结构固定的需求文档。


---

## 一、输入

| 输入 | 来源 | 说明 |
|:-----|:-----|:-----|
| `{OP}` | 任务目标 | 算子名（snake_case，如 `softplus_v2_grad`） |
| 客户需求 | 任务目标 / 用户 prompt | 运行环境、调用方式、网络信息（缺省用默认值并标注「假设」） |
| 参考源码仓 | `reference/`（若存在） | CANN `ops-*`/`canndev`、`op-plugin`、`torchair`、竞品 `pytorch`/`tensorflow` |

**源码路径**（若 `reference/` 存在则实证搜索，缺失则降级）：见下方「源码路径与搜索层级」。
**降级规则**：`reference/` 不存在时，不得编造行号/文件路径级证据；改以模型知识 + WebSearch（论文、框架官方文档、公开源码）
研究，并在文档中标注「未接入源码仓，以下为公开资料 / 模型知识推导」。

---

## 二、执行流水线

```
阶段1 名称解析   → 在 CANN / TensorFlow / PyTorch 中定位算子，得跨框架映射（内部结论，不单独出文件）
阶段2 三维研究   → 并行产出 research/ 下的中间件：
        ├── research/model_research.md              模型场景与数学背景
        ├── research/opensource/{框架}/            竞品实现研究（实际找到的框架，可 TF/PyTorch 之一或两者，§4.2）
        │     ├── code_walkthrough.md               调用链路走读
        │     ├── code_design.md                    实现分析
        │     └── formula.md                        从竞品 kernel 提取的公式
        └── research/cann/                          CANN 现状（A2/A3 既有实现参照，三件套，§4.3）
              ├── code_walkthrough.md               调用链路走读（贴码 + 内联注释）
              ├── code_design.md                    交付件覆盖总览 + 分章设计分析
              └── formula.md                        从既有 kernel Compute 提取的数学公式（语义锚定）
阶段3 需求总结   → 按输出模板 COPY 研究中间件 + 自行生成「需求背景 / 框架差异 / 客户需求 / 需求总结」
                   → 组装成 REQUIREMENTS.md
```

阶段 2 的三类研究相互独立；有 SubAgent 能力时应并行发起，无则顺序执行，产物落到 `research/` 下。
**冲突裁决**：语义与公式以**竞品实现**为准；签名与交付件事实**官方 IR 命中时**以 IR 为唯一事实源（防同名多义），
**未命中时**（全新算子）以竞品接口为设计基准（aclnn 对标 PyTorch、GEIR 对标 TensorFlow）并标注依据。

---

## 三、阶段 1 · 算子名解析（内部结论）

在各框架定位算子，形成映射表（**不单独出文件**，作为阶段 2/3 的事实来源）：

| 框架 | 定位方法（有源码仓时） | 无源码仓时 |
|:-----|:----------------------|:-----------|
| CANN | 先查本地内置 proto（见下）；再 `find reference/cann/ops-*/ -type d -iname "*{op_snake}*"`；未中则回退 `canndev/ops/`；交付件搜索见下表 | 同左（本地内置 proto 不依赖源码仓），再按已知 CANN 命名 + 公开文档推断 |
| PyTorch | `native_functions.yaml` grep `- func: {op}`；`torch/nn/functional.py` | 官方 API 文档 + 公开源码（aten native）|
| TensorFlow | `core/ops/*.cc` grep `REGISTER_OP("{Op}")` | 官方 API 文档 |

> **本地内置 proto 是 CANN 侧最高事实源**：`grep -rn "REG_OP({PascalCase})" $ASCEND_OPP_PATH/built-in/op_proto/inc/`，
> 命中同名即权威 IR，原文摘录进 `research/cann/code_design.md`；语义推断（命名约定 / 竞品语义）不得凌驾其上，
> 冲突时并列两者并注明「以本地内置 proto 为准」。

**官方 IR 锚定（强制，防同名多义误判）**：名称解析必须先锚定官方 `REG_OP` 的**输入输出签名**再谈语义：

1. **签名以官方 IR 为准**：`grep -rn "REG_OP({PascalCase})" $ASCEND_OPP_PATH/built-in/op_proto/inc/` 命中后，
   将 `.INPUT(...)` / `.OUTPUT(...)` / `.ATTR(...)` 逐字摘录进 REQUIREMENTS.md（GEIR 设计 / API 设计一节），
   **输入的个数、名称、dtype、语义全部以官方 IR 为唯一事实源**，不得按模型先验改写（如把双输入改单输入、给无 attr 的算子加 mode 属性）。
2. **同名实体必须显式消解**：同名算子可能存在于 CANN 内置注册表、vendor 包、竞品框架中且对应**不同语义**。
   必须先在本地内置 `REG_OP` 命中处锚定官方签名，再逐一列出其余同名实体并明确「以本地内置官方 IR 为准，本需求沿用其输入输出签名」；
   禁止在没有官方 IR 证据时自行杜撰 vendor/自定义同名算子语义。
3. **「旧代际已支持、需补齐新代际」优先按代际补齐语义理解、且以官方 IR 芯片覆盖为据**：提示词出现「旧平台已有、需在新平台补齐」等表述时，
   先按公共 skill [`npu-arch`](../npu-arch/SKILL.md) 查代号→芯片代际映射，映射表见 [`npu-arch-guide.md` §架构代号别名](../npu-arch/references/npu-arch-guide.md)（A2→Ascend910B、A3→Ascend910_93、A5→Ascend950 等），
   再以官方 `REG_OP` 的芯片覆盖（`AddConfig`）核对：旧代际确实已支持、目标代际缺失 → 属**芯片代际补齐**（沿用既有接口，补实现），
   **不是**算子功能层面新增属性；不得仅凭提示词字符串把代际标签包装成 mode/谓词属性。

**算子名格式**：目录 snake_case（`softplus_v2_grad`）、注册名 PascalCase（`SoftplusV2Grad`）、
aclnn 函数 `aclnn{PascalCase}`。版本后缀（V2/V3）是算子名组成部分，不可省略或模糊匹配。

**框架选择（自主）**：以实际能定位到的框架为准。三者都要尽力研究；某框架完全找不到就在文档中标注 ❌ 并跳过其竞品章节。

---

## 四、阶段 2 · 三维研究（产出 research/ 中间件）

**决策优先级（冲突时裁决）**：
- **语义与公式 → 以竞品实现为准**（最主要的语义基准与参考 oracle 来源）。
- **签名 / dtype / 交付件事实 → 分场景**：官方 IR **命中**（内置算子、代际补齐）时以 IR 为唯一事实源
  （防同名多义误判），竞品口径不得凌驾；官方 IR **未命中**（全新算子）时以**竞品接口为设计基准**
  （aclnn 对标 PyTorch、GEIR 对标 TensorFlow），并在文档中标注依据。
所有 Markdown 中间件**标题一律不加序号**（纯文本标题），编号在阶段 3 汇总时统一添加。

### 4.1 model_research.md（模型场景）
落 `research/model_research.md`，覆盖：算子数学背景（前向 / 梯度公式、与相关激活/算子的关系、原始论文链接）、
典型模型场景（2–5 个，每个含 Mermaid 结构图 + 输入输出表 + 计算逻辑 + 参考链接）、调用方式建议（推荐 / 不推荐场景 + 参数配置）、总结。
有融合算子变体时追溯其社区演进线。

**来源纪律**：L1 arXiv → L2 GitHub 官方仓 → L3 HuggingFace → L4 博客（仅补充）。链接须真实有效；
模型结构对照论文/源码验证，无法验证的标「未验证」；资料不足标「信息有限」，不编造。

### 4.2 opensource/{框架}/（竞品实现研究，三件套 + 检索纪律）

对每个定位到的竞品框架，落 `research/opensource/{tensorflow|pytorch}/`，**walkthrough 先行**，其余据其产出：

1. **`code_walkthrough.md`**：按调用链路走读（Python 接口 → 注册/dispatch → OP 定义 → Kernel 实现），
   贴关键代码 + 内联注释（规范同 `references/code_walkthrough_guide.md`）。
2. **`code_design.md`**：算子基本信息（含**正反向身份**）/ 对外接口与 dtype / 声明 / 注册与 dispatch 与类型支持 /
   OP 定义与封装（Shape 推导 / dtype 转换 / 规格约束）/ Kernel 实现（空 Tensor / 确定性 / 边界值 / workspace /
   tiling / 计算步骤 / 分支）/ 实现评估（优化点 / NPU 可迁移性 / 不足）。
3. **`formula.md`**：从竞品 **Kernel 实现**直接提取公式（规则同 `references/formula_template.md`），
   与 CANN 侧并列对照，供 §6 框架差异对比引用。

**正反向判定**：PyTorch 的 `_backward` 后缀、TF 的 `Grad`/`Backprop` 后缀为反向算子；正反向互为独立算子，
互不混析，需求对象是哪个就只分析哪个。

**检索纪律**：
- 接口→注册算子：TF 搜 `tensorflow/python/ops/`（先 `tf.nn.*` 次 `tf.raw_ops.*`）；PyTorch 查 `native_functions.yaml` 与 `torch/nn/functional.py`。
- Kernel **GPU 优先**（`cuda`/`gpu`/`.cu`）；无 GPU 实现切 CPU 并标注「无 GPU 实现」。
- 检索失败：标注原因（如无 meta 函数、委托第三方库则标库名），不编造不中断。

**框架概念对照（检索定位用）**：

| 概念 | PyTorch | TensorFlow |
|:-----|:--------|:-----------|
| 算子声明 | `native_functions.yaml`（`func:` 行） | `REGISTER_OP` 宏 |
| GPU 注册 | `dispatch: CUDA:` | `REGISTER_KERNEL_BUILDER`（`.Device(DEVICE_GPU)`） |
| 类型分发 | `AT_DISPATCH_*` 宏 | `TF_CALL_*` 宏 + `.TypeConstraint<T>` |
| 计算入口 | `TORCH_IMPL_FUNC` | `OpKernel::Compute()` |
| Shape 推导 | `TORCH_META_FUNC` | `.SetShapeFn()` |
| Python 桥接 | `torch/_C/` 绑定 | `gen_*_ops.py` 自动生成 |

### 4.3 cann/（CANN 现状，A2/A3 既有实现参照，三件套）

落 `research/cann/`，**按序产出**（walkthrough → design → formula，后者依赖前者的 kernel 章节）：

1. **`code_walkthrough.md`**：按调用链路走读（aclnn API → 算子声明 → Shape 推导 → Tiling → Kernel → 框架适配），
   贴关键代码 + 内联注释，规范见 `references/code_walkthrough_guide.md`（含**变体全量覆盖**要求）。
2. **`code_design.md`**：开头为**交付件覆盖总览表**（GEIR / OpDef / 信息库 / API / Shape / Tiling / Kernel / 融合 /
   框架注册 / Torchair / op-plugin，各标 ✅/❌/⚠仅旧仓 + 路径 + 一句话），再按交付件类型分章
   （GEIR 原型含注册信息 + 按芯片分行的类型支持矩阵），每章末标注关联走读章节。
   其中**框架注册按证据枚举**：找到插件即列出其参数解析（如 ONNX 的 `ParseParams`：NodeProto 属性 → CANN 属性映射）
   与注册代码（如 `.FrameworkType(ONNX)`），TF/ONNX/Caffe 逐一标 ✅/❌；未找到标 ❌ 而非省略（ONNX 经 ATC 入图是常见推理通路）。
3. **`formula.md`**：从既有 kernel 的 **Compute 方法**逐条翻译 AscendC 指令为 LaTeX 公式（不走 TF 映射），
   标注源码位置与常量系数来源，多 dtype 分支分列。模板见 `references/formula_template.md`。
   **作用**：A5 需求语义锚定 A2/A3 实现而非仅凭论文/竞品；需求阶段只做语义与公式锚定。

> **无源码仓降级**：总览标注「未接入源码仓」，类型支持矩阵 / 接口设计以公开资料 + 模型知识给出并注明来源，
> **不得杜撰**文件行号；walkthrough 无码可贴时只保留链路说明；formula.md 标注「Kernel 代码缺失」并改按公开文档公式推导。

---

## 五、阶段 3 · 需求总结（组装 REQUIREMENTS.md）

严格按 `references/output_template.md` 组装 `REQUIREMENTS.md`。要点：

1. **COPY 研究中间件**：模板中标 `COPY: <file>` 的章节，把对应 research 文件**逐字复制原文**（禁止摘要 / 改写 / 省略），
   遵守 `references/output_template.md` 的「COPY 规范」（丢一级标题、标题降档、开头追加源链接）。
2. **自行生成章节**：需求背景（帮助读者从 0 理解算子功能，关注算子本身）、框架差异对比（据各 code_design.md 汇总对比表）、
   客户需求（网络信息 / 运行环境 / 调用方式 / 性能要求，用默认值时标「假设」）、需求分析总结（交付件清单 + ACLNN/GEIR 接口设计 + 框架兼容性）。
   其中**交付件清单按输出模板的「调用方式 → 交付件」映射推导取并集**（不写固定全"是"）；
   **接口设计遵守能力并集不可收窄原则**（代际补齐 / 新增 kernel 场景：不减 dtype、不移参数，新 kernel 声明子集 +
   IsAiCoreSupport 分发 fallback；全新算子按需声明），签名与阶段 1 官方 IR 锚定摘录一致。
   其中 **`REQUIREMENTS.md` §7.4 性能要求**只定关键 shape 集（不少于 4 条，取自本文件 §2 模型分析的真实场景；这是下限）与目标值来源路线**，
   不产出目标数值。路线判定按优先级实证执行、不臆断：
   - 先探 workspace 有无 `competitor-environment.json`（`COMPETITOR_ENVIRONMENT_CONFIG` 或当前目录向上查找），
     有则跑 `bash skills/ops-competitor-profiling/scripts/check-competitor-env.sh` 预检；退出码 0 → **路线 A（竞品实测）**。
   - 否则判本算子是否 Ascend950 纯 Vector（cube / cube-vector 混合不适用）；是 → **路线 B（理论评估）**。
    - 两条都不适用时如实记「两条来源均不适用 + 原因」，「性能目标」据此记「无目标值」，**不得编造性能指标**。
3. **统一标题编号**：research 中间件标题无编号；组装时对全文 `##`/`###`/`####` 统一加层级编号（`N` / `N.M` / `N.M.K`），
   编号与标题文本用一个空格分隔。
4. **重建 + 校验目录**：正文写完后扫描全部 `##`/`###` 标题重建目录；校验「正文标题集合」与「目录条目集合」数量相等、文本逐一匹配，
   不一致则修正目录直到通过。

**输出**：`REQUIREMENTS.md`（唯一交付物）。研究中间件保留在 `research/` 供 COPY 溯源。

---

## 六、源码路径与搜索层级（有 reference/ 时实证使用）

| 类别 | 路径 |
|:-----|:-----|
| CANN 安装包内置 proto（最先必查，无需源码仓） | `$ASCEND_OPP_PATH/built-in/op_proto/inc/` |
| CANN 算子仓（优先） | `reference/cann/ops-nn`、`ops-math`、`ops-transformer`、`ops-cv`、`ops-rand` |
| CANN 历史仓（回退） | `reference/cann/canndev` |
| PyTorch 适配 | `reference/ascend/op-plugin`、`reference/ascend/torchair` |
| 竞品 | `reference/competitor/pytorch`、`reference/competitor/tensorflow` |

CANN 交付件搜索：目录定位后按 `GEIR原型 / OpDef / 信息库 / API / Shape / Tiling / Kernel / 融合PASS / 框架注册 / Torchair / op-plugin`
逐类匹配（ops-* 优先，缺失回退 canndev）。框架注册插件检索路径：ops-* 下 `{module}/{op}/framework/`；
canndev 下 `built-in/framework/{tf_plugin|onnx_plugin|caffe_plugin}/{op}_plugin.cc`。
PyTorch：`native_functions.yaml` → `dispatch:` → cuda/cpu kernel。搜索须实际执行，禁止编造结果。

---

## 七、错误处理

| 场景 | 处理 |
|:-----|:-----|
| `reference/` 不存在 | 降级为公开资料 + 模型知识研究，文档标注来源，不编造行号 |
| 某框架定位不到 | 该框架竞品章节标 ❌ 跳过，不阻断 |
| research 中间件缺失 | 对应 COPY 章节标「待补充 / 源文件内容为空」，不编造 |
| CANN 侧部分交付件未找到 | code_design.md 汇总表对应项标 ❌ 并注明原因，不生成空章节 |
| 算子目录未找到（ops-* / canndev / 内置 proto 均未命中） | 判定为**全新算子**：总览全 ❌ 并注明「CANN 无既有实现，A5 为全新开发」；walkthrough 只保留目标链路说明；formula.md 按竞品/论文推导并标来源 |
| Kernel 代码为空或无法解析 | formula.md 标注「Kernel 代码缺失」，改按公开文档公式推导 |
| 客户需求缺项 | 用默认值（950PR/DT、单算子+PyTorch）并显式标注「假设」 |
| 目录校验失败 | 列出差异项，修正目录后重校验至通过 |

## 八、约束

1. REQUIREMENTS.md 必须包含输出模板的全部固定章节；COPY 章节须逐字复制，禁止摘要改写。
2. 交付件与接口设计必须与调用方式匹配；接口设计考虑昇腾亲和方案。
3. 数学公式 / dtype / 芯片 / 容差口径必须在本需求文档中完整可追溯。
4. 当算子输出或中间计算链存在浮点→整数 cast 时，必须声明 cast 语义：舍入模式（如截断/舍入/向零等）与溢出策略（NPU 上正向溢出饱和到 INT_MAX，负向溢出饱和到 INT_MIN），不得留空。
5. 所有外部链接必须有效；无源码仓时的推导须标注来源，不得杜撰文件级证据。
6. **公式提取**：formula.md 一律从既有 kernel 的 Compute 方法直接翻译，不走 TF 映射；常量系数标注来源行号。
7. **变体全量覆盖**：Tiling/Kernel 规格表列出 N 个变体，则走读与设计分析须逐一给出详细子章节（计算流程 + Buffer 分配 +
   Tiling 策略），禁止只写"主要"变体或"结构同模板 1"式跳过。
8. **顺序约束**：CANN 侧 walkthrough → design → formula 不可颠倒。

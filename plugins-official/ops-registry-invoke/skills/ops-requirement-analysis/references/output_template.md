# REQUIREMENTS.md 输出模板

## 输出位置

`REQUIREMENTS.md`（唯一交付物）。研究中间件保留在 `research/` 供 COPY 溯源：
`model_research.md`，以及 `opensource/{框架}/` 与 `cann/` 下的 `code_walkthrough.md`、`code_design.md`、`formula.md`
（各 walkthrough 不 COPY，仅在对应章节末段以链接形式溯源）。

## 报告结构

> 组装时：research 中间件按 `COPY` 规范逐字复制；其余章节自行生成；全文标题统一加层级编号；最后重建并校验目录。

```markdown
# 目录

<!--
  目录约束：
  1. 必须包含全部 ### 及以上标题（H2+H3），禁止静态占位
  2. ### 较多时章节目录子项做缩进折叠
  3. 目录在全部章节写完后按实际标题扫描生成，不预先固定
-->

---

## 1 需求背景

<!-- 自行生成：帮助开发者从 0 理解这个算子是什么，描述算子必要功能，关注算子本身。来源：客户 prompt + 模型知识 + WebSearch。
     末段点明本次需求：目标芯片、目标框架、支持 dtype、以何种方式（registry-invoke / Ascend C）开发。 -->

## 2 模型分析

COPY: research/model_research.md

## 3 竞品分析 - TensorFlow

COPY: research/opensource/tensorflow/code_design.md（如存在，否则整章标 ❌ 未定位并省略）

### 3.x 公式推导（从竞品 kernel 提取）

COPY: research/opensource/tensorflow/formula.md（如存在）

<!-- 末段给出走读溯源链接 [code_walkthrough.md](research/opensource/tensorflow/code_walkthrough.md)。 -->

## 4 竞品分析 - PyTorch

COPY: research/opensource/pytorch/code_design.md（如存在，否则整章标 ❌ 未定位并省略）

### 4.x 公式推导（从竞品 kernel 提取）

COPY: research/opensource/pytorch/formula.md（如存在）

<!-- 末段给出走读溯源链接 [code_walkthrough.md](research/opensource/pytorch/code_walkthrough.md)。 -->

## 5 CANN 方案分析

COPY: research/cann/code_design.md（如存在）

### 5.x 公式推导（从既有 kernel 提取）

COPY: research/cann/formula.md（如存在；Kernel 缺失时为文档公式推导并含标注说明）

<!-- 末段给出代码走读溯源链接 [code_walkthrough.md](research/cann/code_walkthrough.md)。 -->

## 6 框架差异对比

<!-- 自行生成：据实际存在的 code_design.md 汇总对比表，列取实际存在的框架 -->

| 对比项 | {框架1} | {框架2} |
|:-------|:--------|:--------|
| 算子名 | | |
| 核心公式 | | |
| 数值稳定性 | | |
| 类型支持 | | |
| 参数差异 | | |
| 计算精度 | | |
| 算法实现 | | |
| workspace 使用 | | |

## 7 客户需求

来源：**用户给定 / 默认假设**

### 7.1 网络信息

<!-- 未指定则说明算子为通用算子，适用范围 -->

### 7.2 运行环境

芯片平台（默认 `Ascend 950PR/950DT`，非任务指定时标「假设」）

### 7.3 调用方式

| 类别 | 描述 |
|:-----|:-----|
| 调用方式 | 单算子模式（默认） |
| 调用框架 | PyTorch（默认） |

### 7.4 性能要求

<!-- 定关键 shape 集与目标值来源路线，不在此产出目标数值。 -->

**关键 shape 集**（**不少于 4 条**，从本文件 §2 模型分析的典型场景取真实 shape，不自造；这是下限不是上限——
两条来源的每条 case 边际成本都很低，覆盖越全越好。本阶段分支尚未划分；关键 shape 集为下限）：

| # | shape | dtype | 取自（模型/场景） |
|:--|:------|:------|:-----------------|
| 1 | | | |

**目标值来源路线**（二选一，按优先级判定并记录判定依据）：

| 路线 | 工具 | 适用条件 | 本算子是否适用 |
|:-----|:-----|:---------|:--------------|
| A 竞品实测（优先） | `ops-competitor-profiling` | workspace 存在 `competitor-environment.json` 且 `check-competitor-env.sh` 预检通过 | |
| B 理论评估（兜底） | `ascendc-performance-evaluation` | 无竞品环境；且本算子是 Ascend950 纯 Vector（cube / cube-vector 混合不适用） | |

**判定结论**：选定路线 = A / B / 两条均不适用（后者须写明原因，「性能目标」据此记「无目标值」）。

**目标口径**：耗时（μs，竞品口径为 `kernel_total_us_avg`；理论口径为引擎理论时延）或 GM 带宽利用率，二选一并说明达成率算法。

## 8 需求分析总结

来源：基于竞品分析、模型分析、客户需求推导

### 8.1 交付件

<!-- 交付件按映射推导（非固定全"是"）：先定 §7.3 调用方式，查表取并集，各标 是/否/可选 + 判断依据 -->

**调用方式 → 交付件映射**：

| 调用方式 | 必需交付件 |
|:---------|:-----------|
| 单算子模式 | aclnnAPI、OpDef、信息库、infershape、tiling、kernel |
| 图模式 | GEIR、OpDef、信息库、infershape、tiling、kernel、fusion_pass（可选） |
| TensorFlow 框架 | TF 插件、GEIR、OpDef、信息库、infershape、tiling、kernel、fusion_pass（可选） |
| PyTorch Eager | 单算子模式交付件 + op-plugin |
| PyTorch 图模式 | 单算子模式交付件 + GEIR、op-plugin、Meta 推导函数、Converter 转换 |

多种调用方式组合时交付件**取并集**（如「单算子 + PyTorch」→ 单算子交付件 + op-plugin）。
ONNX 通路（ATC 入图）需要时补框架插件注册（含 ParseParams 属性映射），结论须与 §5 CANN 现状一致。

| 交付件 | 是否需要 | 备注 |
|:-------|:---------|:-----|
| OpDef | 是 | 算子定义文件，必需 |
| 信息库 | 是 | 算子信息配置，必需 |
| infershape | 是 | Shape 推导实现 |
| tiling | 是 | Ascend C Tiling 策略 |
| kernel | 是 | Ascend C Kernel 核心实现 |
| aclnnAPI | 是 | 单算子模式必需 |
| PyTorch Eager | 是 | op-plugin 适配 |
| 框架插件注册 | 按需 | TF/ONNX/Caffe 映射；ONNX 通路（ATC 入图）需要时含 ParseParams 属性映射，结论须与 §5 CANN 现状一致 |

### 8.2 API 接口设计

#### 8.2.1 ACLNN 接口设计

<!-- 核心规则：aclnn 接口是所有 kernel 实现的能力并集。代际补齐/新增 kernel 时不可收窄（不减 dtype、不移参数）；
     新 kernel 声明子集（AICORE_DTYPE_SUPPORT_LIST），按 IsAiCoreSupport() 分发，不支持的 fallback 旧实现。
     全新算子按需声明，避免盲目全类型。 -->

```cpp
aclnnStatus aclnnOperatorGetWorkspaceSize(
    Type name, // 注释输入/输出、DataType、Format 等
    uint64_t* workspaceSize, aclOpExecutor** executor);
aclnnStatus aclnnOperator(void* workspace, uint64_t workspaceSize, aclOpExecutor* executor, aclrtStream stream);
```

#### 8.2.2 GEIR 设计

<!-- 核心规则同 aclnn：GEIR 为能力并集，新增 kernel 不可收窄（不减 dtype、不移参数、不收紧约束），
     新 kernel 声明子集，框架按 ImplyType + dtype 分发；新建 GEIR 按需声明，避免盲目 BasicType()。
     签名须与 §5 官方 IR 锚定摘录一致。 -->

| 字段分组 | 字段名 | 字段类型 | 字段类型范围 | 默认值 | Format | 说明 |
|:---------|:-------|:---------|:------------|:-------|:-------|:-----|
| INPUT/OUTPUT/ATTR | x | Tensor | f32/f16/bf16 | NA | ND | |

#### 8.2.3 框架兼容性

<!-- 对标规则：aclnn 接口参数尽量与 PyTorch 一致；GEIR 接口参数尽量与 TensorFlow 一致；
     两者都存在时接口尽量一致（避免不同调用方式感知差异）；无对标竞品（如新融合算子）时保持自洽一致。 -->

对比多个竞品的接口参数含义，说明 NPU 定义算子 GEIR 和 aclnn 的合理性：

1. **参数对比**：列出 PyTorch/TensorFlow 对应算子的参数
2. **差异说明**：说明 NPU 接口与竞品接口的差异点
3. **合理性论证**：论证差异设计的必要性（如昇腾硬件特性、性能优化等）

#### 8.2.4 数值口径分析

<!-- 对每个 dtype 路径分析以下四项，为每个 dtype 路径给出明确的数值行为约定 -->

| dtype 路径 | 中间计算精度 | 输出值域可行性 | 溢出行为 | 容差合理性 |
|:-----------|:------------|:--------------|:---------|:----------|
| <!-- 如 fp16 --> | <!-- 如 Cast→fp32 平方/累加/sqrt → CAST_RINT 回 fp16 --> | <!-- 如 sqrt 结果范围 [0, +Inf)，fp16 可表示 --> | <!-- 如 不溢出 / 溢出时返回 Inf --> | <!-- 如 max_relative 1e-3 合理 --> |
| <!-- 如 int32 --> | <!-- 如 Cast→fp32 平方/累加/sqrt → CAST_TRUNC 回 int32 --> | <!-- 如 sqrt(Σx²) 可能超出 INT32_MAX（x 值大时） --> | <!-- 如 超出时饱和到 INT32_MAX / 报错 / 限制输入范围 --> | <!-- 如 bitwise_equal 是否可能成立？int32→fp32 丢精度(>2^24) + fp32 sqrt 浮点运算 → 不可能 bitwise；建议 max_relative --> |

**分析要点**：
- **中间计算精度**：该 dtype 路径内部是否提升到更宽精度（如 int32→fp32、fp16→fp32）？提升后中间运算的精度特性是什么？
- **输出值域可行性**：计算结果（如 sqrt(Σx²)）的值域是否可能超出输出 dtype 的表示范围？给出具体边界（如 int32 输入 max² 的 sqrt 是否 > INT32_MAX）。
- **溢出行为**：当结果超出输出 dtype 范围时，应饱和到最大值 / 报错 / 限制输入范围？必须明确，不能留给实现阶段猜测。
- **Cast 语义（fp→int）**：当计算链中存在浮点→整数 cast 时，声明舍入模式（如截断/舍入/向零等）。NPU 上正向溢出饱和到 INT_MAX，负向溢出饱和到 INT_MIN，golden 与 kernel 必须一致遵循。
- **容差合理性**：如果内部计算涉及浮点运算（如 sqrt），bitwise_equal 是否从数学上可能成立？如果不可能，应使用 max_relative 并给出 rtol/atol。

---

## COPY 规范

所有 `COPY: <file>` 遵守：

1. **丢弃一级标题**：丢掉子文档的 `# 一级标题`。
2. **标题统一降档**：`新等级 = 原等级 + 父标题 # 数 − 1`。父标题为 `##`(2级) 时：子文档 `##`→`###`、`###`→`####`。
3. **开头追加链接**：粘贴前追加源文件链接 `[source.md](research/.../source.md)`。
4. **禁止摘要改写**：逐字复制原文，禁止摘要、改写、省略。
5. **添加标题编号**：源文件标题无编号，COPY 后按所在章节序号从头计算子序号添加层级编号。

## 标题编号规范

**职责分离**：research 中间件（model_research.md / code_design.md）标题**均不加序号**；`REQUIREMENTS.md` 组装时**统一加编号**。

- `##` → `N`（1, 2, 3 …）
- `###` → `N.M`（如 `2.1`）
- `####` → `N.M.K`（如 `2.1.1`）
- 格式：`## N 标题名`（编号与文本用一个空格分隔）。
- COPY 章节：源无编号，按所在章节序号从头计子序号（如第 2 章 COPY 的 `### 概述` → `### 2.1 概述`）。

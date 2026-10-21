<!--
require_template.md — 算子需求文档 (REQUIRE.md) 模板, interactive 模式
(无预置用例 / 无 golden, 纯需求描述触发) 使用.

两种用法:
1. 人工填写: 复制本模板, 把 {{OP_NAME}} 替换为算子名, 逐节填写内容,
   删除文末 {{RAW_DESC}} 一节;
2. prepare_case.py --from-desc 封装: 用户原始需求文本缺少必备节结构时,
   脚本按本模板包一层 —— 替换 {{OP_NAME}}, 并把原文原样填入 {{RAW_DESC}}
   (保留原文, 不改写); 原文已具备必备结构时不封装, 逐字落盘.

字段约定 (与 lint OL09 对齐: Stage 1 产出的 SPEC.md 必须能从 REQUIRE.md
推出 算子语义(数学公式) / 输入输出规格 / 精度要求 三节):

- 算子名 (op_name): 合法 Python 标识符 (如 relu / apply_adam_w),
  同时是 custom/<op>/ 目录名与 <op>_wrapper 命名前缀;
- 算子语义 (必填): 数学公式或逐操作描述, 是 golden 数值语义的唯一锚点;
- 输入输出规格: 每 tensor 一行 name/shape/dtype (shape 未知可写 unknown,
  由 Stage 1 intent-understand 推断);
- Shape 约束与动态轴 (可选): 对齐关系 (如 out.shape == in.shape)、动态轴名;
- 精度要求: rtol/atol/max_error_ratio, 缺省按输出 dtype 推导
  (float32: rtol=1e-3 atol=1e-3; FP16/BF16 更宽);
- 硬件与布局约束: 目标平台 / device id / 是否要求真实 NPU 验证;
- 性能目标: perf_target_us 可声明"无硬性目标"; tune_rounds 缺省 3;
- 接口契约: 必须导出 <op>_wrapper(...) -> torch.Tensor; 是否需要
  ModelNew 桥接 (interactive 默认不需要, staged 模式由调用方契约决定).
-->
---
schema_version: 1
op_name: {{OP_NAME}}
---

# {{OP_NAME}} 算子需求规格

> 本 REQUIRE 是 pypto-op-orchestrator Stage 1 的用户需求输入,
> 字段约定见 workflows/templates/require_template.md 头部注释。

## 算子语义 (数学公式/逐操作描述, 必填)

> 待补: 用数学公式或逐操作步骤描述算子语义, 例如 `out = relu(x)` 即
> `out[i] = max(x[i], 0)`。本节是 golden 数值语义的唯一锚点。

## 输入输出规格

**输入规格**:

| # | name | shape | dtype |
|---|------|-------|-------|
| 0 | `input0` | `待补` | `float32` |

**输出规格**:

| # | name | shape | dtype |
|---|------|-------|-------|
| 0 | `output0` | `待补` | `float32` |

## Shape 约束与动态轴 (可选)

> 待补: shape 对齐/推导关系与动态轴名; 无动态轴可写"未声明"。

## 精度要求

- 缺省按输出 dtype 推导: float32 取 `rtol=1e-3, atol=1e-3`; FP16/BF16 使用更宽容差。
- 如需逐输出标准, 逐输出声明 `rtol` / `atol` / `max_error_ratio`;
  判定语义: 元素超标 iff `|impl-ref| > atol + rtol*|ref|`,
  输出失败 iff 超标元素比例 > `max_error_ratio`。

## 硬件与布局约束

- 目标平台: 真实 NPU 验证 (device id 以 prepared_case.json 的 device_id 为准)。
- 布局/内存约束: 无额外声明时按 pypto 默认。

## 性能目标

- `perf_target_us`: 可声明具体数值 (us), 或声明"无硬性性能目标"
  (按工作流自带规范完成 Stage 7 调优与报告)。
- `tune_rounds`: Stage 7 调优轮次, 缺省 3; 0 表示仅基线测量不调优。

## 接口契约

1. 必须导出 `{{OP_NAME}}_wrapper(...) -> torch.Tensor`。
2. golden / impl / test 三文件分离。
3. interactive 模式默认**不需要** ModelNew 桥接;
   仅当被外部评测框架消费 (staged 模式) 时才需额外产出 `{{OP_NAME}}_pypto_impl.py`
   (含 ModelNew 类), 契约以调用方 prompt 为准。

## 原始需求描述

{{RAW_DESC}}
